"""Offline Meta Code 10 regression: diagnostics without leaking private data."""
import io
import json
import os
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest.mock import patch

from modules import order_delivery
from modules.otp_delivery import DeliveryError


class MetaCode10Tests(unittest.TestCase):
    def test_order_send_reports_code_without_secrets(self):
        token = "fake-private-token-very-secret"
        recipient = "9876543210"
        reference = "ORDER-SECRET-123"
        salon = "PRIVATE-SALON"
        error_body = json.dumps({"error": {
            "message": "Permission denied for " + recipient + " " + token,
            "code": 10,
            "error_subcode": 200,
        }}).encode()

        class FailingOpener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(error_body))

        env = {
            "WHATSAPP_ACCESS_TOKEN": token,
            "WHATSAPP_PHONE_NUMBER_ID": "1364782060053556",
            "WHATSAPP_API_VERSION": "v23.0",
            "WHATSAPP_ORDER_TEMPLATE": "esone_order_confirmation",
        }
        with patch.dict(os.environ, env), patch.object(
            order_delivery.urllib.request, "build_opener", return_value=FailingOpener()
        ):
            with self.assertRaises(DeliveryError) as caught:
                order_delivery.send_confirmation(
                    recipient, salon, reference,
                    datetime(2026, 10, 31, tzinfo=timezone.utc), "INR 999")
        message = str(caught.exception)
        self.assertIn("Meta HTTP 400", message)
        self.assertIn("code 10", message)
        self.assertIn("error_subcode 200", message)
        self.assertNotIn(token, message)
        self.assertNotIn(recipient, message)
        self.assertNotIn(salon, message)
        self.assertNotIn(reference, message)


if __name__ == "__main__":
    unittest.main()
