"""Attendance policy integration tests against an isolated database."""
import os
import re
import unittest
from datetime import timedelta
from unittest.mock import patch
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, Attendance, AuditLog, Client, DemoBooking, SalesOrder, Visit
from modules.workflows import now

class DutyGateTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    punch_in_for_test=OperationsTests.punch_in_for_test
    _base_login=OperationsTests.login
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def duty(self,*ids):self.punch_in_for_test(*(ids or (2,)))

    def field(self,client_id='1'):
        # Get a normal form while on duty, then reuse it after punch-out in stale-tab tests.
        html=self.client.get('/field/intake').text
        return {**{k:re.search(r'name="'+k+r'" value="([^"]+)"',html)[1] for k in ['csrf','submission']},'latitude':'23','longitude':'72','visit_type':'SALES','client_id':client_id,'notes':'Attendance QA'}

    def punch(self,action):
        return self.client.post('/attendance',data=dict(csrf=self.csrf,action=action,latitude=23,longitude=72,accuracy=12),follow_redirects=False)

    def demo(self,creator=2,assignee=2,status='BOOKED'):
        with SessionLocal.begin() as db:
            a=Activity(client_id=1,activity_type='DEMO',status=status,created_by=creator,assigned_user_id=assignee);db.add(a);db.flush()
            d=DemoBooking(activity_id=a.id,demo_date=now(),assigned_educator_id=assignee,started_at=now() if status=='IN_PROGRESS' else None);db.add(d);db.flush();identity=d.id
        return '/demos/'+str(identity)

    def test_off_duty_cannot_check_in_lookup_or_use_legacy_start(self):
        self.login('a')
        self.assertIn('CHECK IN VISIT — Punch In first',self.client.get('/field/intake').text)
        self.assertEqual(self.client.get('/field/nearby?latitude=23&longitude=72').status_code,409)
        for endpoint,data in [('/field/start',dict(csrf=self.csrf,submission='a'*24,latitude=23,longitude=72,visit_type='SALES',business_name='No write',phone='555')),('/visits/create',dict(client_id=1,visit_type='SALES')),('/visits/6/start',dict(latitude=23,longitude=72))]:
            response=self.client.post(endpoint,data=data);self.assertEqual(response.status_code,409,endpoint)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),6);self.assertEqual(db.query(Client).count(),3);self.assertEqual(db.query(AuditLog).count(),0)

    def test_full_shift_visit_complete_home_then_punch_out(self):
        self.login('a');self.assertEqual(self.punch('IN').status_code,303)
        started=self.client.post('/field/start',data=self.field(),follow_redirects=False)
        self.assertEqual(started.status_code,303);url=started.headers['location']
        self.assertEqual(self.punch('OUT').status_code,409)
        self.assertIn('disabled aria-disabled="true"',self.client.get('/attendance').text)
        with patch.dict(os.environ,{'ESONE_REQUIRE_ACTIVITY_OTP':'false'}):
            complete=self.client.post(url+'/complete',data=dict(csrf=self.csrf,notes='Test complete'),follow_redirects=False)
        self.assertEqual(complete.headers['location'],'/workspace')
        self.assertEqual(self.punch('OUT').status_code,303)
        with SessionLocal() as db:
            self.assertIsNotNone(db.query(Attendance).one().punch_out_at)
            self.assertEqual(db.get(Activity,int(url.split('/')[-1])).status,'COMPLETED')

    def test_stale_open_form_cannot_create_business_after_punch_out(self):
        self.login('a');self.duty();data=self.field('');data.update(business_name='Blocked New Salon',phone='9876543210')
        self.assertEqual(self.punch('OUT').status_code,303)
        self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
        with SessionLocal() as db:self.assertEqual(db.query(Client).count(),3);self.assertEqual(db.query(Activity).count(),6)

    def test_admin_field_visit_still_requires_punch_in(self):
        self.login();self.assertEqual(self.client.post('/visits/6/start',data=dict(latitude=23,longitude=72)).status_code,409)
        self.duty(1);self.assertEqual(self.client.post('/visits/6/start',data=dict(latitude=23,longitude=72)).status_code,200)

    def test_off_duty_cannot_book_order_register_salon_or_book_demo(self):
        self.login('a')
        order=dict(csrf=self.csrf,submission='q'*24,client_id=1,**{'qty_ES-01':1,'discount_ES-01':0})
        self.assertEqual(self.client.post('/orders',data=order).status_code,409)
        self.assertEqual(self.client.post('/salons/new',data=dict(csrf=self.csrf,business_name='Blocked',phone='555')).status_code,409)
        from zoneinfo import ZoneInfo
        from datetime import datetime
        booking=dict(csrf=self.csrf,submission='d'*24,client_id=1,educator_name='QA',treatment='NanoBeen',demo_at=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'))
        self.assertEqual(self.client.post('/demos',data=booking).status_code,409)
        self.assertIn('<fieldset disabled aria-disabled="true">',self.client.get('/orders/new').text)
        with SessionLocal() as db:self.assertEqual(db.query(SalesOrder).count(),0);self.assertEqual(db.query(DemoBooking).count(),0);self.assertEqual(db.query(Client).count(),3)
        self.duty();self.assertEqual(self.client.post('/orders',data=order,follow_redirects=False).status_code,303)

    def test_open_order_form_is_denied_after_punch_out(self):
        self.login('a');self.duty()
        html=self.client.get('/orders/new').text
        data=dict(csrf=self.csrf,submission=re.search('name="submission" value="([^"]+)"',html)[1],client_id=1,**{'qty_ES-01':1})
        self.assertEqual(self.punch('OUT').status_code,303)
        self.assertEqual(self.client.post('/orders',data=data).status_code,409)

    def test_office_order_and_registration_are_available_off_duty(self):
        self.login()
        data=dict(csrf=self.csrf,submission='o'*24,client_id=1,**{'qty_ES-01':1})
        self.assertEqual(self.client.post('/orders',data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post('/salons/new',data=dict(csrf=self.csrf,business_name='Office Salon',phone='444'),follow_redirects=False).status_code,303)
        self.assertNotIn('<fieldset disabled',self.client.get('/orders/new').text)

    def test_demo_requires_duty_and_blocks_punch_out_until_complete(self):
        self.login('a');url=self.demo();data=dict(csrf=self.csrf,action='START',notes='QA start')
        self.assertEqual(self.client.post(url,data=data).status_code,409)
        self.duty();self.assertEqual(self.client.post(url,data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.punch('OUT').status_code,409)
        response=self.client.post(url,data={**data,'action':'COMPLETE','result':'CONVERTED'},follow_redirects=False)
        self.assertEqual(response.headers['location'],'/workspace');self.assertEqual(self.punch('OUT').status_code,303)

    def test_creator_can_punch_out_when_another_educator_owns_active_demo(self):
        self.login();self.duty(1,2);url=self.demo(creator=1,assignee=2,status='IN_PROGRESS')
        self.assertEqual(self.punch('OUT').status_code,303)
        self.login('a');self.assertEqual(self.punch('OUT').status_code,409)

    def test_assigned_educator_must_be_on_duty_for_admin_start(self):
        self.login();self.duty(1);url=self.demo(creator=1,assignee=2)
        response=self.client.post(url,data=dict(csrf=self.csrf,action='START',notes='Admin start'))
        self.assertEqual(response.status_code,409);self.assertIn('educator must Punch In',response.text)
        self.duty(2);self.assertEqual(self.client.post(url,data=dict(csrf=self.csrf,action='START',notes='Admin start'),follow_redirects=False).status_code,303)

    def test_other_employee_activity_and_completed_work_do_not_block_punch_out(self):
        self.login('a');self.duty(2,3);self.demo(creator=3,assignee=3,status='IN_PROGRESS')
        self.assertEqual(self.punch('OUT').status_code,303)

    def test_overnight_shift_can_finish_but_cannot_start_new_work(self):
        self.login('a');self.duty()
        self.assertEqual(self.client.post('/visits/6/start',data=dict(latitude=23,longitude=72)).status_code,200)
        with SessionLocal.begin() as db:db.query(Attendance).filter_by(user_id=2).one().punch_in_at=now()-timedelta(days=1)
        self.assertEqual(self.client.post('/visits/create',data=dict(client_id=1,visit_type='SALES')).status_code,409)
        self.assertEqual(self.punch('OUT').status_code,409)
        with patch.dict(os.environ,{'ESONE_REQUIRE_ACTIVITY_OTP':'false'}):
            html=self.client.get('/visits/6').text
            self.assertNotIn('<fieldset disabled',html)
            self.assertEqual(self.client.post('/visits/6/complete',data=dict(csrf=self.csrf,notes='Overnight recovery'),follow_redirects=False).status_code,303)
        self.assertEqual(self.punch('OUT').status_code,303)
        self.assertEqual(self.punch('IN').status_code,303)

    def test_old_open_shift_without_active_work_can_be_closed_and_reopened(self):
        self.login('a');self.duty()
        with SessionLocal.begin() as db:db.query(Attendance).one().punch_in_at=now()-timedelta(days=1)
        self.assertEqual(self.client.get('/field/nearby?latitude=23&longitude=72').status_code,409)
        self.assertEqual(self.punch('OUT').status_code,303);self.assertEqual(self.punch('IN').status_code,303)
        self.assertEqual(self.client.get('/field/nearby?latitude=23&longitude=72').status_code,200)

    def test_reports_history_and_sharing_remain_available_off_duty(self):
        self.login('a')
        for url in ['/workspace','/visits','/visits/1','/activity-reports','/notifications','/account/password','/activities/1/pdf']:
            self.assertEqual(self.client.get(url).status_code,200,url)
        html=self.client.get('/visits/1').text
        self.assertIn('class="share-pdf"',html)

    def test_ended_attendance_cannot_complete_existing_visit_directly(self):
        self.login('a');self.duty();self.client.post('/visits/6/start',data=dict(latitude=23,longitude=72))
        with SessionLocal.begin() as db:db.query(Attendance).one().punch_out_at=now()
        with patch.dict(os.environ,{'ESONE_REQUIRE_ACTIVITY_OTP':'false'}):
            self.assertEqual(self.client.post('/visits/6/complete',data=dict(csrf=self.csrf,notes='Bypass')).status_code,409)
        with SessionLocal() as db:self.assertEqual(db.get(Activity,6).status,'IN_PROGRESS')

    def test_cancelling_booked_demo_is_available_off_duty(self):
        self.login('a');url=self.demo()
        self.assertIn('Cancel Booking',self.client.get(url).text)
        self.assertEqual(self.client.post(url,data=dict(csrf=self.csrf,action='CANCEL',notes='Schedule changed'),follow_redirects=False).status_code,303)


del OperationsTests
