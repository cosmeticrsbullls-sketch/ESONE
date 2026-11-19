import json
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import patch
from pypdf import PdfReader
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, Attendance, AuditLog
from modules.auto_attendance import day_cutoff, expire_attendance
from modules.workflows import now


class AutoAttendanceTests(unittest.TestCase):
    setUpClass = classmethod(OperationsTests.setUpClass.__func__)
    setUp = OperationsTests.setUp
    tearDown = OperationsTests.tearDown
    login = OperationsTests.login
    punch_in_for_test = OperationsTests.punch_in_for_test

    def attendance(self, punch_in, **extra):
        record = Attendance(user_id=2, punch_in_at=punch_in,
                            in_latitude=23, in_longitude=72, in_accuracy=10, **extra)
        with SessionLocal.begin() as db:
            db.add(record)
            db.flush()
            return record.id

    def test_cutoff_boundary_is_idempotent_and_preserves_gps(self):
        started = datetime(2026, 11, 18, 4, 30)
        cutoff = datetime(2026, 11, 18, 18, 29)
        self.assertEqual(day_cutoff(started), cutoff)
        identity = self.attendance(started)
        with SessionLocal.begin() as db:
            self.assertEqual(expire_attendance(db, cutoff - timedelta(seconds=1)), 0)
        with SessionLocal.begin() as db:
            self.assertEqual(expire_attendance(db, cutoff), 1)
        with SessionLocal.begin() as db:
            self.assertEqual(expire_attendance(db, cutoff + timedelta(days=1)), 0)
        with SessionLocal() as db:
            record = db.get(Attendance, identity)
            self.assertEqual(record.punch_in_at, started)
            self.assertEqual(record.punch_out_at, cutoff)
            self.assertIsNone(record.out_latitude)
            self.assertIsNone(record.out_longitude)
            self.assertIsNone(record.out_accuracy)
            event = db.query(AuditLog).filter_by(action='AUTO_PUNCH_OUT').one()
            self.assertEqual(json.loads(event.new_value)['actor'], 'system')
            self.assertEqual(record.in_accuracy, 10)

    def test_catchup_preserves_manual_punch_and_unfinished_work(self):
        closed = self.attendance(datetime(2026, 11, 17, 4),
                                 punch_out_at=datetime(2026, 11, 17, 12),
                                 out_latitude=24, out_longitude=73, out_accuracy=8)
        expired = self.attendance(datetime(2026, 11, 18, 4))
        with SessionLocal.begin() as db:
            db.get(Activity, 6).status = 'IN_PROGRESS'
            db.flush()
            self.assertEqual(expire_attendance(db, datetime(2026, 11, 19, 1)), 1)
        with SessionLocal() as db:
            self.assertEqual(db.get(Attendance, closed).out_latitude, 24)
            self.assertEqual(db.get(Attendance, closed).punch_out_at, datetime(2026, 11, 17, 12))
            self.assertEqual(db.get(Activity, 6).status, 'IN_PROGRESS')
            self.assertEqual(db.get(Attendance, expired).punch_out_at, datetime(2026, 11, 18, 18, 29))

    def test_legacy_late_punch_never_has_negative_duration(self):
        identity = self.attendance(datetime(2026, 11, 18, 18, 29, 30))
        with SessionLocal.begin() as db:
            self.assertEqual(expire_attendance(db, datetime(2026, 11, 19, 1)), 1)
        with SessionLocal() as db:
            record = db.get(Attendance, identity)
            self.assertGreaterEqual(record.punch_out_at, record.punch_in_at)

    def test_request_catchup_updates_home_history_and_pdf(self):
        self.login('a')
        identity = self.attendance(now() - timedelta(days=1))
        self.assertIn('Punch In', self.client.get('/workspace').text)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(Attendance, identity).punch_out_at)
        self.assertIn('Auto Punch Out', self.client.get('/attendance').text)
        pdf = self.client.get(f'/attendance/{identity}/pdf')
        text = ''.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Auto Punch Out', text)
        self.assertIn('No checkout GPS', text)

    def test_punch_in_waits_until_new_day_during_closing_minute(self):
        self.login('a')
        with patch('modules.team.now', return_value=day_cutoff(now())):
            response = self.client.post('/attendance', data={
                'csrf': self.csrf, 'action': 'IN', 'latitude': 23,
                'longitude': 72, 'accuracy': 10,
            })
        self.assertEqual(response.status_code, 409)
        with SessionLocal() as db:
            self.assertEqual(db.query(Attendance).count(), 0)


del OperationsTests
