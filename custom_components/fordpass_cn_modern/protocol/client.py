"""Async client for the observed FordPass China API, with private inputs.

Authentication and door-lock commands are based on owner-validated traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import base64
import hmac
import math
import json
import secrets
import string
import time
from uuid import UUID
from urllib.parse import parse_qs, parse_qsl, urlsplit

import aiohttp

from .signing import sign_r3, sign_lbs


BASE_URL = "https://cn.api.mps.ford.com.cn"
APPLICATION_ID = "35F9024B-010E-4FE7-B202-62D941F8681C"


class FordApiError(Exception):
    """A Ford API call failed without disclosing response content."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.reason = reason


@dataclass(frozen=True, repr=False)
class PrivateSettings:
    sign_secret_key: str
    sign_payload_key: str
    app_key: str
    codec_bearer: str
    codec_url: str = "http://127.0.0.1:8766/codec"
    app_version: str = "6.14.0"
    client_type: str = "FP"
    os_type: str = "ios"
    brand: str = "FORD"
    lbs_secret_key: str = ""
    lbs_payload_key: str = ""
    lbs_application_id: str = ""


@dataclass(frozen=True, repr=False)
class DltTokens:
    access_token: str
    refresh_token: str
    access_expires_ms: int
    refresh_expires_ms: int


@dataclass(frozen=True, repr=False)
class Vehicle:
    vin: str
    model_year: str | None
    vehicle_type: str | None
    encrypted_vin: str
    nickname: str | None = None


class FordCodec:
    def __init__(self, session: aiohttp.ClientSession, settings: PrivateSettings) -> None:
        self._session = session
        self._settings = settings

    async def transform(self, operation: str, payload: bytes, iv: bytes, *, service: str = "x_api") -> bytes:
        import base64

        request = {
            "service": service,
            "operation": operation,
            "data_base64": base64.b64encode(payload).decode("ascii"),
            "iv_hex": iv.hex(),
        }
        headers = {"Authorization": f"Bearer {self._settings.codec_bearer}"}
        async with self._session.post(
            self._settings.codec_url,
            json=request,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                raise FordApiError(f"codec HTTP {response.status}")
            data = await response.json()
        return base64.b64decode(data["data_base64"], validate=True)

    async def encrypt_text(self, text: str) -> tuple[str, str]:
        import base64

        iv = new_ford_iv()
        encrypted = await self.transform("encrypt", text.encode("utf-8"), iv)
        return base64.b64encode(encrypted).decode("ascii"), iv.hex()

    async def decrypt_text(self, encoded: str, iv_hex: str) -> str:
        import base64

        encrypted = base64.b64decode(encoded, validate=True)
        return (await self.transform("decrypt", encrypted, bytes.fromhex(iv_hex))).decode("utf-8")


class FordApi:
    def __init__(self, session: aiohttp.ClientSession, settings: PrivateSettings) -> None:
        self._session = session
        self._settings = settings
        self.codec = FordCodec(session, settings)

    @property
    def location_enabled(self) -> bool:
        return bool(self._settings.lbs_secret_key and self._settings.lbs_payload_key and self._settings.lbs_application_id)

    async def vehicle_location(self, access_token: str, vin: str) -> dict[str, object]:
        """Query the last cloud-reported location without sending a car command."""
        if not self.location_enabled:
            raise FordApiError("LBS settings are missing", reason="not_configured")
        encrypted, iv = await self.codec.encrypt_text(vin)
        token_body = await self._request(
            "GET", "/api/cnxapi-token-exchange/v1/app/third-party-token",
            {"brand": self._settings.brand, "encryptedVin": encrypted, "xjw": iv, "tokenType": "LBS"},
            access_token=access_token,
        )
        data = token_body["data"]
        token = await self.codec.decrypt_text(str(data["encryptedAccessToken"]), str(data["xjw"]))
        lbs_iv = new_ford_iv()
        encrypted_vin = await self.codec.transform("encrypt", vin.encode(), lbs_iv, service="lbs_p2c")
        body = {"token": token, "vin": base64.b64encode(encrypted_vin).decode(), "iv": lbs_iv.hex(), "source": 0, "secretVersion": "1.0"}
        timestamp = int(time.time() * 1000)
        headers = {
            "X-AppKey": self._settings.lbs_secret_key,
            "X-Timestamp": str(timestamp),
            "X-Sign": sign_lbs(body, secret_key=self._settings.lbs_secret_key, payload_key=self._settings.lbs_payload_key, timestamp_ms=timestamp),
            "Ocp-Application-Id": self._settings.lbs_application_id,
            "osType": self._settings.os_type, "clientType": self._settings.client_type,
            "User-Agent": "Dart (dart:io)",
        }
        async with self._session.post(
            "https://api-connect.ford.com.cn/lbs-map/v2/public/app/queryLocation",
            json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200:
                raise FordApiError("Ford location HTTP failure", http_status=response.status)
            answer = await response.json(content_type=None)
        if not isinstance(answer, dict) or answer.get("code") != 200 or not isinstance(answer.get("data"), dict):
            raise FordApiError("Ford location query failed")
        data = answer["data"]
        expected = sign_lbs(data, secret_key=self._settings.lbs_secret_key, payload_key=self._settings.lbs_payload_key, timestamp_ms=int(answer["timestamp"]))
        if not hmac.compare_digest(expected, str(answer.get("sign", ""))):
            raise FordApiError("Ford location response signature mismatch")
        async def decrypt(field):
            raw = base64.b64decode(data[field], validate=True)
            return (await self.codec.transform("decrypt", raw, bytes.fromhex(data["iv"]), service="lbs_p2c")).decode()
        latitude, longitude = float(await decrypt("lat")), float(await decrypt("lon"))
        address = await decrypt("address") if data.get("address") else ""
        return validated_location(latitude, longitude, address, str(data["uploadTime"]))

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {
            "Application-Id": APPLICATION_ID,
            "appversion": self._settings.app_version,
            "clienttype": self._settings.client_type,
            "ostype": self._settings.os_type,
            "User-Agent": "Dart (dart:io)",
            "Accept-Encoding": "gzip",
        }
        if access_token:
            headers["auth-token"] = access_token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        fields: dict[str, object],
        *,
        access_token: str | None = None,
    ) -> dict[str, object]:
        payload = dict(fields)
        payload["timestamp"] = int(time.time() * 1000)
        payload["sign"] = sign_r3(
            payload,
            secret_key=self._settings.sign_secret_key,
            payload_key=self._settings.sign_payload_key,
        )
        headers = self._headers(access_token)
        options = {"params": payload} if method == "GET" else {"json": payload}
        async with self._session.request(
            method,
            BASE_URL + path,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
            **options,
        ) as response:
            if response.status != 200:
                reason = None
                try:
                    error_body = await response.json(content_type=None)
                    if (
                        isinstance(error_body, dict)
                        and error_body.get("errorCode") == 100500
                        and isinstance(error_body.get("error"), str)
                        and "whitebox decrypt error" in error_body["error"].lower()
                    ):
                        reason = "whitebox_decrypt_error"
                except (aiohttp.ContentTypeError, ValueError, UnicodeError):
                    pass
                raise FordApiError(
                    f"Ford HTTP {response.status} at {path}",
                    http_status=response.status,
                    reason=reason,
                )
            body = await response.json(content_type=None)
        if not isinstance(body, dict) or body.get("status") not in (0, 200, "200"):
            code = body.get("status") if isinstance(body, dict) else "invalid"
            raise FordApiError(f"Ford status {code} at {path}")
        return body

    async def bootstrap_login_url(self) -> str:
        body = await self._request(
            "GET",
            "/api/app-init/v1/app-setting/info",
            {
                "appVersion": self._settings.app_version,
                "clientType": self._settings.client_type,
                "osType": self._settings.os_type,
            },
        )
        return str(body["data"]["b2cLoginUrl"])

    async def _parse_tokens(self, body: dict[str, object]) -> DltTokens:
        data = body["data"]
        iv = str(data["xjw"])
        access = await self.codec.decrypt_text(str(data["encryptedAccessToken"]), iv)
        refresh = await self.codec.decrypt_text(str(data["encryptedRefreshToken"]), iv)
        return DltTokens(
            access_token=access,
            refresh_token=refresh,
            access_expires_ms=expiry_timestamp_ms(data["expiresIn"]),
            refresh_expires_ms=expiry_timestamp_ms(data["refreshExpiresIn"]) if data.get("refreshExpiresIn") else 0,
        )

    async def exchange_b2c_code(self, code: str, policy_type: str) -> DltTokens:
        encrypted, iv = await self.codec.encrypt_text(code)
        body = await self._request(
            "POST",
            "/api/cnxapi-token-exchange/v1/app/dlt-token-by-b2c-auth-code",
            {
                "encryptedAuthCode": encrypted,
                "xjw": iv,
                "brand": self._settings.brand,
                "osType": self._settings.os_type.upper(),
                "policyType": policy_type,
            },
        )
        return await self._parse_tokens(body)

    async def refresh_dlt_token(self, refresh_token: str) -> DltTokens:
        encrypted, iv = await self.codec.encrypt_text(refresh_token)
        body = await self._request(
            "POST",
            "/api/cnxapi-token-exchange/v1/app/refresh-dlt-token",
            {"encryptedRefreshToken": encrypted, "xjw": iv, "brand": self._settings.brand},
        )
        return await self._parse_tokens(body)

    async def vehicles(self, access_token: str) -> list[Vehicle]:
        body = await self._request(
            "GET",
            "/api/cnxapi-vds/v5/vehicles/list",
            {
                "appKey": self._settings.app_key,
                "appVersion": self._settings.app_version,
                "clientType": self._settings.client_type,
            },
            access_token=access_token,
        )
        data = body["data"]
        iv = str(data["xjw"])
        vehicles = []
        for item in data["list"]:
            vin = await self.codec.decrypt_text(str(item["encryptedVin"]), iv)
            nickname = None
            if item.get("encryptedNickName"):
                try:
                    nickname = (await self.codec.decrypt_text(str(item["encryptedNickName"]), iv)).strip() or None
                except (FordApiError, ValueError, UnicodeError):
                    pass
            vehicles.append(
                Vehicle(
                    vin,
                    item.get("modelYear"),
                    item.get("vehicleType"),
                    str(item["encryptedVin"]),
                    nickname,
                )
            )
        return vehicles

    async def vehicle_status(self, access_token: str, vin: str) -> dict[str, object]:
        encrypted, iv = await self.codec.encrypt_text(vin)
        body = await self._request(
            "GET",
            "/api/cnxapi-cvinfo/v1/vehicle-status",
            {"encryptedVin": encrypted, "xjw": iv},
            access_token=access_token,
        )
        data = body["data"]
        return json.loads(await self.codec.decrypt_text(str(data["encryptedResponseBody"]), str(data["xjw"])))

    async def _command_response(self, body: dict[str, object]) -> dict[str, object]:
        """Decode an authenticated command response without logging its contents."""
        data = body.get("data")
        if not isinstance(data, dict):
            raise FordApiError("Ford command response has no data")
        encrypted = data.get("encryptedResponseBody")
        iv = data.get("xjw")
        if not isinstance(encrypted, str) or not isinstance(iv, str):
            raise FordApiError("Ford command response is incomplete")
        try:
            decoded = json.loads(await self.codec.decrypt_text(encrypted, iv))
        except (TypeError, ValueError, UnicodeError) as error:
            raise FordApiError("Ford command response could not be decoded") from error
        if not isinstance(decoded, dict):
            raise FordApiError("Ford command response is invalid")
        return decoded

    async def send_door_lock_command(self, access_token: str, vin: str, *, lock: bool) -> str:
        """Submit one door-lock command; a returned ID is not execution success."""
        encrypted, iv = await self.codec.encrypt_text(vin)
        body = await self._request(
            "POST",
            "/api/cnxapi-cvinfo/v1/vehicles/send-command",
            {
                "commandType": "DoorLock" if lock else "DoorUnlock",
                "encryptedVin": encrypted,
                "xjw": iv,
            },
            access_token=access_token,
        )
        decoded = await self._command_response(body)
        command_id = decoded.get("commandId")
        if decoded.get("status") != 200 or not isinstance(command_id, str):
            raise FordApiError("Ford did not accept the door-lock command")
        try:
            UUID(command_id)
        except (ValueError, AttributeError) as error:
            raise FordApiError("Ford returned an invalid command ID") from error
        return command_id

    async def door_lock_command_status(
        self, access_token: str, vin: str, command_id: str, *, lock: bool
    ) -> int:
        """Return Ford's execution code: 552 pending, 200 completed."""
        if not isinstance(command_id, str) or not 0 < len(command_id) <= 128:
            raise ValueError("invalid Ford command ID")
        encrypted, iv = await self.codec.encrypt_text(vin)
        body = await self._request(
            "GET",
            "/api/cnxapi-cvinfo/v1/vehicles/command-execution-status",
            {
                "commandId": command_id,
                "commandType": "DoorLock" if lock else "DoorUnlock",
                "encryptedVin": encrypted,
                "xjw": iv,
            },
            access_token=access_token,
        )
        decoded = await self._command_response(body)
        status = decoded.get("status")
        if not isinstance(status, int) or isinstance(status, bool):
            raise FordApiError("Ford returned an invalid command status")
        return status


def validated_location(latitude: float, longitude: float, address: str, uploaded: str) -> dict[str, object]:
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
        raise FordApiError("Ford returned invalid coordinates")
    time_value = datetime.strptime(uploaded, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=8)))
    if time_value > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise FordApiError("Ford location timestamp is in the future")
    return {"latitude": latitude, "longitude": longitude, "address": address, "reported_at": time_value.isoformat(), "coordinate_system": "ford_lbs_unverified"}


def policy_type_from_login_url(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    for part in parts:
        if part.upper().startswith("B2C_1A_SIGNINSIGNUP_"):
            return "SIGNINSIGNUP"
    raise ValueError("Ford login URL did not contain the sign-in policy")


def new_ford_iv() -> bytes:
    """Match the app's 16-character lowercase ASCII white-box IV format."""
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(16)).encode("ascii")


def login_url_with_consents(url: str) -> str:
    """Match the official app's account-login URL after owner consent.

    The app appends these three parameters before opening B2C account login.
    Call this only after the owner explicitly confirms the required terms.
    The app supplies the second consent separately; this implementation does
    not opt in to it.
    """
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "login.ford.com.cn":
        raise ValueError("unexpected Ford login host")
    existing = {key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if existing.intersection({"tnc_accepted", "tnc_consent1_accepted", "tnc_consent2_accepted"}):
        raise ValueError("Ford login URL already contains consent parameters")
    separator = "&" if parsed.query else "?"
    return (url + separator + "tnc_accepted=true"
            "&tnc_consent1_accepted=true&tnc_consent2_accepted=false")


def expiry_timestamp_ms(value: object, *, now_ms: int | None = None) -> int:
    """Accept absolute Unix timestamps or relative seconds/milliseconds.

    The observed access expiry is an absolute millisecond timestamp. The
    refresh field has not yet been observed in a live login response.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    number = int(value)
    if number <= 0:
        raise ValueError("invalid Ford token expiry")
    if number >= 1_000_000_000_000:  # Unix milliseconds
        result = number
    elif number >= 1_000_000_000:  # Unix seconds
        result = number * 1000
    elif number >= 100_000:  # conservative for ambiguous long durations
        result = now_ms + number
    else:  # relative seconds
        result = now_ms + number * 1000
    if result > now_ms + 10 * 365 * 24 * 3600 * 1000:
        raise ValueError("implausible Ford token expiry")
    return result


def authorization_code_from_redirect(text: str) -> str:
    value = text.strip()
    if "://" not in value:
        return value
    parsed = urlsplit(value)
    for component in (parsed.query, parsed.fragment):
        code = parse_qs(component).get("code", [None])[0]
        if code:
            return code
    raise ValueError("Ford redirect URL did not contain an authorization code")
