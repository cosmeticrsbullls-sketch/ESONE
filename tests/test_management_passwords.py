import re
import unittest
from datetime import timedelta
from fastapi.testclient import TestClient
from test_operations import OperationsTests
from main import app
from database.db import SessionLocal
from database.models import User,AuditLog,PasswordReset
from modules.security import verify_password
from modules.workflows import now

class ManagementPasswordTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login
    def data(self):
        response=self.client.get('/command-center/passwords/2')
        self.assertEqual(response.status_code,200)
        csrf=re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
        return dict(csrf=csrf,admin_password='Test-only-password-123',new_password='New-employee-password-123',confirm_password='New-employee-password-123',reason='FORGOT_PASSWORD',confirmed='yes')
    def test_reset_revokes_employee_sessions_and_records_no_secret(self):
        self.login()
        staff=TestClient(app)
        try:
            self.assertEqual(staff.post('/login',data={'email':'a@example.test','password':'Test-only-password-123'},follow_redirects=False).status_code,303)
            with SessionLocal.begin() as db:
                db.add(PasswordReset(user_id=2,token_hash='a'*64,password_fingerprint='b'*64,expires_at=now()+timedelta(minutes=30),created_at=now()))
            data=self.data()
            self.assertEqual(self.client.post('/command-center/passwords/2',data=data,follow_redirects=False).status_code,303)
            self.assertEqual(staff.get('/workspace',follow_redirects=False).status_code,303)
            self.assertEqual(staff.post('/login',data={'email':'a@example.test','password':data['new_password']},follow_redirects=False).status_code,303)
            with SessionLocal() as db:
                self.assertTrue(verify_password(data['new_password'],db.get(User,2).password_hash))
                record=db.query(AuditLog).filter_by(action='ADMIN_PASSWORD_RESET').one()
                self.assertEqual((record.user_id,record.entity_id),(1,2))
                self.assertNotIn(data['new_password'],record.new_value)
                self.assertNotIn(data['admin_password'],record.new_value)
                self.assertIsNotNone(db.query(PasswordReset).one().used_at)
        finally:staff.close()
    def test_wrong_admin_password_csrf_or_mismatch_do_not_write(self):
        self.login();data=self.data()
        for change,status in [({'admin_password':'wrong'},403),({'csrf':'wrong'},403),({'confirm_password':'different'},400),({'confirmed':''},400)]:
            self.assertEqual(self.client.post('/command-center/passwords/2',data={**data,**change}).status_code,status)
        with SessionLocal() as db:
            self.assertTrue(verify_password('Test-only-password-123',db.get(User,2).password_hash))
            self.assertEqual(db.query(AuditLog).filter_by(action='ADMIN_PASSWORD_RESET').count(),0)
    def test_staff_and_office_cannot_reset_and_management_cannot_reset_admins(self):
        self.login();data=self.data()
        with SessionLocal.begin() as db:db.get(User,3).role='MANAGEMENT'
        self.assertEqual(self.client.get('/command-center/passwords/3').status_code,403)
        self.assertEqual(self.client.get('/command-center/passwords/1').status_code,403)
        self.client.get('/logout');self.login('a')
        self.assertEqual(self.client.get('/command-center/passwords').status_code,403)
        self.assertEqual(self.client.post('/command-center/passwords/3',data=data).status_code,403)
        with SessionLocal.begin() as db:db.get(User,2).role='OFFICE'
        self.assertEqual(self.client.get('/command-center/passwords').status_code,403)
    def test_superadmin_has_a_command_center_entry(self):
        with SessionLocal.begin() as db:db.get(User,1).role='SUPER_ADMIN'
        self.login()
        self.assertIn('/command-center/passwords',self.client.get('/command-center').text)
        self.assertIn('/command-center/passwords/2',self.client.get('/users').text)
    def test_failed_admin_authentication_is_throttled(self):
        self.login();data=self.data()
        for _ in range(5):
            self.assertEqual(self.client.post('/command-center/passwords/2',data={**data,'admin_password':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/command-center/passwords/2',data=data).status_code,429)
        with SessionLocal() as db:
            self.assertTrue(verify_password('Test-only-password-123',db.get(User,2).password_hash))
            self.assertEqual(db.query(AuditLog).filter_by(action='ADMIN_PASSWORD_RESET_DENIED').count(),5)
    def test_success_message_cannot_be_faked_by_query_parameter(self):
        self.login()
        response=self.client.get('/command-center/passwords/2?done=1')
        self.assertIn('name="new_password"',response.text)
        self.assertNotIn('The password was reset',response.text)
