import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch
from modules import otp_delivery

class OtpFailureTests(unittest.TestCase):
    def test_meta_code_10_does_not_verify(self):
        body = json.dumps({"error":{"code":10,"error_subcode":200}}).encode()
        class Opener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(request.full_url,400,"Bad Request",{},io.BytesIO(body))
        env = {"WHATSAPP_ACCESS_TOKEN":"test-token","WHATSAPP_PHONE_NUMBER_ID":"123456789","WHATSAPP_OTP_TEMPLATE":"test_otp","WHATSAPP_API_VERSION":"v23.0"}
        with patch.dict(os.environ,env),patch.object(otp_delivery.urllib.request,"build_opener",return_value=Opener()):
            with self.assertRaises(otp_delivery.DeliveryError) as result:
                otp_delivery.send_otp("9876543210","482913")
        message = str(result.exception)
        self.assertIn("code 10",message)
        self.assertIn("error_subcode 200",message)
        self.assertNotIn("482913",message)
        self.assertIn("visit remains in progress",message)
