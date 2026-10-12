import os,re,unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from pypdf import PdfReader
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Attendance,EmployeeProfile,User,SalesOrder,OrderLine,Activity,AuditLog,DemoBooking,DemoEducator,CommunicationLog
from modules.catalog import CATALOG
from modules.otp_delivery import DeliveryError

class TeamOrderTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def form(self,url):
        r=self.client.get(url);self.assertEqual(r.status_code,200)
        return {k:re.search(r'name="'+k+r'" value="([^"]+)"',r.text)[1] for k in ['csrf']+(['submission'] if 'name="submission"' in r.text else [])}

    def order(self,**extra):
        d=self.form('/orders/new');d.update(client_id=1,**{'qty_ES-01':'2','discount_ES-01':'50','qty_ES-16':'3','discount_ES-16':'10'});d.update(extra);return d

    def test_gps_punch_state_csrf_duplicate_and_evidence(self):
        self.login('a');d=self.form('/attendance');d.update(action='IN',latitude=23,longitude=72,accuracy=12)
        for bad in [{'csrf':'bad'},{'latitude':'NaN'},{'accuracy':201}]:
            self.assertIn(self.client.post('/attendance',data={**d,**bad}).status_code,[400,403])
        r=self.client.post('/attendance',data=d,follow_redirects=False);self.assertEqual(r.headers['location'],'/workspace')
        self.assertEqual(self.client.post('/attendance',data=d).status_code,409)
        self.assertIn('query=23.0,72.0',self.client.get('/attendance').text)
        self.assertIn('Punch out pending',self.client.get('/notifications').text)
        d.update(action='OUT',latitude=24,longitude=73)
        self.assertEqual(self.client.post('/attendance',data=d,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post('/attendance',data=d).status_code,409)
        with SessionLocal() as db:
            p=db.query(Attendance).one();self.assertEqual(p.user_id,2);self.assertEqual(p.in_latitude,23);self.assertEqual(p.out_latitude,24);self.assertIsNotNone(p.punch_out_at)
            self.assertEqual(db.query(AuditLog).filter(AuditLog.action.in_(['PUNCH_IN','PUNCH_OUT'])).count(),2)

    def test_employee_profile_preserves_auth_and_sales_cannot_edit(self):
        self.login();d=self.form('/employees/2');d.update(employee_code='E002',phone='9999999999',designation='Sales Executive',base_city='Rajkot',joining_date='2026-10-05')
        self.assertEqual(self.client.post('/employees/2',data=d,follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            u=db.get(User,2);p=db.get(EmployeeProfile,2);self.assertEqual(u.role,'SALES');self.assertTrue(u.is_active);self.assertEqual(u.password_hash,self.password_hash);self.assertEqual(p.base_city,'Rajkot')
        self.assertEqual(self.client.post('/employees/3',data=d).status_code,409)
        self.client.get('/logout');self.login('a')
        self.assertEqual(self.client.get('/employees').status_code,403);self.assertEqual(self.client.post('/employees/2',data=d).status_code,403)

    def test_order_prices_16_skus_no_ledger_mutation_and_replay(self):
        self.login('a');self.assertEqual(len(CATALOG),16)
        html=self.client.get('/orders/new').text
        self.assertEqual(len(re.findall(r'name="qty_ES-',html)),16)
        d=self.order();r=self.client.post('/orders',data=d,follow_redirects=False);self.assertEqual(r.status_code,303);url=r.headers['location']
        self.assertEqual(self.client.post('/orders',data=d,follow_redirects=False).headers['location'],url)
        with SessionLocal() as db:
            o=db.query(SalesOrder).one();self.assertEqual(o.subtotal,Decimal(6395));self.assertEqual(o.total_amount,Decimal('4156.30'));self.assertEqual(db.query(OrderLine).count(),2)
            self.assertEqual(db.get(Activity,o.activity_id).created_by,2)
            from database.models import Client
            self.assertEqual(db.get(Client,1).outstanding_amount,0)
        pdf=self.client.get(url+'/pdf');self.assertEqual(pdf.status_code,200);text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages);self.assertIn('4156.30',text);self.assertIn('not tax invoice',text)
        self.client.get('/logout');self.login('b');self.assertEqual(self.client.get(url).status_code,404);self.assertEqual(self.client.get(url+'/pdf').status_code,404)

    def test_order_invalid_fields_and_unconnected_whatsapp(self):
        self.login('a')
        for bad in [{'qty_ES-01':'1.5'},{'discount_ES-01':'101'},{'discount_ES-01':'NaN'},{'discount_ES-01':'0.001'},{'qty_ES-01':'-2'},{'csrf':'bad'}]:
            self.assertIn(self.client.post('/orders',data=self.order(**bad)).status_code,[400,403])
        with SessionLocal() as db:self.assertEqual(db.query(SalesOrder).count(),0)
        r=self.client.post('/orders',data=self.order(),follow_redirects=False);url=r.headers['location'];d=self.form(url)
        with patch('modules.order_delivery.send_confirmation',side_effect=DeliveryError('Not connected')):
            self.assertEqual(self.client.post(url+'/send',data=d,follow_redirects=False).status_code,303)
        with SessionLocal() as db:self.assertEqual(db.query(CommunicationLog).one().status,'FAILED')
        self.assertEqual(self.client.post(url+'/send',data=d).status_code,429)

    def test_sales_demo_free_name_edit_availability_and_owner(self):
        self.login('a');d=self.form('/demos/new');scheduled=datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)
        d.update(client_id=1,educator_name='Guest Educator',educator_id=0,treatment='NanoBeen',demo_at=scheduled.strftime('%Y-%m-%dT%H:%M'))
        r=self.client.post('/demos',data=d,follow_redirects=False);self.assertEqual(r.status_code,303);url=r.headers['location']
        self.assertIn('Guest Educator',self.client.get(url).text)
        available=self.client.get('/demo-availability?day='+str(scheduled.date())).json();self.assertEqual(len(available['bookings']),1);self.assertEqual(available['bookings'][0]['educator'],'Guest Educator')
        self.assertIn('Guest Educator',self.client.get('/demos/new?demo_day='+str(scheduled.date())).text)
        edit=self.form(url);edit.update(educator_name='Edited Educator')
        self.assertEqual(self.client.post(url+'/educator',data=edit,follow_redirects=False).status_code,303)
        self.assertIn('Edited Educator',self.client.get(url).text)
        self.client.get('/logout');self.login('b');self.assertEqual(self.client.get(url).status_code,403)
        edit['csrf']=self.form('/demos/new')['csrf'];self.assertEqual(self.client.post(url+'/educator',data=edit).status_code,403)
        self.assertEqual(self.client.post(url,data={**edit,'action':'CANCEL','notes':'Cancel'}).status_code,403)

    def test_notifications_and_employee_pdf_scope_dates(self):
        self.login('a');self.client.post('/orders',data=self.order(),follow_redirects=False)
        self.assertIn('ORDER',self.client.get('/notifications').text)
        self.assertIn('Book Order',self.client.get('/workspace').text)
        self.assertIn('Main menu',self.client.get('/workspace').text)
        self.assertEqual(self.client.get('/activity-reports/pdf?employee_id=3').status_code,403)
        pdf=self.client.get('/activity-reports/pdf');self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.content.startswith(b'%PDF'));self.assertIn('ORDER',''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages))
        self.assertEqual(self.client.get('/activity-reports?period=monthly&month=bad').status_code,400)
        self.assertEqual(self.client.get('/activity-reports/pdf?start=2025-01-01&end=2026-12-01').status_code,400)
        self.client.get('/logout');self.login();self.assertIn('Employee',self.client.get('/activity-reports').text)
        self.assertTrue(self.client.get('/reports/pdf?kind=visits').content.startswith(b'%PDF'))

    def test_sales_register_salon_returns_to_order_without_privilege_change(self):
        self.login('a');d=self.form('/salons/new?return_to=/orders/new');d.update(business_name='New Salon',phone='1234567890',return_to='/orders/new')
        r=self.client.post('/salons/new',data=d,follow_redirects=False);self.assertRegex(r.headers['location'],r'^/orders/new\?client_id=\d+$')
        self.assertEqual(self.client.post('/salons/new',data=d,follow_redirects=False).headers['location'],r.headers['location'])
        from database.models import Client
        with SessionLocal() as db:self.assertEqual(db.query(Client).filter_by(business_name='New Salon').count(),1)

del OperationsTests
