import unittest

from urllib.parse import parse_qs, urlsplit

from fordpass_china_next.client import expiry_timestamp_ms, login_url_with_consents, new_ford_iv, policy_type_from_login_url


class ExpiryTests(unittest.TestCase):
    def test_absolute_milliseconds(self):
        self.assertEqual(expiry_timestamp_ms(1_800_000_600_000, now_ms=1_800_000_000_000), 1_800_000_600_000)

    def test_absolute_seconds(self):
        self.assertEqual(expiry_timestamp_ms(1_800_000_600, now_ms=1_800_000_000_000), 1_800_000_600_000)

    def test_relative_seconds(self):
        self.assertEqual(expiry_timestamp_ms(600, now_ms=1_800_000_000_000), 1_800_000_600_000)

    def test_relative_milliseconds(self):
        self.assertEqual(expiry_timestamp_ms(600_000, now_ms=1_800_000_000_000), 1_800_000_600_000)

    def test_login_url_requires_explicit_ford_host(self):
        with self.assertRaises(ValueError):
            login_url_with_consents("https://example.com/authorize")

    def test_login_url_adds_required_only_consents(self):
        base = "https://login.ford.com.cn/authorize?redirect_uri=https%3A%2F%2Fwww.ford.com.cn%2Fcb&client_id=demo"
        url = login_url_with_consents(base)
        self.assertTrue(url.startswith(base + "&"))
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["client_id"], ["demo"])
        self.assertEqual(query["tnc_accepted"], ["true"])
        self.assertEqual(query["tnc_consent1_accepted"], ["true"])
        self.assertEqual(query["tnc_consent2_accepted"], ["false"])

    def test_b2c_policy_type_is_api_enum(self):
        url = "https://login.ford.com.cn/CNB2CFORD.partner.onmschina.cn/B2C_1A_SIGNINSIGNUP_ZH-CN/oauth2/v2.0/authorize"
        self.assertEqual(policy_type_from_login_url(url), "SIGNINSIGNUP")

    def test_ford_iv_format(self):
        iv = new_ford_iv()
        self.assertEqual(len(iv), 16)
        self.assertTrue(all(97 <= byte <= 122 for byte in iv))
        self.assertNotEqual(iv, new_ford_iv())


if __name__ == "__main__":
    unittest.main()
