import base64
import unittest
import re
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from fastapi import HTTPException
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import WebPushSubscription,WebPushDelivery,EmployeeDevice
from modules.web_push import valid_subscription,keys,dispatch,b64
from modules.workflows import now

class WebPushTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    _base_login=OperationsTests.login
    def login(self,who='manager'):
        self._base_login(who)
        self.csrf=re.search(r'name="csrf" value="([^"]+)"',self.client.get('/permissions').text)[1]

    def subscription(self,endpoint='https://fcm.googleapis.com/fcm/send/test-only'):
        public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        return {'endpoint':endpoint,'keys':{'p256dh':b64(public),'auth':b64(b'1234567890123456')}}

    def test_setup_and_key_are_private_and_stable(self):
        self.assertEqual(self.client.get('/permissions',follow_redirects=False).status_code,303)
        self.login('a')
        page=self.client.get('/permissions');self.assertEqual(page.status_code,200)
        for label in ['Enable Location','Enable Camera','Enable Notifications','Send Test Notification','Skip for now']:
            self.assertIn(label,page.text)
        with SessionLocal.begin() as db:
            key=keys(db);private=key.private_key;public=key.public_key
            self.assertEqual(keys(db).public_key,public)
            self.assertNotIn(private,page.text)
            Vapid.from_string(private)
        worker=self.client.get('/assets/push-worker.js')
        self.assertEqual(worker.headers['service-worker-allowed'],'/')
        self.assertNotIn('caches.',worker.text)

    def test_subscribe_test_csrf_logout_and_revocation(self):
        self.login('a');data={'csrf':self.csrf,'subscription':self.subscription()}
        self.assertEqual(self.client.post('/push/subscribe',json={**data,'csrf':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/push/subscribe',json=data).status_code,200)
        self.assertEqual(self.client.post('/push/subscribe',json=data).status_code,200)
        with SessionLocal() as db:self.assertEqual(db.query(WebPushSubscription).count(),1)
        with patch('pywebpush.webpush') as sender:
            self.assertEqual(self.client.post('/push/test',json={'csrf':self.csrf}).status_code,200)
            self.assertEqual(sender.call_count,1)
            self.assertEqual(self.client.post('/push/test',json={'csrf':self.csrf}).status_code,429)
        self.client.get('/logout')
        with SessionLocal() as db:self.assertFalse(db.query(WebPushSubscription).one().enabled)

    def test_unsubscribe_and_foreign_subscription_are_rejected(self):
        self.login('a');data={'csrf':self.csrf,'subscription':self.subscription()}
        self.assertEqual(self.client.post('/push/subscribe',json=data).status_code,200)
        from fastapi.testclient import TestClient
        other=TestClient(__import__('main').app)
        try:
            other.post('/login',data={'email':'b@example.test','password':'Test-only-password-123'})
            with SessionLocal.begin() as db:
                db.query(EmployeeDevice).filter_by(user_id=3).one().status='APPROVED'
            csrf=re.search(r'name="csrf" value="([^"]+)"',other.get('/permissions').text)[1]
            self.assertEqual(other.post('/push/subscribe',json={**data,'csrf':csrf}).status_code,409)
        finally:other.close()
        self.login('a');self.assertEqual(self.client.post('/push/unsubscribe',json={'csrf':self.csrf}).status_code,200)
        with SessionLocal() as db:self.assertFalse(db.query(WebPushSubscription).one().enabled)

    def test_invalid_endpoints_and_keys_do_not_send_requests(self):
        for endpoint in ['http://fcm.googleapis.com/x','https://localhost/x','https://fcm.googleapis.com.evil.test/x','https://fcm.googleapis.com:8443/x','https://x@fcm.googleapis.com/x']:
            with self.assertRaises(HTTPException):valid_subscription(self.subscription(endpoint))
        data=self.subscription();data['keys']['auth']='bad'
        with self.assertRaises(HTTPException):valid_subscription(data)

    def test_dispatch_dedup_failure_retry_and_device_revoke(self):
        self.login('a');self.client.post('/push/subscribe',json={'csrf':self.csrf,'subscription':self.subscription()})
        with SessionLocal.begin() as db:db.query(WebPushSubscription).one().created_at=now()-timedelta(minutes=1)
        stamp=now();events=[('Test update','/notifications',stamp)]
        with patch('modules.notifications.inbox',return_value=events),patch('pywebpush.webpush') as sender:
            dispatch();dispatch();self.assertEqual(sender.call_count,1)
        with SessionLocal.begin() as db:
            row=db.query(WebPushSubscription).one();db.get(EmployeeDevice,row.device_id).status='REVOKED'
        with patch('modules.notifications.inbox',return_value=[('Another update','/notifications',now())]),patch('pywebpush.webpush') as sender:
            dispatch();sender.assert_not_called()
        with SessionLocal() as db:self.assertEqual(db.query(WebPushDelivery).count(),1)

    def test_transient_failure_retries_without_duplicate_immediate_sends(self):
        from pywebpush import WebPushException
        self.login('a');self.client.post('/push/subscribe',json={'csrf':self.csrf,'subscription':self.subscription()})
        with SessionLocal.begin() as db:db.query(WebPushSubscription).one().created_at=now()-timedelta(minutes=1)
        events=[('Retry test','/notifications',now())]
        with patch('modules.notifications.inbox',return_value=events),patch('pywebpush.webpush',side_effect=WebPushException('temporary',response=SimpleNamespace(status_code=503))) as sender:
            dispatch();dispatch();self.assertEqual(sender.call_count,1)
        with SessionLocal.begin() as db:
            item=db.query(WebPushDelivery).one();self.assertFalse(item.delivered);item.retry_at=now()-timedelta(seconds=1)
        with patch('modules.notifications.inbox',return_value=events),patch('pywebpush.webpush') as sender:
            dispatch();self.assertEqual(sender.call_count,1)
        with SessionLocal() as db:self.assertTrue(db.query(WebPushDelivery).one().delivered)

    def test_account_switch_and_password_reset_stop_push(self):
        from database.models import User
        self.login('a');self.client.post('/push/subscribe',json={'csrf':self.csrf,'subscription':self.subscription()})
        self.login('b')
        with SessionLocal() as db:self.assertFalse(db.query(WebPushSubscription).one().enabled)
        self.login('a');self.client.post('/push/subscribe',json={'csrf':self.csrf,'subscription':self.subscription()})
        with SessionLocal.begin() as db:
            db.get(User,2).password_hash='changed-password-hash'
        with patch('pywebpush.webpush') as sender:dispatch();sender.assert_not_called()
        with SessionLocal() as db:self.assertFalse(db.query(WebPushSubscription).one().enabled)

    def test_expired_subscription_is_disabled(self):
        from pywebpush import WebPushException
        self.login('a');self.client.post('/push/subscribe',json={'csrf':self.csrf,'subscription':self.subscription()})
        with patch('pywebpush.webpush',side_effect=WebPushException('expired',response=SimpleNamespace(status_code=410))):
            self.assertEqual(self.client.post('/push/test',json={'csrf':self.csrf}).status_code,503)
        with SessionLocal() as db:self.assertFalse(db.query(WebPushSubscription).one().enabled)

del OperationsTests
