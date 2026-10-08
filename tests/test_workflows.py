import re
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, AuditLog, CollectionActivity, DemoBooking, PromiseToPay
from modules.operations import business_today

class WorkflowTests(unittest.TestCase):
    setUpClass = classmethod(OperationsTests.setUpClass.__func__)
    setUp = OperationsTests.setUp
    tearDown = OperationsTests.tearDown
    login = OperationsTests.login
    workbook = OperationsTests.workbook

    def form(self, path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        return {key: re.search(r'name="'+key+r'" value="([^"]+)"',response.text).group(1) for key in ['csrf']+(['submission'] if 'name="submission"' in response.text else [])}

    def call(self,kind='COLLECTION',outcome='PTP',**extra):
        data=self.form('/calls/new')
        data.update(client_id=1,kind=kind,outcome=outcome,notes='Customer call',promised_amount='1234.50',promise_date=str(business_today()))
        data.update(extra)
        return data

    def booking(self):
        data=self.form('/demos/new')
        data.update(client_id=1,educator_id=2,treatment='NanoBeen',demo_at=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),notes='Booking notes')
        return data

    def test_call_creates_ptp_and_replay_is_rejected(self):
        self.login();data=self.call()
        self.assertEqual(self.client.post('/calls',data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post('/calls',data=data,follow_redirects=False).status_code,409)
        with SessionLocal() as db:
            self.assertEqual(db.query(PromiseToPay).count(),4)
            c=db.query(CollectionActivity).order_by(CollectionActivity.id.desc()).first()
            self.assertIsNone(c.amount_received)
            self.assertEqual(db.query(AuditLog).filter_by(action='CALL_RECORDED').count(),1)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=calls'))),3)
        dashboard=self.client.get('/command-center').text
        self.assertIn('PTP today: <strong>2</strong>',dashboard)
        self.assertIn('Courtesy calls due: <strong>2</strong>',dashboard)

    def test_csrf_and_role_denials_leave_database_unchanged(self):
        self.login();data=self.call();data['csrf']='wrong'
        self.assertEqual(self.client.post('/calls',data=data).status_code,403)
        self.client.get('/logout');self.login('a')
        for path in ['/calls/new','/demos','/demos/new','/ptps/1']:
            self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.client.post('/calls',data=data).status_code,403)
        with SessionLocal() as db:self.assertEqual(db.query(PromiseToPay).count(),3)

    def test_invalid_amounts_dates_and_client_do_not_write(self):
        self.login()
        for value in ['NaN','Infinity','0','-1','1.001','10000000000','bad']:
            self.assertEqual(self.client.post('/calls',data=self.call(promised_amount=value)).status_code,400)
        self.assertEqual(self.client.post('/calls',data=self.call(promise_date='2020-01-01')).status_code,400)
        self.assertEqual(self.client.post('/calls',data=self.call(client_id=999)).status_code,404)
        with SessionLocal() as db:self.assertEqual(db.query(PromiseToPay).count(),3)

    def test_courtesy_contact_clears_current_visit_only(self):
        self.login()
        self.assertEqual(self.client.post('/calls',data=self.call('COURTESY_CALL','NO_ANSWER'),follow_redirects=False).status_code,303)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=courtesy'))),3)
        self.assertEqual(self.client.post('/calls',data=self.call('COURTESY_CALL','CONTACTED'),follow_redirects=False).status_code,303)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=courtesy'))),2)
        self.assertEqual(self.client.post('/calls',data=self.call('COURTESY_CALL','CONTACTED')).status_code,409)
        with SessionLocal() as db:
            db.add(Activity(client_id=1,activity_type='FIELD_VISIT',status='COMPLETED',completed_at=datetime.combine(business_today()-timedelta(days=7),datetime.min.time())+timedelta(hours=11)))
            db.commit()
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=courtesy'))),3)

    def test_ptp_reschedule_preserves_original_and_blocks_replay(self):
        self.login();data=self.form('/ptps/1');data.update(outcome='RESCHEDULED',notes='Next week',promise_date=str(business_today()+timedelta(days=7)),promised_amount='500')
        self.assertEqual(self.client.post('/ptps/1',data={**data,'csrf':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/ptps/1',data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post('/ptps/1',data=data).status_code,409)
        with SessionLocal() as db:
            old=db.get(PromiseToPay,1);self.assertEqual(old.status,'RESCHEDULED');self.assertEqual(old.promised_amount,5000)
            new=db.query(PromiseToPay).order_by(PromiseToPay.id.desc()).first();self.assertEqual(new.promised_amount,500);self.assertEqual(new.status,'OPEN')
        self.assertEqual(self.client.post('/ptps/2',data={**data,'outcome':'PAID'}).status_code,400)

    def test_demo_booking_start_complete_and_timestamp_replay(self):
        self.login();data=self.booking()
        response=self.client.post('/demos',data=data,follow_redirects=False)
        self.assertEqual(response.status_code,303);url=response.headers['location']
        self.assertEqual(self.client.post('/demos',data=data).status_code,409)
        transition=self.form(url);transition.update(action='COMPLETE',result='CONVERTED',notes='Done')
        self.assertEqual(self.client.post(url,data=transition).status_code,409)
        transition['action']='START';self.assertEqual(self.client.post(url,data=transition,follow_redirects=False).status_code,303)
        with SessionLocal() as db:started=db.query(DemoBooking).one().started_at
        self.assertEqual(self.client.post(url,data=transition).status_code,409)
        transition.update(action='COMPLETE',result='FOLLOW_UP')
        self.assertEqual(self.client.post(url,data=transition).status_code,400)
        transition.update(result='NOT_CONVERTED',notes='<script>reason</script>')
        self.assertEqual(self.client.post(url,data=transition,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post(url,data=transition).status_code,409)
        with SessionLocal() as db:
            d=db.query(DemoBooking).one();self.assertEqual(d.started_at,started);self.assertEqual(d.conversion_status,'NOT_CONVERTED');self.assertEqual(db.get(Activity,d.activity_id).status,'COMPLETED')
        self.assertNotIn('<script>reason</script>',self.client.get(url).text)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=demos'))),2)
        self.assertEqual(len(self.workbook(self.client.get('/reports/export?kind=demos&q=nonexistent'))),1)

    def test_management_forms_and_reports_do_not_write_records(self):
        self.login()
        from database.db import Base
        with SessionLocal() as db:before={t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        for path in ['/calls/new','/ptps/1','/demos','/demos/new','/reports/export?kind=calls','/reports/export?kind=demos','/command-center']:
            self.assertEqual(self.client.get(path).status_code,200)
        with SessionLocal() as db:after={t.name:db.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        self.assertEqual(before,after)

    def test_demo_invalid_booking_and_cancel(self):
        self.login();data=self.booking()
        self.assertEqual(self.client.post('/demos',data={**data,'educator_id':999}).status_code,400)
        self.assertEqual(self.client.post('/demos',data={**data,'demo_at':'2020-01-01T10:00'}).status_code,400)
        self.assertEqual(self.client.post('/demos',data={**data,'client_id':999}).status_code,404)
        response=self.client.post('/demos',data=data,follow_redirects=False);url=response.headers['location']
        t=self.form(url);t.update(action='CANCEL',notes='Customer cancelled')
        self.assertEqual(self.client.post(url,data=t,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post(url,data={**t,'action':'START'}).status_code,409)
        self.assertEqual(self.client.get('/demos/999').status_code,404)

# Keep discovery from re-running the imported fixture class.
del OperationsTests
