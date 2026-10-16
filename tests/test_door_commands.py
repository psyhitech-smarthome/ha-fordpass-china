"""The Ford API must submit each owner command once and validate its receipt."""

import unittest
from unittest.mock import AsyncMock

from fordpass_china_next.client import FordApi, FordApiError, PrivateSettings


COMMAND_ID = "a3d99bb0-6f7e-4c21-8a64-21441a9bad61"


class DoorCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        settings = PrivateSettings("secret", "payload", "app", "codec")
        self.api = FordApi(None, settings)
        self.api.codec.encrypt_text = AsyncMock(return_value=("ciphertext", "iv"))
        self.api.codec.decrypt_text = AsyncMock()
        self.api._request = AsyncMock(return_value={"data": {"encryptedResponseBody": "reply", "xjw": "reply-iv"}})

    async def test_unlock_submits_once_and_requires_command_id(self):
        self.api.codec.decrypt_text.return_value = f'{{"status":200,"commandId":"{COMMAND_ID}"}}'
        result = await self.api.send_door_lock_command("token", "vin", lock=False)
        self.assertEqual(result, COMMAND_ID)
        self.api._request.assert_awaited_once()
        method, path, fields = self.api._request.await_args.args
        self.assertEqual((method, path), ("POST", "/api/cnxapi-cvinfo/v1/vehicles/send-command"))
        self.assertEqual(fields["commandType"], "DoorUnlock")

    async def test_submission_rejects_missing_receipt(self):
        self.api.codec.decrypt_text.return_value = '{"status":200}'
        with self.assertRaises(FordApiError):
            await self.api.send_door_lock_command("token", "vin", lock=True)
        self.api._request.assert_awaited_once()

    async def test_status_uses_fresh_vin_encryption_and_distinguishes_outcomes(self):
        self.api.codec.encrypt_text.side_effect = [("cipher-one", "iv-one"), ("cipher-two", "iv-two"), ("cipher-three", "iv-three")]
        self.api.codec.decrypt_text.side_effect = ['{"status":552}', '{"status":200}', '{"status":500}']
        codes = [await self.api.door_lock_command_status("token", "vin", COMMAND_ID, lock=True) for _ in range(3)]
        self.assertEqual(codes, [552, 200, 500])
        fields = [call.args[2] for call in self.api._request.await_args_list]
        self.assertEqual([field["encryptedVin"] for field in fields], ["cipher-one", "cipher-two", "cipher-three"])
        self.assertTrue(all(field["commandType"] == "DoorLock" for field in fields))

    async def test_invalid_command_id_never_polls(self):
        with self.assertRaises(ValueError):
            await self.api.door_lock_command_status("token", "vin", "", lock=True)
        self.api._request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
