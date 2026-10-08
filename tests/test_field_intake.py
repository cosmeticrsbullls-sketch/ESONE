import re
import unittest
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Client, Activity, Visit, AuditLog


class FieldIntakeTests(unittest.TestCase):
    setUpClass = classmethod(OperationsTests.setUpClass.__func__)
    setUp = OperationsTests.setUp
    tearDown = OperationsTests.tearDown
    login = OperationsTests.login


def form(self, who='a'):
    self.login(who)
    html=self.client.get('/visits').text
    return {'csrf':re.search(r'name="csrf" value="([^"]+)"',html)[1],
            'submission':re.search(r'name="submission" value="([^"]+)"',html)[1],
            'latitude':'23', 'longitude':'72', 'visit_type':'SALES'}


def test_lookup_types_distance_unmapped_and_no_writes(self):
    self.login('a')
    with SessionLocal() as db:
        for cid,kind,lat in [(1,'SALON',23),(2,'DISTRIBUTOR',23.001),(3,'ACADEMY',24)]:
            c=db.get(Client,cid);c.client_type=kind;c.latitude=lat;c.longitude=72
        db.add(Client(business_name='Unmapped academy',client_type='ACADEMY'))
        db.commit();before=db.query(AuditLog).count()
    result=self.client.get('/field/nearby?latitude=23&longitude=72').json()
    self.assertEqual([c['type'] for c in result['nearby']],['SALON','DISTRIBUTOR'])
    self.assertEqual(result['unmapped'][0]['name'],'Unmapped academy')
    with SessionLocal() as db:self.assertEqual(db.query(AuditLog).count(),before)


def test_empty_database_offers_registration(self):
    data=form(self)
    with SessionLocal() as db:db.query(Client).delete();db.commit()
    result=self.client.get('/field/nearby?latitude=23&longitude=72').json()
    self.assertEqual(result['nearby'],[]);self.assertEqual(result['unmapped'],[])
    html=self.client.get('/visits').text
    self.assertIn('ADD NEW VISIT — REGISTER NEW BUSINESS',html)
    self.assertNotIn('Select Salon',html)
    response=self.client.post('/field/start',data={**data,'business_name':'New Academy','phone':'999','client_type':'ACADEMY','address':'Test address','pincode':'380001','notes':'Discuss treatments'},follow_redirects=False)
    self.assertEqual(response.status_code,303)
    with SessionLocal() as db:
        c=db.query(Client).filter_by(business_name='New Academy').one()
        self.assertEqual((c.latitude,c.longitude,c.created_by,c.assigned_sales_id),(23,72,2,2))
        a=db.query(Activity).filter_by(client_id=c.id,activity_type='FIELD_VISIT').order_by(Activity.id.desc()).first()
        self.assertEqual(a.status,'IN_PROGRESS');self.assertEqual(a.notes,'Discuss treatments');self.assertEqual(c.address,'Test address')
        v=db.query(Visit).filter_by(activity_id=a.id).one();self.assertIsNotNone(v.check_in_at)


def test_existing_first_visit_and_replay(self):
    data={**form(self),'client_id':'1'}
    first=self.client.post('/field/start',data=data,follow_redirects=False)
    second=self.client.post('/field/start',data=data,follow_redirects=False)
    self.assertEqual(first.status_code,303);self.assertEqual(first.headers['location'],second.headers['location'])
    with SessionLocal() as db:
        self.assertEqual(db.query(Activity).count(),7)
        self.assertEqual(db.get(Client,1).latitude,23)
        self.assertEqual(db.query(AuditLog).filter_by(action='FIELD_INTAKE').count(),1)


def test_new_duplicate_rejected_without_visit(self):
    data={**form(self),'business_name':'New Salon','phone':'111','client_type':'SALON'}
    self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
    with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6);self.assertEqual(db.query(Client).count(),3)


def test_permissions_invalid_gps_csrf_and_radius(self):
    self.assertEqual(self.client.get('/field/nearby?latitude=23&longitude=72').status_code,401)
    data={**form(self),'client_id':'1'}
    for fields,status in [({'csrf':''},403),({'latitude':'nan'},400),({'longitude':'181'},400),({'visit_type':'BAD'},400),({'client_id':'999'},404)]:
        self.assertEqual(self.client.post('/field/start',data={**data,**fields}).status_code,status)
    with SessionLocal() as db:c=db.get(Client,1);c.latitude=24;c.longitude=72;db.commit()
    self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
    with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6);self.assertEqual(db.get(Client,1).latitude,24)

for test in [test_lookup_types_distance_unmapped_and_no_writes,test_empty_database_offers_registration,test_existing_first_visit_and_replay,test_new_duplicate_rejected_without_visit,test_permissions_invalid_gps_csrf_and_radius]:
    setattr(FieldIntakeTests,test.__name__,test)
del OperationsTests
