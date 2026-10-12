import io
import json
import os
import unittest
import urllib.error
from email.message import EmailMessage
from unittest.mock import MagicMock,patch
from modules.email_delivery import send,DeliveryError
from modules.account_recovery import mail_settings

class EmailDeliveryTests(unittest.TestCase):
    def message(self):
        message=EmailMessage();message['To']='user@example.test';message['Subject']='ESONE password reset'
        message.set_content('Use https://esone.example.test/reset-password?token=test-only')
        return message
    def config(self):return dict(EMAIL_PROVIDER='resend',EMAIL_FROM='ESONE <noreply@example.test>',RESEND_API_KEY='test-only-key',ESONE_PUBLIC_URL='https://esone.example.test')
    def test_https_payload_and_duplicate_key(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"id":"test-message-id"}'
        opener=MagicMock();opener.open.return_value=response
        with patch('modules.email_delivery.urllib.request.build_opener',return_value=opener):
            self.assertEqual(send(self.config(),self.message()),'test-message-id')
            first=opener.open.call_args.args[0]
            self.assertEqual(first.full_url,'https://api.resend.com/emails')
            body=json.loads(first.data)
            self.assertEqual(body['to'],['user@example.test'])
            self.assertIn('token=test-only',body['text'])
            send(self.config(),self.message())
            self.assertEqual(first.get_header('Idempotency-key'),opener.open.call_args.args[0].get_header('Idempotency-key'))
    def test_provider_errors_are_not_exposed(self):
        error=urllib.error.HTTPError('https://api.resend.com/emails',403,'private provider response',{},io.BytesIO(b'private'))
        with patch('modules.email_delivery.urllib.request.build_opener') as builder:
            builder.return_value.open.side_effect=error
            with self.assertRaises(DeliveryError) as raised:send(self.config(),self.message())
            self.assertNotIn('private',str(raised.exception))
    def test_settings_need_https_origin_and_sender(self):
        config=self.config()
        with patch.dict(os.environ,config,clear=True):self.assertEqual(mail_settings()['EMAIL_PROVIDER'],'resend')
        for url in ['http://esone.example.test','https://user:secret@esone.example.test','https://esone.example.test?secret=x']:
            with patch.dict(os.environ,{**config,'ESONE_PUBLIC_URL':url},clear=True):self.assertIsNone(mail_settings())
        with patch.dict(os.environ,{**config,'EMAIL_FROM':'sender\r\nInjected: value'},clear=True):self.assertIsNone(mail_settings())
