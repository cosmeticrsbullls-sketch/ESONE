import re
import unittest
from datetime import datetime
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, Client, DemoBooking

class CalendarTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def form(self,path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        return {'csrf':re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)}

    def seed_demos(self):
        with SessionLocal() as db:
            for index,scheduled,educator,status in [(10,'2028-02-29T10:00',2,'BOOKED'),(11,'2028-02-29T14:00',3,'BOOKED'),(12,'2028-02-28T10:00',2,'CANCELLED'),(13,'2028-03-01T10:00',2,'BOOKED')]:
                a=Activity(id=index,client_id=1,activity_type='DEMO',status=status,created_by=1)
                db.add(a);db.flush();db.add(DemoBooking(id=index,activity_id=a.id,demo_date=datetime.fromisoformat(scheduled),product_or_treatment='NanoBeen',assigned_educator_id=educator))
            db.commit()

    def test_calendar_highlights_dates_and_filters_educator(self):
        self.login();self.seed_demos()
        response=self.client.get('/demos?month=2028-02')
        self.assertIn('data-date="2028-02-29" data-demo-count="2"',response.text)
        self.assertIn('data-date="2028-02-28" data-demo-count="0"',response.text)
        self.assertNotIn('data-date="2028-03-01"',response.text)
        response=self.client.get('/demos?month=2028-02&educator_id=2')
        self.assertIn('data-date="2028-02-29" data-demo-count="1"',response.text)
        self.assertIn('Sales A',response.text)
        self.assertNotIn('#11</a>',response.text)

    def test_day_drilldown_and_booking_prefill(self):
        self.login();self.seed_demos()
        response=self.client.get('/demos?month=2028-02&day=2028-02-29&educator_id=2')
        self.assertIn('#10</a>',response.text);self.assertNotIn('#12</a>',response.text)
        self.assertIn('demo_day=2028-02-29',response.text)
        response=self.client.get('/demos/new?demo_day=2028-02-29&educator_id=2&client_id=1')
        self.assertIn('value="2028-02-29T10:00"',response.text)
        self.assertIn('value="2" selected>Sales A',response.text)
        self.assertIn('value="1" selected>',response.text)

    def test_calendar_invalid_dates_permissions_and_nonmutating_reads(self):
        self.login()
        for path in ['/demos?month=bad','/demos?month=2028-13','/demos?month=2028-02&day=2028-03-01','/demos?educator_id=999']:
            self.assertEqual(self.client.get(path).status_code,400)
        self.assertEqual(self.client.get('/demos?month=2028-02&day=2028-02-30').status_code,422)
        with SessionLocal() as db:before=db.query(Activity).count()
        self.assertEqual(self.client.get('/demos?month=2028-02').status_code,200)
        with SessionLocal() as db:self.assertEqual(before,db.query(Activity).count())
        self.client.get('/logout');self.login('a');self.assertEqual(self.client.get('/demos').status_code,403)

    def test_empty_salon_options_are_explicit_and_registration_is_visible(self):
        self.login()
        with SessionLocal() as db:db.query(Client).delete();db.commit()
        response=self.client.get('/demos/new')
        self.assertIn('No salons registered',response.text);self.assertIn('+ New Salon',response.text)
        self.assertIn('Search salon / phone',response.text)
        self.assertIn('name="client_id" required',response.text)
        self.assertIn('id="new-salon"',self.client.get('/clients').text)

    def test_register_salon_returns_to_booking_safely(self):
        self.login();data=self.form('/clients?return_to=/demos/new')
        data.update(business_name='New Test Salon',return_to='/demos/new')
        self.assertEqual(self.client.post('/clients/create',data={**data,'csrf':'wrong'}).status_code,403)
        response=self.client.post('/clients/create',data=data,follow_redirects=False)
        self.assertEqual(response.status_code,303)
        self.assertRegex(response.headers['location'],r'^/demos/new\?client_id=\d+$')
        self.assertIn('New Test Salon',self.client.get(response.headers['location']).text)
        response=self.client.post('/clients/create',data={**data,'business_name':'Other Salon','return_to':'https://evil.example'},follow_redirects=False)
        self.assertEqual(response.headers['location'],'/clients')
        self.assertEqual(self.client.post('/clients/create',data={**data,'business_name':'   '}).status_code,400)

# The imported class supplies fixtures only.
del OperationsTests
