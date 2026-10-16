"""Read-only Ford vehicle sensors."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime
import math
import re

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@dataclass(frozen=True)
class SensorSpec:
    key: str
    name: str
    path: tuple[str, ...]
    icon: str
    unit: str | None = None
    numeric: bool = False
    state_class: SensorStateClass | None = None


SENSORS = (
    SensorSpec("odometer", "Odometer", ("odometer", "value"), "mdi:counter", UnitOfLength.KILOMETERS, True, SensorStateClass.TOTAL_INCREASING),
    SensorSpec("fuel_level", "Fuel level", ("fuel", "fuelLevel"), "mdi:gas-station", PERCENTAGE, True, SensorStateClass.MEASUREMENT),
    SensorSpec("range", "Distance to empty", ("fuel", "distanceToEmpty"), "mdi:map-marker-distance", UnitOfLength.KILOMETERS, True, SensorStateClass.MEASUREMENT),
    SensorSpec("oil_life", "Oil life", ("oil", "oilLifeActual"), "mdi:oil", PERCENTAGE, True, SensorStateClass.MEASUREMENT),
    SensorSpec("front_left_tire", "Front left tire pressure", ("TPMS", "leftFrontTirePressure", "value"), "mdi:gauge", UnitOfPressure.KPA, True, SensorStateClass.MEASUREMENT),
    SensorSpec("front_right_tire", "Front right tire pressure", ("TPMS", "rightFrontTirePressure", "value"), "mdi:gauge", UnitOfPressure.KPA, True, SensorStateClass.MEASUREMENT),
    SensorSpec("rear_left_tire", "Rear left tire pressure", ("TPMS", "outerLeftRearTirePressure", "value"), "mdi:gauge", UnitOfPressure.KPA, True, SensorStateClass.MEASUREMENT),
    SensorSpec("rear_right_tire", "Rear right tire pressure", ("TPMS", "outerRightRearTirePressure", "value"), "mdi:gauge", UnitOfPressure.KPA, True, SensorStateClass.MEASUREMENT),
    SensorSpec("battery_health", "Battery health", ("battery", "batteryHealth", "value"), "mdi:car-battery"),
    SensorSpec("lock_status", "Lock status", ("lockStatus", "value"), "mdi:car-door-lock"),
    SensorSpec("ignition_status", "Ignition status", ("ignitionStatus", "value"), "mdi:engine"),
    SensorSpec("remote_start_status", "Remote start status", ("remoteStartStatus", "value"), "mdi:remote"),
    SensorSpec("last_refresh", "Last vehicle refresh", ("lastRefresh",), "mdi:clock-outline"),
    SensorSpec("driver_door", "Driver door", ("doorStatus", "driverDoor", "value"), "mdi:car-door"),
    SensorSpec("passenger_door", "Passenger door", ("doorStatus", "passengerDoor", "value"), "mdi:car-door"),
    SensorSpec("left_rear_door", "Left rear door", ("doorStatus", "leftRearDoor", "value"), "mdi:car-door"),
    SensorSpec("right_rear_door", "Right rear door", ("doorStatus", "rightRearDoor", "value"), "mdi:car-door"),
    SensorSpec("hood", "Hood", ("doorStatus", "hoodDoor", "value"), "mdi:car-door"),
    SensorSpec("tailgate", "Tailgate", ("doorStatus", "tailgateDoor", "value"), "mdi:car-door"),
    SensorSpec("inner_tailgate", "Inner tailgate", ("doorStatus", "innerTailgateDoor", "value"), "mdi:car-door"),
    SensorSpec("driver_window", "Driver window", ("windowPosition", "driverWindowPosition", "value"), "mdi:car-door"),
    SensorSpec("passenger_window", "Passenger window", ("windowPosition", "passWindowPosition", "value"), "mdi:car-door"),
    SensorSpec("left_rear_window", "Left rear window", ("windowPosition", "rearDriverWindowPos", "value"), "mdi:car-door"),
    SensorSpec("right_rear_window", "Right rear window", ("windowPosition", "rearPassWindowPos", "value"), "mdi:car-door"),
)


def nested_value(data: dict, path: tuple[str, ...]):
    value = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FordSensor(coordinator, vin, spec)
        for vin in coordinator.data
        for spec in SENSORS
    )
    async_add_entities(FordLocationSensor(coordinator, vin, key) for vin in coordinator.data for key in LOCATION_SENSORS)


class FordSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, vin: str, spec: SensorSpec) -> None:
        super().__init__(coordinator)
        self._vin = vin
        self._spec = spec
        vehicle = coordinator.data[vin][0]
        vehicle_id = sha256(vin.encode()).hexdigest()[:24]
        self._attr_unique_id = f"{vehicle_id}_{spec.key}"
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_state_class = spec.state_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vehicle_id)},
            "manufacturer": "Ford Motor Company",
            "model": vehicle.vehicle_type or "Connected vehicle",
            "name": vehicle.nickname or f"Ford {vehicle.vehicle_type or 'vehicle'}",
        }

    @property
    def native_value(self):
        if self._vin not in self.coordinator.data:
            return None
        payload = self.coordinator.data[self._vin][1]
        value = nested_value(payload.get("vehiclestatus", {}), self._spec.path)
        if value is None or not self._spec.numeric:
            return value
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None


LOCATION_SENSORS = {
    "location_region": ("车辆位置", "mdi:map-marker"),
    "distance_to_home": ("距家直线距离", "mdi:map-marker-distance"),
    "location_reported": ("位置上报时间", "mdi:clock-outline"),
    "location_checked": ("定位查询时间", "mdi:cloud-sync-outline"),
    "location_query": ("定位查询状态", "mdi:map-check-outline"),
}


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    value = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, value))))


class FordLocationSensor(FordSensor):
    def __init__(self, coordinator, vin, key):
        name, icon = LOCATION_SENSORS[key]
        super().__init__(coordinator, vin, SensorSpec(key, name, (), icon))
        if key == "distance_to_home":
            self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
        if key in ("location_reported", "location_checked"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def available(self):
        if not super().available:
            return False
        if self._spec.key in ("location_query", "location_checked", "location_reported"):
            return True
        return self.coordinator.locations.get(self._vin, {}).get("query_status") == "success"

    @property
    def native_value(self):
        info = self.coordinator.locations.get(self._vin, {})
        key = self._spec.key
        if key == "location_query":
            return {"success": "查询成功", "failed": "查询失败", "not_configured": "未配置"}.get(info.get("query_status"), "等待查询")
        if key in ("location_reported", "location_checked"):
            value = info.get("reported_at" if key == "location_reported" else "checked_at")
            return datetime.fromisoformat(value) if value else None
        if info.get("query_status") != "success":
            return None
        if key == "location_region":
            address = info.get("address", "")
            match = re.match(r".*?(?:自治州|地区|盟|市)", address)
            return match.group() if match else "福特已返回位置"
        home = self.coordinator.hass.config
        if (home.latitude == 0 and home.longitude == 0):
            return None
        # Ford's coordinate datum remains unverified. Round to whole km and
        # expose this as an estimate, not a tracker for home-zone automation.
        return round(distance_km(info["latitude"], info["longitude"], home.latitude, home.longitude))

    @property
    def extra_state_attributes(self):
        info = self.coordinator.locations.get(self._vin, {})
        return {"vehicle_reported_at": info.get("reported_at"), "last_query_at": info.get("checked_at"), "last_success_at": info.get("last_success_at"), "query_status": info.get("query_status"), "distance_is_approximate": True, "coordinate_system": info.get("coordinate_system"), "source": "Ford LBS"}
