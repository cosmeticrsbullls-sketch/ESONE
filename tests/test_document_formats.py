import json
import unittest
from decimal import Decimal
from test_operations import OperationsTests
from database.db import SessionLocal
from database.models import Client, CollectionActivity, DocumentImport, SalesOrder
from modules.invoice_parser import parse_invoice
from modules.workflows import now

class InvoiceParserTests(unittest.TestCase):
    def test_items_and_balance_labels_remain_distinct(self):
        parsed=parse_invoice('''Tax Invoice
Bill To
TEST CLIENT
TEST ADDRESS
Contact No. : 9999999999
Transportation Details
Invoice No. : TEST/26/1
Date : 07-10-2026
Due Date : 06-11-2026
1 TEST SHAMPOO 1LTR 1,999.00 2 Pcs 600.00 1,200.00
2 TEST SERUM 50ML 799.00 3 Pcs 320.00 960.00
Sub Total 2,160.00
Total 2,160.00
Received 160.00
Balance 2,000.00
Previous Balance 3,000.00
Current Balance 5,000.00
Payment mode
Credit''')
        self.assertEqual(parsed['total'],'2160.00')
        self.assertEqual(parsed['current_balance'],'5000.00')
        self.assertEqual(parsed['document_date'],'2026-10-07')
        self.assertEqual(len(parsed['items']),2)
        self.assertEqual(parsed['total_quantity'],'5')
        self.assertEqual(parsed['warnings'],[])
        self.assertEqual(parsed['tax_lines'],[])
    def test_image_header_columns_do_not_confuse_dates_or_customer(self):
        parsed=parse_invoice('''Bill To Transportation Details Invoice Details
TEST CLIENT Transport Name: Invoice No. : TEST/26/2
TEST ADDRESS Vehicle Number: Due   Date : 06-11-2026
TEST CITY Delivery Date: Date : 07-10-2026
Contact No. : 9999999999 Delivery Location:
Total 100.00''')
        self.assertEqual(parsed['reference'],'TEST/26/2')
        self.assertEqual(parsed['customer_name'],'TEST CLIENT')
        self.assertEqual(parsed['customer_address'],'TEST ADDRESS\nTEST CITY')
        self.assertEqual(parsed['document_date'],'2026-10-07')
        self.assertEqual(parsed['due_date'],'2026-11-06')

    def test_mismatch_requires_review(self):
        parsed=parse_invoice('1 TEST 100.00 2 Pcs 50.00 90.00\nSub Total 100.00\nTotal 100.00\nReceived 10.00\nBalance 100.00')
        self.assertGreaterEqual(len(parsed['warnings']),3)

class BalanceImportTests(unittest.TestCase):
    setUpClass=classmethod(OperationsTests.setUpClass.__func__)
    setUp=OperationsTests.setUp
    tearDown=OperationsTests.tearDown
    login=OperationsTests.login
    def stage(self):
        records=[dict(sheet='TEST',row=4,customer_name='TEST CUSTOMER',area='TEST AREA',phone='9999999999',reference='TEST-1',document_date='2026-09-01',bill_amount='1000',outstanding='600',remarks='')]
        with SessionLocal.begin() as db:
            entry=DocumentImport(created_by=1,kind='BALANCE_SHEET',digest='a'*64,filename='test.xlsx',media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',original=b'test-original',extracted_text=json.dumps(dict(format='OUTSTANDING_SHEET',records=records,warnings=[],ignored_summary_rows=1,total_outstanding='600')),created_at=now())
            db.add(entry);db.flush();identity=entry.id
        return identity
    def test_opening_balances_do_not_invent_receipts(self):
        self.login();identity=self.stage();url=f'/imports/{identity}'
        self.assertIn('not a payment receipt',self.client.get(url).text)
        data=dict(csrf=self.csrf,selected=['0'],client_id=['1'],reference=['TEST-1'],balance=['600'],adjust_balance='yes',confirmed='yes')
        self.assertEqual(self.client.post(url+'/balances',data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.client.post(url+'/balances',data=data,follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.query(SalesOrder).count(),1)
            self.assertEqual(db.get(Client,1).outstanding_amount,600)
            self.assertEqual(db.query(CollectionActivity).count(),1) # fixture only, no invented receipts
            reviewed=json.loads(db.get(DocumentImport,identity).reviewed_data)
            self.assertEqual(reviewed['records'][0]['unallocated_reduction'],'400')
    def test_unmatched_and_invalid_balance_do_not_partially_write(self):
        self.login();identity=self.stage();url=f'/imports/{identity}/balances'
        base=dict(csrf=self.csrf,selected=['0'],client_id=[''],reference=['TEST-1'],balance=['600'],confirmed='yes')
        self.assertEqual(self.client.post(url,data=base).status_code,400)
        self.assertEqual(self.client.post(url,data={**base,'create_missing':'yes','balance':['NaN']}).status_code,400)
        with SessionLocal() as db:self.assertEqual(db.query(SalesOrder).count(),0);self.assertEqual(db.query(Client).count(),3)
        self.assertEqual(self.client.post(url,data={**base,'create_missing':'yes'},follow_redirects=False).status_code,303)
        with SessionLocal() as db:
            self.assertEqual(db.query(Client).count(),4)
            self.assertEqual(db.query(Client).filter_by(phone='9999999999').one().outstanding_amount,0)
