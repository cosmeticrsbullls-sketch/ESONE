import base64
import re
import secrets
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import EmployeeDevice, VisitCameraChallenge, VisitPhoto, Activity, Client, Visit, AuditLog
from main import app


def photo_form(test, client_id=1, lat=23, lon=72):
    response=test.client.post('/visit-camera/challenge',data={'csrf':test.csrf,'client_id':client_id,'latitude':lat,'longitude':lon,'accuracy':12})
    test.assertEqual(response.status_code,200,response.text)
    img=Image.new('RGB',(320,240),color=tuple(secrets.randbelow(255) for _ in range(3)))
    buf=BytesIO();img.save(buf,format='JPEG')
    return {'csrf':test.csrf,'submission':secrets.token_urlsafe(24),'client_id':client_id,'latitude':lat,'longitude':lon,'visit_type':'SALES','notes':'Discussed shampoo, follow up next week','photo_nonce':response.json()['nonce'],'photo_data':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}


class DeviceCameraTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    punch_in_for_test=OperationsTests.punch_in_for_test
    login=OperationsTests.login

    def test_new_device_is_pending_and_blocks_get_and_post(self):
        response=self.client.post('/login',data={'email':'a@example.test','password':'Test-only-password-123'},follow_redirects=False)
        self.assertEqual(response.headers['location'],'/device-access')
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        for path in ['/workspace','/field/start','/attendance']:
            result=self.client.request('POST' if path!='/workspace' else 'GET',path,follow_redirects=False)
            self.assertEqual(result.headers.get('location'),'/device-access')
        self.assertIn('PENDING',self.client.get('/device-access').text)
        with SessionLocal() as db:
            self.assertEqual(db.query(EmployeeDevice).one().status,'PENDING')
            self.assertEqual(db.query(Activity).count(),6)

    def test_approval_csrf_privilege_replacement_and_old_session_revocation(self):
        self.login('a');old=TestClient(app);old.cookies.update(self.client.cookies)
        other=TestClient(app)
        try:
            other.post('/login',data={'email':'a@example.test','password':'Test-only-password-123'})
            with SessionLocal() as db:new=db.query(EmployeeDevice).order_by(EmployeeDevice.id.desc()).first().id
            self.assertEqual(self.client.post(f'/command-center/devices/{new}',data={'csrf':self.csrf,'decision':'APPROVE'}).status_code,403)
            self.login()
            self.assertEqual(self.client.post(f'/command-center/devices/{new}',data={'decision':'APPROVE'}).status_code,403)
            self.assertEqual(self.client.post(f'/command-center/devices/{new}',data={'csrf':self.csrf,'decision':'APPROVE'},follow_redirects=False).status_code,303)
            self.assertEqual(other.get('/workspace').status_code,200)
            denied=old.get('/workspace',follow_redirects=False)
            self.assertEqual(denied.headers['location'],'/device-access')
            with SessionLocal() as db:
                self.assertEqual(db.query(EmployeeDevice).filter_by(user_id=2,status='APPROVED').count(),1)
        finally:old.close();other.close()

    def test_session_alone_cannot_use_another_browser_and_self_approval_denied(self):
        self.login();device_only=TestClient(app)
        try:
            device_only.cookies.set('session',self.client.cookies.get('session'))
            self.assertEqual(device_only.get('/workspace',follow_redirects=False).headers['location'],'/device-access')
            with SessionLocal() as db:own=db.query(EmployeeDevice).filter_by(user_id=1).one().id
            response=self.client.post(f'/command-center/devices/{own}',data={'csrf':self.csrf,'decision':'REVOKE'})
            self.assertEqual(response.status_code,403)
        finally:device_only.close()

    def test_finish_creates_completed_visit_photo_and_maps_once_then_home(self):
        self.login('a');self.punch_in_for_test()
        data=photo_form(self)
        first=self.client.post('/field/start',data=data)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['redirect'],'/workspace')
        second=self.client.post('/field/start',data=data)
        self.assertEqual(second.json()['redirect'],'/workspace')
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),7)
            a=db.query(Activity).order_by(Activity.id.desc()).first();aid=a.id
            self.assertEqual((a.status,a.source,a.notes),('COMPLETED','FIELD_FORM',data['notes']))
            self.assertIsNotNone(a.completed_at)
            self.assertEqual(db.get(Client,1).latitude,23)
            v=db.query(Visit).filter_by(activity_id=aid).one();self.assertIsNone(v.check_out_at)
            photo=db.query(VisitPhoto).one();self.assertEqual((photo.activity_id,photo.user_id,photo.accuracy),(aid,2,12))
            self.assertTrue(photo.jpeg.startswith(b'\xff\xd8'))
            self.assertIsNotNone(db.query(VisitCameraChallenge).one().used_at)
        self.assertIn('Visit recorded successfully',self.client.get('/workspace').text)
        self.assertIn('View salon photo',self.client.get(f'/visits/{aid}').text)
        with SessionLocal.begin() as db:
            db.query(VisitPhoto).one().received_at=datetime(2026,11,20,10,37,39,674993)
        shared=self.client.get(f'/activities/{aid}/share').text
        self.assertIn('Recorded (IST): 20 Nov 2026, 04:07:39 PM IST',shared)
        self.assertNotIn('Recorded (UTC)',shared)
        with SessionLocal() as db:
            self.assertEqual(db.query(VisitPhoto).one().received_at,datetime(2026,11,20,10,37,39,674993))
        image=self.client.get(f'/activities/{aid}/photo');self.assertEqual(image.status_code,200)
        self.assertIn('no-store',image.headers['cache-control'])
        self.login('b');self.assertEqual(self.client.get(f'/activities/{aid}/photo').status_code,404)
        self.login();self.assertEqual(self.client.get(f'/activities/{aid}/photo').status_code,200)
        employees=self.client.get('/live-activity/data').json()['employees']
        employee=next(person for person in employees if person['id']==2)
        self.assertEqual(employee['today_visits'],1)
        self.assertEqual(employee['activity_id'],aid)
        self.assertIn('Last recorded',employee['activity'])
        self.assertEqual(employee['location']['source'],'Visit recorded')

    def test_missing_invalid_expired_and_wrong_business_photo_roll_back(self):
        self.login('a');self.punch_in_for_test();data=photo_form(self)
        for changes,expected in [({'photo_nonce':''},409),({'photo_data':'data:image/jpeg;base64,bm90IGFuIGltYWdl'},400),({'client_id':2},409),({'latitude':23.0001},409),({'notes':''},400),({'csrf':''},403)]:
            r=self.client.post('/field/start',data={**data,**changes});self.assertEqual(r.status_code,expected,r.text)
        with SessionLocal.begin() as db:db.query(VisitCameraChallenge).one().expires_at=datetime.utcnow()-timedelta(seconds=1)
        self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),6);self.assertEqual(db.query(VisitPhoto).count(),0)
            self.assertIsNone(db.get(Client,1).latitude)

    def test_used_photo_and_nonce_are_rejected_on_new_submission(self):
        self.login('a');self.punch_in_for_test();data=photo_form(self)
        self.assertEqual(self.client.post('/field/start',data=data).status_code,200)
        self.assertEqual(self.client.post('/field/start',data={**data,'submission':secrets.token_urlsafe(24)}).status_code,409)
        fresh=photo_form(self);fresh['photo_data']=data['photo_data']
        self.assertEqual(self.client.post('/field/start',data=fresh).status_code,409)
        with SessionLocal() as db:self.assertEqual(db.query(VisitPhoto).count(),1)

    def test_off_duty_bad_accuracy_and_wrong_gps_are_blocked(self):
        self.login('a')
        body={'csrf':self.csrf,'client_id':1,'latitude':23,'longitude':72,'accuracy':10}
        self.assertEqual(self.client.post('/visit-camera/challenge',data=body).status_code,409)
        self.punch_in_for_test()
        self.assertEqual(self.client.post('/visit-camera/challenge',data={**body,'accuracy':201}).status_code,400)
        data=photo_form(self)
        with SessionLocal.begin() as db:c=db.get(Client,1);c.latitude=24;c.longitude=72
        r=self.client.post('/field/start',data=data);self.assertEqual(r.status_code,409);self.assertIn('Location mismatch',r.text)
        with SessionLocal() as db:self.assertEqual(db.query(VisitPhoto).count(),0)

    def test_single_form_no_gallery_no_legacy_start_or_inline_registration(self):
        self.login('a');self.punch_in_for_test()
        text=self.client.get('/field/intake').text
        self.assertIn('>Finish</button>',text);self.assertIn('data-camera-capture',text)
        self.assertNotIn('type="file"',text);self.assertNotIn('name="business_name"',text)
        script=self.client.get('/visit-camera.js').text
        self.assertIn('getUserMedia',script);self.assertIn('maximumAge:0',script)
        self.assertEqual(self.client.post('/visits/6/start').status_code,410)
        data=photo_form(self);data['client_id']=''
        self.assertEqual(self.client.post('/field/start',data=data).status_code,400)

    def test_super_admin_bootstrap_and_html_preserves_session_and_device_cookies(self):
        from database.models import User
        from modules.security import hash_password
        with SessionLocal.begin() as db:
            db.add(User(full_name='Root',email='root@example.test',role='SUPER_ADMIN',password_hash=hash_password('Test-only-password-123')))
        result=self.client.post('/login',data={'email':'root@example.test','password':'Test-only-password-123'},follow_redirects=False)
        self.assertEqual(result.headers['location'],'/permissions')
        result=self.client.get('/device-access')
        self.assertEqual(len(result.headers.get_list('set-cookie')),2)
        self.assertEqual(self.client.get('/command-center/devices').status_code,200)
        with SessionLocal() as db:self.assertEqual(db.query(AuditLog).filter_by(action='DEVICE_BOOTSTRAP').count(),1)

    def test_super_admin_keeps_multiple_browsers_and_manual_revocation(self):
        from database.models import User
        from modules.security import hash_password
        with SessionLocal.begin() as db:
            root=User(full_name='Root',email='root@example.test',role='SUPER_ADMIN',password_hash=hash_password('Test-only-password-123'))
            db.add(root); db.flush(); root_id=root.id
        other=TestClient(app)
        try:
            for browser in (self.client,other):
                response=browser.post('/login',data={'email':'root@example.test','password':'Test-only-password-123'},follow_redirects=False)
                self.assertEqual(response.headers['location'],'/permissions')
            self.assertEqual(self.client.get('/command-center/devices').status_code,200)
            self.assertEqual(other.get('/command-center/devices').status_code,200)
            with SessionLocal.begin() as db:
                devices=db.query(EmployeeDevice).filter_by(user_id=root_id).order_by(EmployeeDevice.id).all()
                self.assertEqual([d.status for d in devices],['APPROVED','APPROVED'])
                devices[0].status='REVOKED'
                db.add(AuditLog(user_id=root_id,entity_type='EmployeeDevice',entity_id=devices[0].id,action='DEVICE_REVOKE',new_value='Super Admin bootstrap on replacement browser'))
            self.assertIn('APPROVED',self.client.get('/device-access').text)
            with SessionLocal.begin() as db:
                first=db.query(EmployeeDevice).filter_by(user_id=root_id).order_by(EmployeeDevice.id).first()
                first.status='REVOKED'
                db.add(AuditLog(user_id=root_id,entity_type='EmployeeDevice',entity_id=first.id,action='DEVICE_REVOKE',new_value='REVOKED'))
            self.assertIn('REVOKED',self.client.get('/device-access').text)
        finally: other.close()

    def test_another_employee_cannot_reuse_camera_challenge(self):
        self.login('a');self.punch_in_for_test(2,3);data=photo_form(self)
        self.login('b');data['csrf']=self.csrf
        self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),6)
            self.assertEqual(db.query(VisitPhoto).count(),0)

    def test_rejected_device_can_request_again_but_stays_blocked(self):
        self.client.post('/login',data={'email':'a@example.test','password':'Test-only-password-123'})
        pending=TestClient(app);pending.cookies.update(self.client.cookies)
        try:
            page=pending.get('/device-access').text
            with SessionLocal() as db:identity=db.query(EmployeeDevice).one().id
            self.login()
            self.assertEqual(self.client.post(f'/command-center/devices/{identity}',data={'csrf':self.csrf,'decision':'REJECT'},follow_redirects=False).status_code,303)
            page=pending.get('/device-access').text
            csrf=re.search(r'name="csrf" value="([^"]+)"',page)[1]
            self.assertEqual(pending.post('/device-access/request',data={'csrf':''}).status_code,403)
            result=pending.post('/device-access/request',data={'csrf':csrf},follow_redirects=False)
            self.assertEqual(result.status_code,303)
            self.assertEqual(pending.get('/workspace',follow_redirects=False).headers['location'],'/device-access')
            with SessionLocal() as db:self.assertEqual(db.get(EmployeeDevice,identity).status,'PENDING')
        finally:pending.close()


del OperationsTests
