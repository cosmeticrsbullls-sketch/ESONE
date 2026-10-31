"""Offline regression tests for Meta copy-code OTP request formatting."""
import json
import os
import unittest
from unittest.mock import patch

from modules import otp_delivery


class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return b'{"messages":[{"id":"wamid.test"}]}'


class CopyCodePayloadTests(unittest.TestCase):
    def test_copy_code_requires_matching_body_and_button_values(self):
        captured = {}
        class FakeOpener:
            def open(self, request, timeout):
                captured["url"] = request.full_url
                captured["payload"] = json.loads(request.data)
                return FakeResponse()

        config = {
            "WHATSAPP_ACCESS_TOKEN": "dummy-token",
            "WHATSAPP_PHONE_NUMBER_ID": "123456789",
            "WHATSAPP_OTP_TEMPLATE": "esone_visit_otp",
            "WHATSAPP_API_VERSION": "v23.0",
            "WHATSAPP_OTP_LANGUAGE": "en_US",
        }
        with patch.dict(os.environ, config), patch.object(
            otp_delivery.urllib.request, "build_opener", return_value=FakeOpener()
        ):
            self.assertEqual(otp_delivery.send_otp("9876543210", "482913"), "wamid.test")

        self.assertEqual(captured["url"], "https://graph.facebook.com/v23.0/123456789/messages")
        payload = captured["payload"]
        self.assertEqual(payload["to"], "919876543210")
        self.assertEqual(payload["template"]["name"], "esone_visit_otp")
        self.assertEqual(payload["template"]["language"]["code"], "en_US")
        self.assertEqual(payload["template"]["components"], [
            {"type": "body", "parameters": [{"type": "text", "text": "482913"}]},
            {"type": "button", "sub_type": "url", "index": "0",
             "parameters": [{"type": "text", "text": "482913"}]},
        ])


if __name__ == "__main__":
    unittest.main()
