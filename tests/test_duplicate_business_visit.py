import re
import unittest
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity,Client,Visit

class DuplicateBusinessVisitTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def data(self):
        self.login('a')
        html=self.client.get('/field/intake').text
        fields={k:re.search(r'name="'+k+r'" value="([^"]+)"',html)[1] for k in ['csrf','submission']}
        return {**fields,'latitude':'23','longitude':'72','visit_type':'COURTESY','business_name':'Typed name','phone':'111','notes':'Discussed homecare products'}

    def test_duplicate_recovery_starts_existing_business_visit_once(self):
        data=self.data()
        with SessionLocal.begin() as db:
            c=db.get(Client,1);c.latitude=23;c.longitude=72
        response=self.client.post('/field/start',data=data,follow_redirects=False)
        self.assertEqual(response.status_code,409)
        conflict=response.json();self.assertEqual(conflict['code'],'BUSINESS_ALREADY_EXISTS')
        self.assertEqual(conflict['matches'][0]['id'],1)
        with SessionLocal() as db:
            before=db.get(Client,1);original=(before.business_name,before.phone)
            self.assertEqual(db.query(Client).count(),3)
            self.assertEqual(db.query(Activity).count(),6)
        retry={**data,'client_id':str(conflict['matches'][0]['id'])}
        started=self.client.post('/field/start',data=retry,follow_redirects=False)
        self.assertEqual(started.status_code,303)
        self.assertEqual(self.client.post('/field/start',data=retry,follow_redirects=False).headers['location'],started.headers['location'])
        with SessionLocal() as db:
            self.assertEqual(db.query(Client).count(),3)
            self.assertEqual(db.query(Activity).count(),7)
            existing=db.get(Client,1);self.assertEqual((existing.business_name,existing.phone),original)
            activity=db.get(Activity,int(started.headers['location'].split('/')[-1]))
            self.assertEqual((activity.client_id,activity.created_by,activity.status,activity.notes),(1,2,'IN_PROGRESS',data['notes']))
            visit=db.query(Visit).filter_by(activity_id=activity.id).one()
            self.assertEqual((visit.visit_type,visit.check_in_latitude,visit.check_in_longitude),('COURTESY',23,72))

    def test_matching_registered_business_still_requires_correct_gps(self):
        data=self.data()
        with SessionLocal.begin() as db:
            c=db.get(Client,1);c.latitude=24;c.longitude=72
        conflict=self.client.post('/field/start',data=data).json()
        self.assertEqual(conflict['matches'][0]['id'],1)
        rejected=self.client.post('/field/start',data={**data,'client_id':'1'})
        self.assertEqual(rejected.status_code,409);self.assertIn('Location mismatch',rejected.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(Activity).count(),6)
            self.assertEqual(db.get(Client,1).latitude,24)

    def test_inactive_matches_are_identified_and_cannot_start(self):
        data=self.data()
        with SessionLocal.begin() as db:db.get(Client,1).status='INACTIVE'
        response=self.client.post('/field/start',data=data)
        self.assertFalse(response.json()['matches'][0]['active'])
        self.assertEqual(self.client.post('/field/start',data={**data,'client_id':'1'}).status_code,409)
        with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6)

    def test_ambiguous_name_phone_matches_require_explicit_selection(self):
        data=self.data()
        with SessionLocal.begin() as db:db.get(Client,2).business_name='Typed name'
        response=self.client.post('/field/start',data=data)
        self.assertEqual({m['id'] for m in response.json()['matches']},{1,2})
        with SessionLocal() as db:self.assertEqual(db.query(Activity).count(),6)

    def test_distinct_businesses_can_share_the_same_gps(self):
        data=self.data()
        first=self.client.post('/field/start',data={**data,'business_name':'New Salon One','phone':'444'},follow_redirects=False)
        self.assertEqual(first.status_code,303)
        html=self.client.get('/field/intake').text
        submission=re.search(r'name="submission" value="([^"]+)"',html)[1]
        second=self.client.post('/field/start',data={**data,'submission':submission,'business_name':'New Salon Two','phone':'555'},follow_redirects=False)
        self.assertEqual(second.status_code,303)
        with SessionLocal() as db:
            salons=db.query(Client).filter(Client.business_name.in_(['New Salon One','New Salon Two'])).all()
            self.assertEqual(len(salons),2)
            self.assertTrue(all((s.latitude,s.longitude)==(23,72) for s in salons))
            self.assertEqual(db.query(Activity).count(),8)


del OperationsTests
