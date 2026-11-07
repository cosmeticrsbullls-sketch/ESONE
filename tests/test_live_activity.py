import unittest
from datetime import timedelta
from unittest.mock import patch
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, Attendance, Visit
from modules.live_activity import team_data, utc_boundary
from modules.operations import business_today
from modules.workflows import now

class LiveActivityTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def test_management_only_and_scoped_exports(self):
        self.login('a')
        self.assertEqual(self.client.get('/live-activity').status_code,403)
        self.assertEqual(self.client.get('/live-activity/data').status_code,403)
        self.assertEqual(self.client.get('/activities/6/pdf').status_code,200)
        self.login('b')
        self.assertEqual(self.client.get('/activities/6/pdf').status_code,404)
        self.assertEqual(self.client.get('/activities/6/share').status_code,404)
        self.login()
        self.assertIn('Live Activity',self.client.get('/command-center').text)
        self.assertEqual(self.client.get('/live-activity/data').headers['cache-control'],'no-store')

    def test_counters_boundaries_and_location_links(self):
        lower=utc_boundary(business_today());point=lower+timedelta(hours=1)
        with SessionLocal.begin() as db:
            # Remove fixture completions so calendar boundary expectations are explicit.
            for a in db.query(Activity).all():
                if a.status=='COMPLETED':a.status='CANCELLED'
            db.add(Attendance(user_id=2,punch_in_at=point,in_latitude=23,in_longitude=72,in_accuracy=20))
            a=db.get(Activity,6);a.status='COMPLETED';a.completed_at=point
            v=db.query(Visit).filter_by(activity_id=6).one();v.check_in_at=point;v.check_in_latitude=23.1;v.check_in_longitude=72.1
            db.add(Activity(id=7,client_id=1,activity_type='FIELD_VISIT',status='COMPLETED',assigned_user_id=2,completed_at=lower+timedelta(days=1)))
            db.add(Visit(activity_id=7,visit_type='SALES'))
        with SessionLocal() as db:
            row=next(r for r in team_data(db) if r['id']==2)
            self.assertEqual((row['today_visits'],row['month_visits']),(1,1))
            self.assertTrue(row['on_duty']);self.assertIn('google.com/maps/search/',row['location']['url'])
        self.login('a')
        self.assertIn('Share',self.client.get('/attendance').text)
        with SessionLocal.begin() as db:db.query(Attendance).one().punch_out_at=point+timedelta(minutes=30)
        with SessionLocal() as db:
            row=next(r for r in team_data(db) if r['id']==2)
            self.assertFalse(row['on_duty']);self.assertIsNone(row['location'])

    def test_each_activity_pdf_is_branded(self):
        self.login('a')
        from io import BytesIO
        from pypdf import PdfReader
        response=self.client.get('/activities/6/pdf')
        self.assertEqual(response.status_code,200)
        doc=PdfReader(BytesIO(response.content))
        self.assertGreater(len(doc.pages[0].images),0)
        self.assertIn('/activities/6/share',self.client.get('/activity-reports').text)
        self.assertIn('Share',self.client.get('/visits/6').text)

del OperationsTests
