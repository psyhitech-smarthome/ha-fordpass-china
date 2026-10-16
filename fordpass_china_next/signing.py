"""R3 request signing for the FordPass China API.

Keys are supplied by the caller and must be stored outside this package.
This code deliberately does not include Ford application constants.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo
import base64
import json


_BEIJING = ZoneInfo("Asia/Shanghai")


def sign_lbs(params: Mapping[str, object], *, secret_key: str, payload_key: str, timestamp_ms: int) -> str:
    """LBS uses uppercase Base64, including uppercase alphabet conversion."""
    def normalize(value):
        if isinstance(value, Mapping):
            return {k: normalize(v) for k, v in sorted(value.items()) if v is not None}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        return value

    def value_text(value):
        if isinstance(value, (Mapping, list, tuple, bool)):
            return json.dumps(normalize(value), ensure_ascii=False, separators=(",", ":"))
        return str(value)

    timestamp = str(timestamp_ms)
    canonical = "&".join(f"{k}={value_text(v)}" for k, v in sorted(params.items()) if v is not None and k not in ("timestamp", "sign"))
    text = secret_key + canonical + timestamp + payload_key + secret_key[:5] + timestamp[-5:]
    return base64.b64encode(sha256(text.encode()).digest()).decode("ascii").upper()


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _value_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Mapping):
        return "{" + _joined_items(value) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + "&".join(_value_text(item) for item in value if item is not None) + "]"
    return str(value)


def _joined_items(params: Mapping[str, object]) -> str:
    return "&".join(
        f"{key}={_value_text(value)}"
        for key, value in sorted(params.items())
        if value is not None and key != "sign"
    )


def canonical_params(params: Mapping[str, object]) -> str:
    """Format parameters as the app's sorted, null-skipping R3 input."""
    return _joined_items(params)


def sign_r3(
    params: Mapping[str, object],
    *,
    secret_key: str,
    payload_key: str,
    timestamp_ms: int | None = None,
) -> str:
    """Calculate a lowercase hex R3 signature without storing key material."""
    if timestamp_ms is None:
        timestamp_ms = int(params["timestamp"])
    beijing_date = datetime.fromtimestamp(timestamp_ms / 1000, _BEIJING).strftime("%Y-%m-%d")
    daily_secret = _hash(_hash(beijing_date) + payload_key)
    content = f"secretKey2={daily_secret}&{canonical_params(params)}&secretKey={secret_key}"
    return _hash(content)
