"""Account creation must require the current admin session's CSRF token."""
import re
import unittest
from fastapi.testclient import TestClient
from tests.test_operations import OperationsTests
from main import app
from database.db import SessionLocal
from database.models import User
from modules.security import verify_password


class UserCreationCsrfTests(unittest.TestCase):
    setUpClass = classmethod(OperationsTests.setUpClass.__func__)
    setUp = OperationsTests.setUp
    tearDown = OperationsTests.tearDown
    login = OperationsTests.login

    def admin(self):
        with SessionLocal.begin() as db:
            db.get(User, 1).role = 'SUPER_ADMIN'
        self.login()

    def form_token(self, client=None):
        response = (client or self.client).get('/users')
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]

    def payload(self, **extra):
        return dict(full_name='CSRF Test Employee', email='csrf-employee@example.test',
                    password='Test-only-password-123', role='SALES', **extra)

    def assert_no_employee(self):
        with SessionLocal() as db:
            self.assertEqual(db.query(User).count(), 3)

    def test_current_admin_token_creates_login_capable_employee(self):
        self.admin()
        response = self.client.post('/users/create', data=self.payload(csrf=self.form_token()), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/users')
        with SessionLocal() as db:
            employee = db.query(User).filter_by(email='csrf-employee@example.test').one()
            self.assertEqual(employee.role, 'SALES')
            self.assertTrue(verify_password('Test-only-password-123', employee.password_hash))
        with TestClient(app) as employee_client:
            self.assertEqual(employee_client.post('/login', data={'email':'csrf-employee@example.test', 'password':'Test-only-password-123'}, follow_redirects=False).status_code, 303)

    def test_missing_blank_and_wrong_tokens_do_not_create_employee(self):
        self.admin()
        self.form_token()
        for extra in [{}, {'csrf':''}, {'csrf':'wrong-token'}, {'csrf':'ખોટો-token'}]:
            with self.subTest(extra=extra):
                response = self.client.post('/users/create', data=self.payload(**extra))
                self.assertEqual(response.status_code, 403)
                self.assert_no_employee()

    def test_token_from_another_admin_session_is_rejected(self):
        self.admin()
        own = self.form_token()
        with TestClient(app) as other:
            self.assertEqual(other.post('/login', data={'email':'manager@example.test','password':'Test-only-password-123'}, follow_redirects=False).status_code, 303)
            foreign = self.form_token(other)
        self.assertNotEqual(own, foreign)
        self.assertEqual(self.client.post('/users/create', data=self.payload(csrf=foreign)).status_code, 403)
        self.assert_no_employee()

    def test_relogin_invalidates_old_form_token(self):
        self.admin()
        old = self.form_token()
        self.client.get('/logout')
        self.login()
        self.assertNotEqual(old, self.form_token())
        self.assertEqual(self.client.post('/users/create', data=self.payload(csrf=old)).status_code, 403)
        self.assert_no_employee()

    def test_staff_and_management_cannot_create_users_even_with_valid_token(self):
        for who in ['a', 'manager']:
            with self.subTest(who=who):
                self.login(who)
                self.assertEqual(self.client.get('/users').status_code, 403)
                self.assertEqual(self.client.post('/users/create', data=self.payload(csrf=self.csrf)).status_code, 403)
                self.assert_no_employee()

    def test_unauthenticated_request_redirects_without_creating_employee(self):
        response = self.client.post('/users/create', data=self.payload(csrf='irrelevant'), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/')
        self.assert_no_employee()


del OperationsTests
