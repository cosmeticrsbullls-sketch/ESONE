import re
import unittest
from datetime import timedelta
from unittest.mock import patch, MagicMock
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, Visit, AuditLog, User, DocumentImport, SalesOrder, Client, PasswordReset
from modules.security import verify_password
from modules.workflows import now

class EnhancementTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login
    def csrf_form(self,path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        return re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
    def test_workspace_and_management_closure_preserve_evidence(self):
        self.login()
        self.assertIn('Sales',self.client.get('/workspace').text)
        with SessionLocal.begin() as db:
            db.get(Activity,6).status='IN_PROGRESS'
            visit=db.query(Visit).filter_by(activity_id=6).one();visit.check_in_at=now();visit.check_in_latitude=23;visit.check_in_longitude=72
        detail=self.client.get('/visits/6').text
        self.assertIn('google.com/maps/search/',detail)
        data=dict(csrf=self.csrf,reason='Customer OTP unavailable')
        closed=self.client.post('/visits/6/management-close',data=data,follow_redirects=False)
        self.assertEqual(closed.status_code,303);self.assertEqual(closed.headers['location'],'/workspace')
        self.assertEqual(self.client.post('/visits/6/management-close',data=data).status_code,409)
        with SessionLocal() as db:
            visit=db.query(Visit).filter_by(activity_id=6).one()
            self.assertIsNone(visit.check_out_at);self.assertEqual(visit.check_in_latitude,23)
            self.assertEqual(db.query(AuditLog).filter_by(action='MANAGEMENT_CLOSE').count(),1)
    def test_employee_cannot_override_and_inactive_session_revoked(self):
        self.login('a')
        self.assertEqual(self.client.post('/visits/6/management-close',data={'csrf':self.csrf,'reason':'Customer unavailable'}).status_code,403)
        with SessionLocal.begin() as db:db.get(User,2).is_active=False
        response=self.client.get('/workspace',follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertEqual(response.headers['location'],'/login')
    def test_change_password_and_csrf(self):
        self.login('a');csrf=self.csrf_form('/account/password')
        data=dict(csrf=csrf,current_password='Test-only-password-123',new_password='New-test-password-123',confirm_password='New-test-password-123')
        self.assertEqual(self.client.post('/account/password',data={**data,'csrf':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/account/password',data=data,follow_redirects=False).status_code,303)
        with SessionLocal() as db:self.assertTrue(verify_password(data['new_password'],db.get(User,2).password_hash))
    def upload(self):
        csrf=self.csrf_form('/imports')
        with patch('modules.document_import.extract_document',return_value=('Invoice No: INV-TEST\nGrand Total 1250.00','application/pdf')):
            response=self.client.post('/imports',data={'csrf':csrf,'kind':'BILL'},files={'document':('invoice.pdf',b'%PDF-test','application/pdf')},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        return response.headers['location']
    def test_import_review_atomic_duplicate_and_original(self):
        self.login();location=self.upload()
        with SessionLocal() as db:self.assertEqual(db.query(SalesOrder).count(),0)
        self.assertEqual(self.upload(),location)
        csrf=self.csrf_form(location)
        data=dict(csrf=csrf,client_id=1,reference='INV-TEST',document_date='2026-10-01',amount='1250.00',details='Checked line items and tax',confirmed='yes',adjust_balance='yes')
        self.assertEqual(self.client.post(location,data={**data,'amount':'NaN'}).status_code,400)
        for _ in range(2):self.assertEqual(self.client.post(location,data=data,follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.query(SalesOrder).count(),1)
            self.assertEqual(db.get(Client,1).outstanding_amount,1250)
            self.assertEqual(db.query(DocumentImport).one().status,'CONFIRMED')
        self.assertEqual(self.client.get(location+'/original').content,b'%PDF-test')
    def test_email_reset_is_single_use(self):
        config={'SMTP_HOST':'smtp.example.test','SMTP_USERNAME':'test','SMTP_PASSWORD':'test','SMTP_FROM':'test@example.test','ESONE_PUBLIC_URL':'https://esone.example.test'}
        with patch('modules.account_recovery.mail_settings',return_value=config),patch('modules.account_recovery.smtplib.SMTP') as smtp:
            csrf=self.csrf_form('/forgot-password')
            response=self.client.post('/forgot-password',data={'csrf':csrf,'email':'manager@example.test'})
            self.assertEqual(response.status_code,200)
            message=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            raw=re.search(r'token=([^\s]+)',message.get_content())[1]
        csrf=self.csrf_form('/reset-password?token='+raw)
        data=dict(csrf=csrf,token=raw,password='Reset-test-password-123',confirm='Reset-test-password-123')
        self.assertEqual(self.client.post('/reset-password',data=data,follow_redirects=False).status_code,303)
        data['csrf']=self.csrf_form('/reset-password?token='+raw)
        self.assertEqual(self.client.post('/reset-password',data=data).status_code,400)
        with SessionLocal() as db:self.assertIsNotNone(db.query(PasswordReset).one().used_at)
    def test_reviewed_invoice_items_and_received_amount_are_preserved(self):
        import json
        self.login();location=self.upload();csrf=self.csrf_form(location)
        data=dict(csrf=csrf,client_id=1,reference='INV-PARTIAL',document_date='2026-10-01',due_date='2026-11-01',amount='1250.00',received='50.00',payment_mode='Cash',confirmed='yes',adjust_balance='yes',item_name=['Test shampoo'],item_mrp=['1500.00'],item_quantity=['1'],item_unit=['Pcs'],item_rate=['1250.00'],item_amount=['1250.00'])
        self.assertEqual(self.client.post(location,data={**data,'received':'1300.00'}).status_code,400)
        self.assertEqual(self.client.post(location,data=data,follow_redirects=False).status_code,303)
        from database.models import CollectionActivity
        with SessionLocal() as db:
            self.assertEqual(db.get(Client,1).outstanding_amount,1200)
            receipt=db.query(CollectionActivity).filter_by(payment_reference='IMPORT-1-RECEIVED').one()
            self.assertEqual(receipt.amount_received,50)
            metadata=json.loads(db.query(DocumentImport).one().reviewed_data)
            self.assertEqual(metadata['items'][0]['name'],'Test shampoo')
            self.assertEqual(metadata['due_date'],'2026-11-01')
