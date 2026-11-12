"""Offline order-template contract tests. No Meta credentials or network calls."""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from modules import order_delivery

class Response:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return b'{"messages":[{"id":"wamid.order-test"}]}'

class OrderTemplateTests(unittest.TestCase):
    def test_approved_template_contract(self):
        captured = {}
        class Opener:
            def open(self, req, timeout):
                captured["url"] = req.full_url
                captured["payload"] = json.loads(req.data)
                return Response()
        env = {
            "WHATSAPP_ACCESS_TOKEN": "fake-token",
            "WHATSAPP_PHONE_NUMBER_ID": "1364782060053556",
            "WHATSAPP_API_VERSION": "v23.0",
            "WHATSAPP_ORDER_TEMPLATE": "esone_order_confirmation",
            "WHATSAPP_ORDER_LANGUAGE": "en_US",
        }
        with patch.dict(os.environ, env), patch.object(order_delivery.urllib.request, "build_opener", return_value=Opener()):
            result = order_delivery.send_confirmation(
                "9876543210", "Tangles Hair Lounge", "ES2026001",
                datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc), "INR 2999")
        self.assertEqual(result, "wamid.order-test")
        self.assertEqual(captured["url"], "https://graph.facebook.com/v23.0/1364782060053556/messages")
        payload = captured["payload"]
        self.assertEqual(payload["to"], "919876543210")
        self.assertEqual(payload["template"]["name"], "esone_order_confirmation")
        self.assertEqual(payload["template"]["language"]["code"], "en_US")
        self.assertEqual(payload["template"]["components"], [{
            "type": "body",
            "parameters": [{"type": "text", "text": x} for x in
                           ["Tangles Hair Lounge", "ES2026001", "12 October 2026", "INR 2999"]]
        }])

if __name__ == "__main__":
    unittest.main()
