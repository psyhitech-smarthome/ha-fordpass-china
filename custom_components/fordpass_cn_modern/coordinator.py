"""Token rotation, vehicle polling, and confirmed manual door commands."""

from __future__ import annotations

import asyncio
from datetime import timedelta, datetime, timezone
import logging
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .protocol.client import FordApi, FordApiError, Vehicle


class FordCoordinator(DataUpdateCoordinator[dict[str, tuple[Vehicle, dict]]]):
    def __init__(self, hass, entry: ConfigEntry, api: FordApi) -> None:
        super().__init__(hass, logger=logging.getLogger(__name__), name="FordPass China Modern", update_interval=timedelta(minutes=15))
        self.entry = entry
        self.api = api
        self._token_lock = asyncio.Lock()
        self._vehicle_command_locks: dict[str, asyncio.Lock] = {}
        self.locations: dict[str, dict] = {}

    async def _access_token(self) -> str:
        async with self._token_lock:
            return await self._access_token_unlocked()

    async def _access_token_unlocked(self) -> str:
        data = self.entry.data
        now_ms = int(time.time() * 1000)
        refresh_expires_ms = int(data.get("refresh_expires_ms", 0))
        access_is_fresh = now_ms + 60_000 < int(data["access_expires_ms"])
        refresh_has_headroom = not refresh_expires_ms or now_ms + 45 * 60_000 < refresh_expires_ms
        if access_is_fresh and refresh_has_headroom:
            return str(data["access_token"])
        if refresh_expires_ms and now_ms >= refresh_expires_ms:
            raise ConfigEntryAuthFailed("Ford DLT refresh credential expired")
        try:
            rotated = await self.api.refresh_dlt_token(str(data["refresh_token"]))
        except FordApiError as error:
            if error.http_status in (401, 403):
                raise ConfigEntryAuthFailed("Ford DLT credential refresh failed") from error
            raise UpdateFailed(f"Ford DLT refresh failed: {type(error).__name__}") from error
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **data,
                "access_token": rotated.access_token,
                "refresh_token": rotated.refresh_token,
                "access_expires_ms": rotated.access_expires_ms,
                "refresh_expires_ms": rotated.refresh_expires_ms,
            },
        )
        return rotated.access_token

    async def _async_update_data(self) -> dict[str, tuple[Vehicle, dict]]:
        try:
            token = await self._access_token()
            vehicles = await self.api.vehicles(token)
            result = {}
            for vehicle in vehicles:
                result[vehicle.vin] = (vehicle, await self.api.vehicle_status(token, vehicle.vin))
            if not result:
                raise UpdateFailed("Ford returned no authorized vehicles")
            for vehicle in vehicles:
                await self._refresh_location(token, vehicle.vin)
            return result
        except ConfigEntryAuthFailed:
            raise
        except (FordApiError, KeyError, TypeError, ValueError, UnicodeError) as error:
            if isinstance(error, FordApiError) and error.http_status in (401, 403):
                raise ConfigEntryAuthFailed("Ford vehicle authorization expired") from error
            raise UpdateFailed(f"Ford vehicle update failed: {type(error).__name__}") from error

    async def _refresh_location(self, token: str, vin: str) -> None:
        """Location failure must never make the basic vehicle sensors fail."""
        checked_at = datetime.now(timezone.utc).isoformat()
        previous = self.locations.get(vin, {})
        if not self.api.location_enabled:
            self.locations[vin] = {"query_status": "not_configured", "checked_at": checked_at}
            return
        try:
            async with asyncio.timeout(50):
                location = await self.api.vehicle_location(token, vin)
            if previous.get("reported_at") and location["reported_at"] < previous["reported_at"]:
                raise FordApiError("Location timestamp regressed")
            self.locations[vin] = {**location, "query_status": "success", "checked_at": checked_at, "last_success_at": datetime.now(timezone.utc).isoformat()}
        except (FordApiError, aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError, UnicodeError):
            self.locations[vin] = {**previous, "query_status": "failed", "checked_at": checked_at}

    async def async_set_door_lock(self, vin: str, *, lock: bool) -> None:
        """Send exactly one command, then confirm execution and reported state.

        A timeout is deliberately ambiguous: the car may still execute later.
        Never retry a state-changing request automatically.
        """
        if vin not in self.data:
            raise HomeAssistantError("车辆不在当前授权列表中")
        command_lock = self._vehicle_command_locks.setdefault(vin, asyncio.Lock())
        if command_lock.locked():
            raise HomeAssistantError("已有车门指令正在执行，请等待结果")
        async with command_lock:
            command_id = None
            command_type = "上锁" if lock else "解锁"
            try:
                token = await self._access_token()
                command_id = await self.api.send_door_lock_command(token, vin, lock=lock)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    await asyncio.sleep(2)
                    code = await self.api.door_lock_command_status(token, vin, command_id, lock=lock)
                    if code == 200:
                        break
                    if code != 552:
                        raise HomeAssistantError(f"福特报告车门{command_type}失败（状态 {code}）")
                else:
                    raise HomeAssistantError(f"车门{command_type}结果未知；请先查看福特派或车辆状态，不要立即重试")

                target = "LOCKED" if lock else "UNLOCKED"
                for attempt in range(5):
                    status = await self.api.vehicle_status(token, vin)
                    vehicle = self.data[vin][0]
                    self.async_set_updated_data({**self.data, vin: (vehicle, status)})
                    if status.get("vehiclestatus", {}).get("lockStatus", {}).get("value") == target:
                        return
                    if attempt < 4:
                        await asyncio.sleep(2)
                raise HomeAssistantError(f"福特已执行车门{command_type}指令，但车况尚未确认；请稍后核对")
            except (FordApiError, UpdateFailed, ConfigEntryAuthFailed, aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError) as error:
                if command_id is not None:
                    raise HomeAssistantError(f"车门{command_type}结果未知；请先查看福特派或车辆状态，不要立即重试") from error
                raise HomeAssistantError(f"车门{command_type}请求未获确认；请先核对车辆状态") from error
