import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

try:
    from custom_components.fordpass_cn_modern.coordinator import FordCoordinator
    from custom_components.fordpass_cn_modern.protocol.client import FordApiError
    from custom_components.fordpass_cn_modern.sensor import FordLocationSensor, distance_km
except ModuleNotFoundError:
    FordCoordinator = None


@unittest.skipIf(FordCoordinator is None, "Home Assistant is not installed")
class LocationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.coordinator = FordCoordinator.__new__(FordCoordinator)
        self.coordinator.locations = {}
        self.coordinator._access_token = AsyncMock(return_value="fake-token")
        self.location = {"latitude": 30.0, "longitude": 100.0, "address": "测试省测试市示例地址", "reported_at": "2020-01-01T08:00:00+08:00"}
        self.coordinator.api = SimpleNamespace(
            location_enabled=True,
            vehicles=AsyncMock(return_value=[SimpleNamespace(vin="test-vin")]),
            vehicle_status=AsyncMock(return_value={"vehiclestatus": {"fuel": 30}}),
            vehicle_location=AsyncMock(return_value=self.location),
        )

    async def test_both_queries_in_same_poll(self):
        result = await self.coordinator._async_update_data()
        self.assertEqual(result["test-vin"][1]["vehiclestatus"]["fuel"], 30)
        self.coordinator.api.vehicle_status.assert_awaited_once()
        self.coordinator.api.vehicle_location.assert_awaited_once()
        self.assertEqual(self.coordinator.locations["test-vin"]["query_status"], "success")

    async def test_location_failure_does_not_break_car_status(self):
        await self.coordinator._async_update_data()
        self.coordinator.api.vehicle_location.side_effect = FordApiError("failed")
        result = await self.coordinator._async_update_data()
        self.assertIn("test-vin", result)
        self.assertEqual(self.coordinator.locations["test-vin"]["query_status"], "failed")
        self.assertEqual(self.coordinator.locations["test-vin"]["reported_at"], self.location["reported_at"])

    async def test_regressed_location_is_not_published_as_success(self):
        await self.coordinator._async_update_data()
        self.coordinator.api.vehicle_location.return_value = {**self.location, "reported_at": "2019-12-01T08:00:00+08:00"}
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.locations["test-vin"]["query_status"], "failed")

    def test_distance_is_straight_line(self):
        self.assertEqual(distance_km(30, 100, 30, 100), 0)
        self.assertAlmostEqual(distance_km(0, 0, 0, 1), 111.195, places=2)

    def test_failed_lookup_hides_region_and_distance(self):
        self.coordinator.locations = {"test-vin": {**self.location, "query_status": "failed"}}
        for key in ("location_region", "distance_to_home"):
            sensor = FordLocationSensor.__new__(FordLocationSensor)
            sensor.coordinator = self.coordinator
            sensor._vin = "test-vin"
            sensor._spec = SimpleNamespace(key=key)
            self.assertIsNone(sensor.native_value)
