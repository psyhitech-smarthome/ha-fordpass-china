import unittest

from fordpass_china_next.signing import canonical_params, sign_r3


class R3SigningTests(unittest.TestCase):
    def test_sorted_null_skipping_and_beijing_date_boundary(self):
        params = {
            "z": "a",
            "timestamp": 1792014600000,
            "a": None,
            "b": 3,
        }
        self.assertEqual(canonical_params(params), "b=3&timestamp=1792014600000&z=a")
        self.assertEqual(
            sign_r3(params, secret_key="demo-secret", payload_key="demo-payload"),
            "61bc3bf8c371f6cddd516ee5671ee508aa6145d08aede513f2e3413ee2db9fce",
        )


if __name__ == "__main__":
    unittest.main()
