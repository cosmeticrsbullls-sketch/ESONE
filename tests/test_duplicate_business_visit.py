"""Registered-business selection replaces inline duplicate registration recovery."""
import unittest
from tests.test_operations import OperationsTests
from tests.test_device_camera import photo_form
from database.db import SessionLocal
from database.models import Client, Activity, VisitPhoto

class DuplicateBusinessVisitTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login
    punch_in_for_test=OperationsTests.punch_in_for_test

    def test_existing_selection_does_not_overwrite_business_details(self):
        self.login('a');self.punch_in_for_test()
        data=photo_form(self)
        response=self.client.post('/field/start',data={**data,'business_name':'Spoofed rename','phone':'999'})
        self.assertEqual(response.status_code,200)
        with SessionLocal() as db:
            self.assertEqual(db.get(Client,1).phone,'111')
            self.assertNotEqual(db.get(Client,1).business_name,'Spoofed rename')
            self.assertEqual(db.query(Client).count(),3)

    def test_registered_businesses_at_same_gps_are_separate_visits(self):
        self.login('a');self.punch_in_for_test()
        for cid in [1,2]:
            self.assertEqual(self.client.post('/field/start',data=photo_form(self,cid)).status_code,200)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),8)
            self.assertEqual(db.query(VisitPhoto).count(),2)
            self.assertEqual((db.get(Client,1).latitude,db.get(Client,2).latitude),(23,23))

    def test_no_business_id_cannot_register_implicitly(self):
        self.login('a');self.punch_in_for_test()
        data=photo_form(self);data['client_id']=''
        self.assertEqual(self.client.post('/field/start',data={**data,'business_name':'Duplicate','phone':'111'}).status_code,400)
        with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6)

del OperationsTests
