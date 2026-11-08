import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
import re
import unittest
from decimal import Decimal
from io import BytesIO
from pypdf import PdfReader
from tests.test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Activity, AuditLog, SalesOrder, Client, OrderLine
from modules.billing import calculate, amount_words

class BillingMathTests(unittest.TestCase):
    def row(self,**kw):return dict(quantity=1,rate='1180',discount='0',gst='18',**kw)
    def test_indian_amount_words_match_bill_totals(self):
        self.assertEqual(amount_words(Decimal('79008')), 'Seventy Nine Thousand Eight Rupees Only')
        self.assertEqual(amount_words(Decimal('309804')), 'Three Lakh Nine Thousand Eight Hundred Four Rupees Only')
        self.assertEqual(amount_words(Decimal('0')), 'Zero Rupees Only')
    def test_gst_is_extracted_not_added_again(self):
        rows,t=calculate([self.row()],'GST','23')
        self.assertEqual((t['taxable'],t['igst'],t['total']),(Decimal('1000'),Decimal('180'),Decimal('1180')))
        self.assertEqual(rows[0]['net'],Decimal('1180'))
    def test_discount_before_inclusive_tax(self):
        _,t=calculate([dict(quantity=2,rate='1180',discount='50',gst='18')],'GST','24')
        self.assertEqual((t['taxable'],t['cgst'],t['sgst'],t['igst'],t['total']),(Decimal('1000'),Decimal('90'),Decimal('90'),Decimal('0'),Decimal('1180')))
    def test_mixed_rates_and_intrastate_rounding_reconcile(self):
        rows,t=calculate([dict(quantity=3,rate='350',discount='0',gst='5'),dict(quantity=1,rate='1180.01',discount='0',gst='18')],'GST','24')
        for row in rows:self.assertEqual(row['taxable']+row['cgst']+row['sgst']+row['igst'],row['net'])
        self.assertEqual(t['net']+t['round_off'],t['total'])
    def test_non_gst_sample_total_matches(self):
        rows=[dict(quantity=6,rate='16999',discount='67.5'),dict(quantity=6,rate='18999',discount='67.5'),dict(quantity=12,rate='1349',discount='65'),dict(quantity=12,rate='749',discount='65')]
        _,t=calculate(rows,'NON_GST','',Decimal('5000'))
        self.assertEqual((t['net'],t['round_off'],t['total'],t['balance']),(Decimal('79007.70'),Decimal('.30'),Decimal('79008'),Decimal('74008')))
        self.assertEqual(t['cgst']+t['sgst']+t['igst'],0)
    def test_invalid_numbers_and_overpayment_rejected(self):
        for bad in ['NaN','Infinity','-1','1.001']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):calculate([dict(quantity=1,rate=bad,discount='0',gst='18')],'GST','24')
        with self.assertRaises(ValueError):calculate([self.row()],'GST','24',Decimal('2000'))
        with self.assertRaises(ValueError):calculate([self.row()],'GST','99')

class BillingRouteTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login

    def form(self,kind='GST',**kw):
        d=dict(csrf=self.csrf,kind=kind,client_id='1',order_id='0',customer_name='Test Salon',customer_address='Test Road, Gujarat',customer_phone='9999999999',customer_gstin='',state_code='24',bill_date='2026-11-08',due_date='2026-12-08',payment_mode='Credit',received='0',qty_ES_01='')
        d.pop('qty_ES_01');d.update({'qty_ES-01':'2','rate_ES-01':'1180','discount_ES-01':'50','gst_ES-01':'18','hsn_ES-01':'3305'});d.update(kw);return d
    def test_command_center_and_two_company_flow(self):
        self.login();self.assertIn('Generate Sales Bill',self.client.get('/command-center').text)
        html=self.client.get('/billing').text
        self.assertIn('SHIVAM EXPORT',html);self.assertIn('SHIVAM COSMETICS',html)
        for kind in ['GST','NON_GST']:
            html=self.client.get('/billing/source?kind='+kind).text
            self.assertIn('From Sales Order',html);self.assertIn('New Sales Bill',html)
            self.assertEqual(self.client.get('/billing/new?kind='+kind).status_code,200)
        self.assertEqual(self.client.get('/billing/source?kind=OTHER').status_code,400)
    def test_sales_and_anonymous_users_cannot_access_billing(self):
        self.assertEqual(self.client.get('/billing',follow_redirects=False).status_code,303)
        self.login('a')
        for url in ['/billing','/billing/source?kind=GST','/billing/new?kind=GST']:
            self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post('/billing/preview',data=self.form()).status_code,403)
    def test_preview_and_pdf_do_not_change_any_ledger_or_order(self):
        self.login()
        with SessionLocal() as db:
            before=(db.query(Activity).count(),db.query(AuditLog).count(),db.query(SalesOrder).count(),db.get(Client,1).outstanding_amount)
        for kind,company in [('GST','SHIVAM EXPORT'),('NON_GST','SHIVAM COSMETICS')]:
            r=self.client.post('/billing/preview',data=self.form(kind));self.assertEqual(r.status_code,200);self.assertIn(company,r.text);self.assertIn('DRAFT — NOT ISSUED',r.text);self.assertIn('data-download-form',r.text)
            pdf=self.client.post('/billing/preview',data=self.form(kind,output='pdf'))
            self.assertEqual(pdf.headers['content-type'],'application/pdf')
            content=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
            self.assertIn(company,content);self.assertIn('NOT ISSUED',content)
            if kind=='NON_GST':self.assertNotIn('24AJFPD0113P2ZK',content);self.assertNotIn('IGST',content)
        with SessionLocal() as db:self.assertEqual(before,(db.query(Activity).count(),db.query(AuditLog).count(),db.query(SalesOrder).count(),db.get(Client,1).outstanding_amount))
    def test_csrf_and_validation_reject_without_writes(self):
        self.login();self.assertEqual(self.client.post('/billing/preview',data=self.form(csrf='bad')).status_code,403)
        for bad in [dict(customer_name=''),dict(customer_address=''),dict(state_code='99'),dict(customer_gstin='BAD'),dict(due_date='2026-11-01'),{'qty_ES-01':'1.5'},{'hsn_ES-01':'bad'},{'qty_FAKE':'1'},{'gst_ES-01':'NaN'},{'rate_ES-01':'Infinity'}]:
            self.assertEqual(self.client.post('/billing/preview',data=self.form(**bad)).status_code,400,bad)
    def test_order_snapshots_prefill_and_customer_mismatch_denied(self):
        self.login()
        with SessionLocal.begin() as db:
            a=Activity(client_id=1,activity_type='ORDER',created_by=2);db.add(a);db.flush()
            o=SalesOrder(activity_id=a.id,order_number='QA-ORDER',total_amount=Decimal('1180'),delivery_address='Order address');db.add(o);db.flush();oid=o.id
            db.add(OrderLine(order_id=oid,sku='ES-01',name='Historic product name',quantity=2,mrp=Decimal('1180'),discount_percent=Decimal('50'),amount=Decimal('1180')))
        html=self.client.get('/billing/new?kind=GST&order_id='+str(oid)).text
        self.assertIn('QA-ORDER',html);self.assertIn('Historic product name',html);self.assertIn('Order address',html)
        response=self.client.post('/billing/preview',data=self.form(order_id=str(oid),client_id='2'))
        self.assertEqual(response.status_code,400)
        good=self.client.post('/billing/preview',data=self.form(order_id=str(oid)))
        self.assertEqual(good.status_code,200);self.assertIn('Historic product name',good.text)
    def test_html_values_are_escaped_in_preview(self):
        self.login();response=self.client.post('/billing/preview',data=self.form(customer_name='<script>alert(1)</script>'))
        self.assertNotIn('<script>alert(1)</script>',response.text);self.assertIn('&lt;script&gt;',response.text)


del OperationsTests
