import re
import unittest
from datetime import timedelta
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Attendance
from modules.workflows import now


class HomeAttendanceTests(unittest.TestCase):
    setUpClass = classmethod(OperationsTests.setUpClass.__func__)
    setUp = OperationsTests.setUp
    tearDown = OperationsTests.tearDown
    login = OperationsTests.login

    def label(self):
        response = self.client.get('/workspace')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return re.search(r'<a class="secondary" href="/attendance"[^>]*>([^<]+)</a>', response.text)[1]

    def test_punch_label_tracks_full_attendance_cycle(self):
        self.login('a')
        self.assertEqual(self.label(), 'Punch In')
        data=dict(csrf=self.csrf,latitude=23,longitude=72,accuracy=12)
        self.assertEqual(self.client.post('/attendance',data={**data,'action':'IN'},follow_redirects=False).status_code,303)
        self.assertEqual(self.label(), 'Punch Out')
        self.assertRegex(self.client.get('/attendance').text,r'<button[^>]*>Punch Out</button>')
        self.assertEqual(self.client.post('/attendance',data={**data,'action':'OUT'},follow_redirects=False).status_code,303)
        self.assertEqual(self.label(), 'Punch In')
        self.assertRegex(self.client.get('/attendance').text,r'<button[^>]*>Punch In</button>')

    def test_another_employee_open_punch_does_not_change_own_label(self):
        with SessionLocal.begin() as db:
            db.add(Attendance(user_id=3,punch_in_at=now(),in_latitude=23,in_longitude=72,in_accuracy=12))
        self.login('a')
        self.assertEqual(self.label(),'Punch In')
        self.login('b')
        self.assertEqual(self.label(),'Punch Out')

    def test_older_unclosed_punch_still_requires_punch_out(self):
        # Match the attendance endpoint: an overnight open shift must be closed.
        with SessionLocal.begin() as db:
            db.add(Attendance(user_id=2,punch_in_at=now()-timedelta(days=1),in_latitude=23,in_longitude=72,in_accuracy=12))
        self.login('a')
        self.assertEqual(self.label(),'Punch Out')

    def test_home_reads_do_not_create_attendance(self):
        self.login('a')
        self.label();self.label()
        with SessionLocal() as db:
            self.assertEqual(db.query(Attendance).count(),0)


del OperationsTests
