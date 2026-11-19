import unittest
from tests.test_operations import OperationsTests
from tests.test_device_camera import photo_form
from database.db import SessionLocal
from database.models import Client, Activity, Visit, AuditLog

class FieldIntakeTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    punch_in_for_test=OperationsTests.punch_in_for_test
    _base_login=OperationsTests.login
    def login(self,who='a'):
        self.punch_in_for_test(1,2,3);self._base_login(who)

    def test_workspace_links_and_single_form_collection_visit(self):
        self.assertEqual(self.client.get('/field/intake',follow_redirects=False).headers['location'],'/login')
        self.login()
        for section in ['sales','collection']:
            self.assertIn('href="/field/intake?visit_type='+section.upper()+'"',self.client.get('/workspace/'+section).text)
            self.assertIn('value="'+section.upper()+'" selected>',self.client.get('/field/intake?visit_type='+section.upper()).text)
        data=photo_form(self);data['visit_type']='COLLECTION'
        response=self.client.post('/field/start',data=data)
        self.assertEqual(response.json()['redirect'],'/workspace')
        with SessionLocal() as db:
            a=db.query(Activity).order_by(Activity.id.desc()).first()
            self.assertEqual(a.status,'COMPLETED')
            self.assertEqual(db.query(Visit).filter_by(activity_id=a.id).one().visit_type,'COLLECTION')

    def test_lookup_types_distance_unmapped_and_no_writes(self):
        self.login()
        with SessionLocal.begin() as db:
            for cid,kind,lat in [(1,'SALON',23),(2,'DISTRIBUTOR',23.001),(3,'ACADEMY',24)]:
                c=db.get(Client,cid);c.client_type=kind;c.latitude=lat;c.longitude=72
            db.add(Client(business_name='Unmapped academy',client_type='ACADEMY'))
            before=db.query(AuditLog).count()
        result=self.client.get('/field/nearby?latitude=23&longitude=72').json()
        self.assertEqual([c['type'] for c in result['nearby']],['SALON','DISTRIBUTOR'])
        self.assertEqual(result['unmapped'][0]['name'],'Unmapped academy')
        with SessionLocal() as db:self.assertEqual(db.query(AuditLog).count(),before)

    def test_missing_business_redirects_employee_to_add_business_not_inline_form(self):
        self.login()
        html=self.client.get('/field/intake').text
        self.assertIn('Add Business on Home',html);self.assertNotIn('name="business_name"',html)
        data=photo_form(self);data['client_id']=''
        response=self.client.post('/field/start',data={**data,'business_name':'No inline','phone':'999'})
        self.assertEqual(response.status_code,400)
        with SessionLocal() as db:self.assertEqual(db.query(Client).count(),3)

    def test_first_visit_registers_gps_and_repeat_finish_is_idempotent(self):
        self.login();data=photo_form(self)
        self.assertEqual(self.client.post('/field/start',data=data).status_code,200)
        self.assertEqual(self.client.post('/field/start',data=data).status_code,200)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),7)
            self.assertEqual(db.get(Client,1).latitude,23)
            self.assertEqual(db.query(AuditLog).filter_by(action='FIELD_INTAKE').count(),1)

    def test_csrf_inactive_and_radius_checks_remain(self):
        self.login();data=photo_form(self)
        self.assertEqual(self.client.post('/field/start',data={**data,'csrf':''}).status_code,403)
        with SessionLocal.begin() as db:db.get(Client,1).status='INACTIVE'
        self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
        with SessionLocal.begin() as db:c=db.get(Client,1);c.status='LEAD';c.latitude=24;c.longitude=72
        self.assertEqual(self.client.post('/field/start',data=data).status_code,409)
        with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6)

del OperationsTests
