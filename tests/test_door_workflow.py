"""Simulated HA command-flow checks. These never contact a vehicle."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

try:
    from custom_components.fordpass_cn_modern.coordinator import FordCoordinator
    from homeassistant.exceptions import HomeAssistantError
except ModuleNotFoundError:
    FordCoordinator = None
    HomeAssistantError = Exception


@unittest.skipIf(FordCoordinator is None, "Home Assistant is not installed")
class DoorWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.coordinator = FordCoordinator.__new__(FordCoordinator)
        self.coordinator.data = {
            "test-vin": (object(), {"vehiclestatus": {"lockStatus": {"value": "UNLOCKED"}}})
        }
        self.coordinator._vehicle_command_locks = {}
        self.coordinator._access_token = AsyncMock(return_value="test-token")
        self.coordinator.async_set_updated_data = Mock()
        self.coordinator.api = SimpleNamespace(
            send_door_lock_command=AsyncMock(return_value="test-command"),
            door_lock_command_status=AsyncMock(side_effect=[552, 200]),
            vehicle_status=AsyncMock(return_value={"vehiclestatus": {"lockStatus": {"value": "LOCKED"}}}),
        )

    async def test_pending_then_confirmed_sends_once(self):
        with patch("custom_components.fordpass_cn_modern.coordinator.asyncio.sleep", new=AsyncMock()):
            await self.coordinator.async_set_door_lock("test-vin", lock=True)
        self.coordinator.api.send_door_lock_command.assert_awaited_once()
        self.assertEqual(self.coordinator.api.door_lock_command_status.await_count, 2)
        self.coordinator.api.vehicle_status.assert_awaited_once()
        self.coordinator.async_set_updated_data.assert_called_once()

    async def test_status_failure_never_resends(self):
        self.coordinator.api.door_lock_command_status = AsyncMock(return_value=500)
        with patch("custom_components.fordpass_cn_modern.coordinator.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(HomeAssistantError):
                await self.coordinator.async_set_door_lock("test-vin", lock=True)
        self.coordinator.api.send_door_lock_command.assert_awaited_once()
        self.coordinator.api.vehicle_status.assert_not_awaited()

    async def test_status_timeout_is_ambiguous_and_never_resends(self):
        self.coordinator.api.door_lock_command_status = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch("custom_components.fordpass_cn_modern.coordinator.asyncio.sleep", new=AsyncMock()):
            with self.assertRaisesRegex(HomeAssistantError, "结果未知"):
                await self.coordinator.async_set_door_lock("test-vin", lock=True)
        self.coordinator.api.send_door_lock_command.assert_awaited_once()
        self.coordinator.api.vehicle_status.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
