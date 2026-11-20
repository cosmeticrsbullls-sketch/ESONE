import re
import unittest
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import User,UserAccessPolicy,EmployeeDevice,Activity,AuditLog,WebPushSubscription

MOBILE='Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Mobile Safari/537.36'
WEB='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0'

class AccessPolicyTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def policy(self,uid,kind):
        with SessionLocal.begin() as db:db.add(UserAccessPolicy(user_id=uid,access_type=kind))

    def admin(self):
        with SessionLocal.begin() as db:db.get(User,1).role='SUPER_ADMIN'
        self.login()

    def test_mobile_and_web_login_restrictions(self):
        self.policy(2,'MOBILE');self.policy(3,'WEB')
        credentials=lambda email:{'email':email,'password':'Test-only-password-123'}
        self.assertEqual(self.client.post('/login',data=credentials('a@example.test'),headers={'user-agent':WEB},follow_redirects=False).status_code,403)
        self.assertEqual(self.client.post('/login',data=credentials('a@example.test'),headers={'user-agent':MOBILE},follow_redirects=False).status_code,303)
        self.client.get('/logout')
        self.assertEqual(self.client.post('/login',data=credentials('b@example.test'),headers={'user-agent':MOBILE},follow_redirects=False).status_code,403)
        self.assertEqual(self.client.post('/login',data=credentials('b@example.test'),headers={'user-agent':WEB},follow_redirects=False).status_code,303)

    def test_existing_session_cannot_bypass_device_type(self):
        self.login('a');self.policy(2,'MOBILE')
        response=self.client.get('/workspace',headers={'user-agent':WEB},follow_redirects=False)
        self.assertEqual(response.headers['location'],'/access-type-denied')
        denied=self.client.get('/access-type-denied',headers={'user-agent':WEB})
        self.assertEqual(denied.status_code,403);self.assertIn('Mobile Only',denied.text)
        self.assertEqual(self.client.get('/workspace',headers={'user-agent':MOBILE}).status_code,200)

    def test_permissions_follow_device_class_and_super_admin_skips(self):
        self.login('a')
        self.assertIn('data-field-required="false"',self.client.get('/permissions',headers={'user-agent':WEB}).text)
        self.assertIn('data-field-required="true"',self.client.get('/permissions',headers={'user-agent':MOBILE}).text)
        self.admin()
        for agent in [MOBILE,WEB]:
            result=self.client.get('/permissions',headers={'user-agent':agent},follow_redirects=False)
            self.assertEqual(result.status_code,303);self.assertEqual(result.headers['location'],'/workspace')
        self.assertIn('name="access_type" required',self.client.get('/users').text)

    def test_reset_device_preserves_employee_data_and_requires_confirmation(self):
        self.login('a');self.admin()
        url='/command-center/access/2/reset-device'
        with SessionLocal() as db:
            password=db.get(User,2).password_hash;count=db.query(Activity).count()
        with SessionLocal.begin() as db:
            device=db.query(EmployeeDevice).filter_by(user_id=2).first()
            db.add(WebPushSubscription(user_id=2,device_id=device.id,endpoint='https://fcm.googleapis.com/test',endpoint_hash='test-hash',p256dh='test-key',auth='test-auth',credential_fingerprint='test-fingerprint',enabled=True,created_at=__import__('datetime').datetime.now()))
        data={'csrf':self.csrf,'reason':'Phone replaced','confirmed':'yes'}
        self.assertEqual(self.client.post(url,data={**data,'confirmed':''}).status_code,400)
        self.assertEqual(self.client.post(url,data={**data,'csrf':'wrong'}).status_code,403)
        self.assertEqual(self.client.post(url,data=data,follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.get(User,2).password_hash,password)
            self.assertEqual(db.query(Activity).count(),count)
            self.assertTrue(all(d.status=='REVOKED' for d in db.query(EmployeeDevice).filter_by(user_id=2)))
            self.assertEqual(db.query(AuditLog).filter_by(action='ADMIN_DEVICE_RESET').count(),1)
            self.assertFalse(db.query(WebPushSubscription).one().enabled)
        self.assertEqual(self.client.post('/command-center/access/1/reset-device',data=data).status_code,403)

    def test_access_update_revokes_devices_and_is_super_admin_only(self):
        self.login('a');self.admin()
        data={'csrf':self.csrf,'access_type':'MOBILE','reason':'Field employee'}
        self.assertEqual(self.client.post('/command-center/access/2',data=data,follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.get(UserAccessPolicy,2).access_type,'MOBILE')
            self.assertTrue(all(d.status=='REVOKED' for d in db.query(EmployeeDevice).filter_by(user_id=2)))
        self.assertEqual(self.client.post('/command-center/access/1',data=data).status_code,403)
        self.login('b')
        self.assertEqual(self.client.post('/command-center/access/2',data={**data,'csrf':self.csrf}).status_code,403)

    def test_new_user_requires_explicit_access_type(self):
        self.admin()
        data={'csrf':self.csrf,'full_name':'New Employee','email':'new@example.test','password':'Test-only-password-123','role':'SALES'}
        self.assertEqual(self.client.post('/users/create',data=data).status_code,400)
        self.assertEqual(self.client.post('/users/create',data={**data,'access_type':'MOBILE'},follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            user=db.query(User).filter_by(email='new@example.test').one()
            self.assertEqual(db.get(UserAccessPolicy,user.id).access_type,'MOBILE')

del OperationsTests
