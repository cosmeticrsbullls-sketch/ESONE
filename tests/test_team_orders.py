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
    punch_in_for_test=OperationsTests.punch_in_for_test
    _base_login=OperationsTests.login
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login
    workbook=OperationsTests.workbook

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
        self.punch_in_for_test(2,3)
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
        self.punch_in_for_test(2,3)
        self.login('a')
        for bad in [{'qty_ES-01':'1.5'},{'discount_ES-01':'101'},{'discount_ES-01':'NaN'},{'discount_ES-01':'0.001'},{'qty_ES-01':'-2'},{'csrf':'bad'}]:
            self.assertIn(self.client.post('/orders',data=self.order(**bad)).status_code,[400,403])
        with SessionLocal() as db:self.assertEqual(db.query(SalesOrder).count(),0)
        r=self.client.post('/orders',data=self.order(),follow_redirects=False);url=r.headers['location'];d={'csrf':self.form('/orders/new')['csrf']}
        detail=self.client.get(url).text
        self.assertRegex(detail,r'class="share-pdf"[^>]*>Share</button>')
        self.assertNotIn('Send Order via connected WhatsApp',detail)
        self.assertNotIn('Share PDF to WhatsApp',detail)
        with patch('modules.order_delivery.send_confirmation',side_effect=DeliveryError('Not connected')):
            self.assertEqual(self.client.post(url+'/send',data=d,follow_redirects=False).status_code,303)
        with SessionLocal() as db:self.assertEqual(db.query(CommunicationLog).one().status,'FAILED')
        self.assertEqual(self.client.post(url+'/send',data=d).status_code,429)

    def test_sales_demo_free_name_edit_availability_and_owner(self):
        self.punch_in_for_test(2,3)
        self.login('a');d=self.form('/demos/new');scheduled=datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)
        d.update(client_id=1,educator_name='Guest Educator',educator_id=0,treatment='NanoBeen',demo_at=scheduled.strftime('%Y-%m-%dT%H:%M'))
        response = self.client.post('/demos', data=d, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/demo-requests')
        self.assertIn('Pending approval', self.client.get('/demo-requests').text)
        self.assertEqual(self.client.post('/demos', data=d).status_code, 409)

        review_url = '/command-center/demo-requests/1'
        availability_url = '/demo-availability?day=' + str(scheduled.date())
        self.client.get('/logout')
        self.login('b')
        self.assertNotIn('Guest Educator', self.client.get('/demo-requests').text)
        self.assertEqual(self.client.get(availability_url).json()['bookings'], [])
        self.assertEqual(self.client.get('/command-center/demo-requests').status_code, 403)
        csrf = self.form('/demos/new')['csrf']
        self.assertEqual(self.client.post(review_url, data={'csrf': csrf, 'decision': 'APPROVED'}).status_code, 403)

        self.client.get('/logout')
        self.login()
        queue = '/command-center/demo-requests'
        self.assertIn('Guest Educator', self.client.get(queue).text)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=demos'))), 1)
        review = {'csrf': self.form(queue)['csrf'], 'decision': 'APPROVED'}
        self.assertEqual(self.client.post(review_url, data={**review, 'csrf': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.post(review_url, data=review, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.post(review_url, data=review).status_code, 409)

        self.client.get('/logout')
        self.login('a')
        tracking = self.client.get('/demo-requests').text
        self.assertIn('Approved', tracking)
        booking_link = re.search(r'href="(/demos/\d+)"', tracking)
        self.assertIsNotNone(booking_link)
        url = booking_link.group(1)
        self.assertIn('Guest Educator',self.client.get(url).text)
        available=self.client.get('/demo-availability?day='+str(scheduled.date())).json();self.assertEqual(len(available['bookings']),1);self.assertEqual(available['bookings'][0]['educator'],'Guest Educator')
        self.assertIn('Guest Educator',self.client.get('/demos/new?demo_day='+str(scheduled.date())).text)
        edit=self.form(url);edit.update(educator_name='Edited Educator')
        self.assertEqual(self.client.post(url+'/educator',data=edit,follow_redirects=False).status_code,303)
        self.assertIn('Edited Educator',self.client.get(url).text)
        self.client.get('/logout');self.login('b');self.assertEqual(self.client.get(url).status_code,403)
        self.assertIn('Edited Educator', self.client.get('/demos?day='+str(scheduled.date())).text)
        edit['csrf']=self.form('/demos/new')['csrf'];self.assertEqual(self.client.post(url+'/educator',data=edit).status_code,403)
        self.assertEqual(self.client.post(url,data={**edit,'action':'CANCEL','notes':'Cancel'}).status_code,403)

    def test_demo_rejection_reason_is_visible_only_in_request_tracking(self):
        self.punch_in_for_test(2)
        self.login('a')
        booking = self.form('/demos/new')
        scheduled = datetime.now(ZoneInfo('Asia/Kolkata')) + timedelta(days=1)
        booking.update(client_id=1, educator_name='Guest', treatment='NanoBeen',
                       demo_at=scheduled.strftime('%Y-%m-%dT%H:%M'))
        self.assertEqual(self.client.post('/demos', data=booking, follow_redirects=False).status_code, 303)

        self.client.get('/logout')
        self.login()
        queue = '/command-center/demo-requests'
        decision = {'csrf': self.form(queue)['csrf'], 'decision': 'REJECTED'}
        self.assertEqual(self.client.post(queue + '/1', data=decision).status_code, 400)
        decision['reason'] = 'Educator unavailable'
        self.assertEqual(self.client.post(queue + '/1', data=decision, follow_redirects=False).status_code, 303)
        self.assertIn('No requests are awaiting approval', self.client.get(queue).text)

        self.client.get('/logout')
        self.login('a')
        tracking = self.client.get('/demo-requests').text
        self.assertIn('Rejected', tracking)
        self.assertIn('Educator unavailable', tracking)
        with SessionLocal() as db:
            self.assertEqual(db.query(DemoBooking).count(), 0)

    def test_notifications_and_employee_pdf_scope_dates(self):
        self.punch_in_for_test(2,3)
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

    def test_business_registration_returns_home_and_is_shared(self):
        self.punch_in_for_test(2, 3)
        self.login('a')
        self.assertIn('Add Business', self.client.get('/workspace').text)
        form = self.form('/salons/new?return_to=/orders/new')
        form.update(business_name='New Shared Salon', phone='9820012345',
                    return_to='/orders/new', client_type='SALON')
        response = self.client.post('/salons/new', data=form, headers={'Accept': 'application/json'})
        self.assertEqual(response.json()['redirect'], '/workspace')
        home = self.client.get('/workspace').text
        self.assertIn('Business registered successfully: New Shared Salon', home)
        self.assertNotIn('Business registered successfully', self.client.get('/workspace').text)
        self.assertEqual(self.client.post('/salons/new', data=form).status_code, 409)
        from database.models import Client
        with SessionLocal() as db:
            self.assertEqual(db.query(Client).filter_by(business_name='New Shared Salon').count(), 1)
        self.client.get('/logout')
        self.login('b')
        results = self.client.get('/business-search?q=shared').json()['matches']
        self.assertEqual(results[0]['name'], 'New Shared Salon')
        for url in ['/orders/new', '/demos/new', '/field/intake']:
            self.assertIn('New Shared Salon' if url != '/field/intake' else 'Search registered entries',
                          self.client.get(url).text)

    def test_business_types_and_optional_registration_gps(self):
        self.login()
        form = self.form('/salons/new')
        from database.models import Client, Visit
        with SessionLocal() as db:
            visits_before = db.query(Visit).count()
        for index, kind in enumerate(['SALON', 'UNISEX', 'PARLOR', 'DISTRIBUTOR', 'ACADEMY', 'OTHER']):
            data = {**form, 'business_name': 'Registered ' + kind,
                    'phone': str(9800000000 + index), 'client_type': kind}
            if kind == 'UNISEX':
                data.update(at_location='yes', latitude='23', longitude='72', accuracy='12')
            response = self.client.post('/salons/new', data=data, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            with SessionLocal() as db:
                client = db.query(Client).filter_by(business_name=data['business_name']).one()
                self.assertEqual(client.client_type, kind)
                self.assertEqual(client.latitude, 23 if kind == 'UNISEX' else None)
                self.assertEqual(client.longitude, 72 if kind == 'UNISEX' else None)
        with SessionLocal() as db:
            self.assertEqual(db.query(Visit).count(), visits_before)
            log = db.query(AuditLog).filter_by(action='GPS_REGISTERED').one()
            self.assertIn('"accuracy_m": 12.0', log.new_value)
        self.punch_in_for_test(1)
        nearby = self.client.get('/field/nearby?latitude=23&longitude=72').json()
        self.assertIn('Registered UNISEX', [item['name'] for item in nearby['nearby']])

    def test_registration_gps_validation_and_duplicate_preservation(self):
        self.login()
        form = self.form('/salons/new')
        data = {**form, 'business_name': 'GPS Salon', 'phone': '9870012345', 'at_location': 'yes'}
        for gps in [{}, {'latitude': 'NaN', 'longitude': '72', 'accuracy': '10'},
                    {'latitude': '91', 'longitude': '72', 'accuracy': '10'},
                    {'latitude': '23', 'longitude': '72', 'accuracy': '201'},
                    {'latitude': '23', 'longitude': '72', 'accuracy': '-1'}]:
            self.assertEqual(self.client.post('/salons/new', data={**data, **gps}).status_code, 400)
        data.update(latitude='23', longitude='72', accuracy='10')
        self.assertEqual(self.client.post('/salons/new', data=data, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.post('/salons/new', data={**data, 'latitude': '24'}).status_code, 409)
        from database.models import Client
        with SessionLocal() as db:
            client = db.query(Client).filter_by(business_name='GPS Salon').one()
            self.assertEqual(client.latitude, 23)
            self.assertEqual(db.query(AuditLog).filter_by(action='GPS_REGISTERED').count(), 1)

    def test_business_search_duplicate_normalization_and_csrf(self):
        self.login()
        form = self.form('/salons/new')
        form.update(business_name='Normal Salon', phone='+91 98200 12345')
        self.assertEqual(self.client.post('/salons/new', data={**form, 'csrf': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/salons/new', data=form, follow_redirects=False).status_code, 303)
        duplicate = {**form, 'business_name': 'Different Name', 'phone': '9820012345'}
        self.assertEqual(self.client.post('/salons/new', data=duplicate).status_code, 409)
        self.assertEqual(self.client.post('/salons/new', data={**form, 'business_name': ' normal   SALON ', 'phone': '5555555555'}).status_code, 409)
        self.assertEqual(self.client.get('/business-search?q=982001').json()['matches'][0]['name'], 'Normal Salon')
        self.assertEqual(self.client.get('/business-search?q=zzzzzz').json()['matches'], [])
        self.assertEqual(self.client.get('/business-search?q=').json()['matches'], [])
        self.assertEqual(self.client.post('/salons/new', data={**form, 'phone': ''}).status_code, 400)
        from database.models import Client
        with SessionLocal() as db:
            client = db.query(Client).filter_by(business_name='Normal Salon').one()
            client.status = 'INACTIVE'
            db.commit()
        self.assertFalse(self.client.get('/business-search?q=normal').json()['matches'][0]['active'])
        self.assertEqual(self.client.post('/salons/new', data=form).status_code, 409)


del OperationsTests

