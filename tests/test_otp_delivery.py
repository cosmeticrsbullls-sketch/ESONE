import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, CommunicationLog, VerificationOTP
from modules import otp_delivery
from main import _otp_hash

CONFIG={'ESONE_ENV':'production','WHATSAPP_ACCESS_TOKEN':'unit-test-token','WHATSAPP_PHONE_NUMBER_ID':'123456','WHATSAPP_OTP_TEMPLATE':'visit_otp','WHATSAPP_API_VERSION':'v25.0'}


class OtpTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def begin_visit(self):
        self.login('a')
        self.assertEqual(self.client.post('/visits/6/start',data={'latitude':23,'longitude':72}).status_code,200)
        return {'notes':'Meeting complete','csrf':self.csrf}

    def test_provider_acceptance_and_verify(self):
        data=self.begin_visit()
        with patch.dict(os.environ,CONFIG),patch('modules.otp_delivery.send_otp',return_value='wamid.test') as send:
            response=self.client.post('/visits/6/request-end-otp',data=data)
        self.assertEqual(response.status_code,200)
        code=send.call_args.args[1]
        self.assertNotIn(code,response.text);self.assertNotIn('TEST OTP',response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(VerificationOTP).one().status,'PENDING')
            log=db.query(CommunicationLog).one();self.assertEqual((log.status,log.provider_message_id),('ACCEPTED','wamid.test'))
        self.assertEqual(self.client.post('/visits/6/verify-end-otp',data={'otp':code,'csrf':self.csrf},follow_redirects=False).status_code,303)

    def test_failed_send_cannot_verify_or_clear_previous_code(self):
        data=self.begin_visit()
        with SessionLocal() as db:
            db.add(VerificationOTP(client_id=1,activity_id=6,purpose='VISIT_END',otp_hash=_otp_hash('654321'),status='PENDING',expires_at=datetime.now()+timedelta(minutes=5),created_at=datetime.now()-timedelta(minutes=2)));db.commit()
        with patch.dict(os.environ,CONFIG),patch('modules.otp_delivery.send_otp',side_effect=otp_delivery.DeliveryError('Delivery failed.')):
            self.assertEqual(self.client.post('/visits/6/request-end-otp',data=data).status_code,502)
        with SessionLocal() as db:
            self.assertEqual([o.status for o in db.query(VerificationOTP).order_by(VerificationOTP.id)],['PENDING','FAILED'])
            self.assertEqual(db.query(CommunicationLog).one().status,'FAILED')
            self.assertEqual(db.get(Activity,6).status,'IN_PROGRESS')

    def test_cooldown_csrf_and_attempt_limit(self):
        data=self.begin_visit()
        with patch.dict(os.environ,CONFIG),patch('modules.otp_delivery.send_otp',return_value='wamid.test') as send:
            self.assertEqual(self.client.post('/visits/6/request-end-otp',data={**data,'csrf':''}).status_code,403)
            self.assertEqual(self.client.post('/visits/6/request-end-otp',data=data).status_code,200)
            self.assertEqual(self.client.post('/visits/6/request-end-otp',data=data).status_code,429)
            self.assertEqual(send.call_count,1)
        for attempt in range(5):
            self.assertEqual(self.client.post('/visits/6/verify-end-otp',data={'otp':'invalid','csrf':self.csrf}).status_code,400)
        with SessionLocal() as db:
            self.assertEqual(db.query(VerificationOTP).one().status,'LOCKED')
            self.assertEqual(db.get(Activity,6).status,'IN_PROGRESS')

    def test_render_never_enables_local_test_code(self):
        data=self.begin_visit()
        with patch.dict(os.environ,{'ESONE_ENV':'test','RENDER':'true','WHATSAPP_ACCESS_TOKEN':''}):
            response=self.client.post('/visits/6/request-end-otp',data=data)
        self.assertEqual(response.status_code,503);self.assertNotIn('TEST OTP',response.text)
        with SessionLocal() as db:self.assertEqual(db.query(VerificationOTP).count(),0)


class TransportTests(unittest.TestCase):
    def test_meta_payload_and_number_normalization(self):
        response=MagicMock();response.read.return_value=b'{"messages":[{"id":"wamid.test"}]}'
        opener=MagicMock();opener.open.return_value.__enter__.return_value=response
        with patch.dict(os.environ,CONFIG),patch('urllib.request.build_opener',return_value=opener):
            self.assertEqual(otp_delivery.send_otp('95586 58907','123456'),'wamid.test')
        request=opener.open.call_args.args[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,'https://graph.facebook.com/v25.0/123456/messages')
        self.assertEqual(body['to'],'919558658907')
        self.assertEqual([c['parameters'][0]['text'] for c in body['template']['components']],['123456','123456'])

    def test_invalid_number_and_provider_failure_hide_details(self):
        for value in ['','abc','111','+01234567890']:
            with self.assertRaises(otp_delivery.DeliveryError):otp_delivery.recipient_number(value)
        opener=MagicMock();opener.open.side_effect=OSError('unit-test-token 123456 secret details')
        with patch.dict(os.environ,CONFIG),patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(otp_delivery.DeliveryError) as error:otp_delivery.send_otp('9558658907','123456')
        self.assertNotIn('unit-test-token',str(error.exception));self.assertNotIn('123456',str(error.exception))

del OperationsTests
