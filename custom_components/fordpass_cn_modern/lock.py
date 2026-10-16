"""Manually operated Ford vehicle door locks."""

from __future__ import annotations

from hashlib import sha256

from homeassistant.components.lock import LockEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(FordDoorLock(coordinator, vin) for vin in coordinator.data)


class FordDoorLock(CoordinatorEntity, LockEntity):
    _attr_has_entity_name = True
    _attr_name = "车门锁"
    _attr_icon = "mdi:car-door-lock"

    def __init__(self, coordinator, vin: str) -> None:
        super().__init__(coordinator)
        self._vin = vin
        vehicle = coordinator.data[vin][0]
        vehicle_id = sha256(vin.encode()).hexdigest()[:24]
        self._attr_unique_id = f"{vehicle_id}_door_lock"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vehicle_id)},
            "manufacturer": "Ford Motor Company",
            "model": vehicle.vehicle_type or "Connected vehicle",
            "name": vehicle.nickname or f"Ford {vehicle.vehicle_type or 'vehicle'}",
        }

    @property
    def is_locked(self) -> bool | None:
        if self._vin not in self.coordinator.data:
            return None
        status = self.coordinator.data[self._vin][1]
        value = status.get("vehiclestatus", {}).get("lockStatus", {}).get("value")
        return {"LOCKED": True, "UNLOCKED": False}.get(value)

    async def async_lock(self, **kwargs) -> None:
        await self.coordinator.async_set_door_lock(self._vin, lock=True)

    async def async_unlock(self, **kwargs) -> None:
        await self.coordinator.async_set_door_lock(self._vin, lock=False)
