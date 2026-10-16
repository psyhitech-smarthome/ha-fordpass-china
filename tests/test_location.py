import math
import unittest
from fordpass_china_next.client import FordApiError, validated_location
from fordpass_china_next.signing import sign_lbs


class LocationProtocolTests(unittest.TestCase):
    def test_lbs_uppercase_base64_regression(self):
        params = {"iv": "abc", "source": 0, "secretVersion": "1.0", "token": "fake-token", "vin": "fake-cipher"}
        self.assertEqual(sign_lbs(params, secret_key="unit-test-secret", payload_key="unit-test-payload", timestamp_ms=1792100000123), "P51BVVY58JPMKAVYPTLOVSNGQDLFQ9SQ+BOD43CT9KQ=")
        params["timestamp"] = 1792100000123
        params["optional"] = None
        self.assertEqual(sign_lbs(params, secret_key="unit-test-secret", payload_key="unit-test-payload", timestamp_ms=1792100000123), "P51BVVY58JPMKAVYPTLOVSNGQDLFQ9SQ+BOD43CT9KQ=")

    def test_invalid_coordinates_rejected(self):
        for lat, lon in ((math.nan, 100), (math.inf, 100), (91, 100), (30, 181), (0, 0)):
            with self.subTest(lat=lat, lon=lon), self.assertRaises(FordApiError):
                validated_location(lat, lon, "", "2020-01-01 08:00:00")

    def test_vehicle_time_has_explicit_china_timezone(self):
        value = validated_location(30, 100, "test", "2020-01-01 08:00:00")
        self.assertEqual(value["reported_at"], "2020-01-01T08:00:00+08:00")
        self.assertEqual(value["coordinate_system"], "ford_lbs_unverified")

    def test_future_report_is_rejected(self):
        with self.assertRaises(FordApiError):
            validated_location(30, 100, "test", "2099-01-01 08:00:00")
