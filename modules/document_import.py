"""Bounded local OCR, original retention, reviewed and atomic ledger imports."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, CollectionActivity, DocumentImport, SalesOrder
from modules.operations import access
from modules.invoice_parser import parse_invoice
from modules.workflows import guard, hidden, now, page

router=APIRouter()
MAX_BYTES=10*1024*1024

def extract_document(data):
    from modules.photo_ocr import extract
    return extract(data)


def suggestions(text):
    number=re.search(r'(?:invoice|bill|receipt)\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9/\-]+)',text,re.I)
    totals=re.findall(r'(?:grand total|net total|amount received|total amount|total)\s*[:₹Rs.\s]*([\d,]+\.\d{2}|[\d,]+)',text,re.I)
    return (number.group(1) if number else '',totals[-1].replace(',','') if totals else '')

@router.get('/imports',response_class=HTMLResponse)
def imports(request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        entries=db.query(DocumentImport).order_by(DocumentImport.id.desc()).limit(50).all()
        rows=''.join(f'<p><a href="/imports/{d.id}">{escape(d.filename)}</a> · {d.status}</p>' for d in entries)
    return HTMLResponse(page('Import bills and collections',f'<p>Capture or upload a document, review the extracted text and ledger fields, then confirm. No ledger entries are created before confirmation.</p><form method="post" enctype="multipart/form-data" onsubmit="this.querySelector(&quot;button&quot;).textContent=&quot;Processing document...&quot;;this.querySelector(&quot;button&quot;).disabled=true;">{hidden(request)}<label>Document type<select name="kind"><option value="BILL">Bill</option><option value="COLLECTION">Previous collection receipt</option><option value="BALANCE_SHEET">Outstanding bill Excel sheet</option></select></label><label>Capture photo<input type="file" name="photo" accept="image/*" capture="environment"></label><label>Or upload image / PDF<input type="file" name="document" accept="image/jpeg,image/png,image/webp,application/pdf,.xlsx"></label><button>Extract and review</button></form>{rows}'))

@router.post('/imports')
async def upload(request:Request,kind:str=Form(...),csrf:str=Form(...),photo:UploadFile|None=File(None),document:UploadFile|None=File(None)):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if kind not in {'BILL','COLLECTION','BALANCE_SHEET'}:return HTMLResponse('Invalid document type',400)
    selected=photo if photo and photo.filename else document
    if not selected or not selected.filename:return HTMLResponse('Choose a photo or document.',400)
    limit=25*1024*1024 if kind=='BALANCE_SHEET' else MAX_BYTES
    data=await selected.read(limit+1);await selected.close()
    if not data or len(data)>limit:return HTMLResponse('Use files up to 10 MB, or outstanding Excel files up to 25 MB.',400)
    digest=hashlib.sha256(data).hexdigest()
    with SessionLocal() as db:
        existing=db.query(DocumentImport).filter_by(digest=digest).first()
        if existing:return RedirectResponse(f'/imports/{existing.id}',303)
    from starlette.concurrency import run_in_threadpool
    try:
        if kind=='BALANCE_SHEET':
            from modules.collection_sheet import parse_collection_sheet
            text=json.dumps(await run_in_threadpool(parse_collection_sheet,data));media='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:text,media=await run_in_threadpool(extract_document,data)
    except Exception as error:
        from modules.photo_ocr import ExtractionError
        if isinstance(error,ExtractionError):return HTMLResponse(page('Document processing',f'<p>{escape(str(error))}</p>'),422)
        # Parser errors must never expose document content or filesystem paths.
        return HTMLResponse(page('Extraction unavailable','<p>This file could not be read. Use a clear JPEG/PNG/WebP or unencrypted text PDF up to 20 pages. Upload outstanding Excel files up to 25 MB, or photos/text PDFs up to 10 MB.</p>'),422)
    if not text.strip():return HTMLResponse('No text detected. Upload a clearer document.',422)
    try:
        with SessionLocal.begin() as db:
            entry=DocumentImport(created_by=request.session['user_id'],kind=kind,digest=digest,filename=Path(selected.filename).name[:200],media_type=media,original=data,extracted_text=text,created_at=now())
            db.add(entry);db.flush();identity=entry.id
            db.add(AuditLog(user_id=request.session['user_id'],entity_type='DOCUMENT_IMPORT',entity_id=identity,action='UPLOAD'))
    except IntegrityError:
        with SessionLocal() as db:identity=db.query(DocumentImport).filter_by(digest=digest).one().id
    return RedirectResponse(f'/imports/{identity}',303)

@router.get('/imports/{identity}',response_class=HTMLResponse)
def review(identity:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        entry=db.get(DocumentImport,identity)
        if not entry:return HTMLResponse('Not found',404)
        if entry.kind=='BALANCE_SHEET':
            from modules.balance_import import balance_review
            return balance_review(entry,request,db)
        parsed=parse_invoice(entry.extracted_text)
        reference,amount=suggestions(entry.extracted_text)
        reference=parsed.get('reference',reference)
        amount=parsed.get('total',amount) if entry.kind=='BILL' else amount
        item_rows=''.join('<tr>'+''.join(f'<td><input aria-label="{label}" name="item_{key}" value="{escape(str(item[key]),quote=True)}" required></td>' for key,label in [('name','Item'),('mrp','MRP'),('quantity','Quantity'),('unit','Unit'),('rate','Rate'),('amount','Amount')])+'<td><button type="button" onclick="this.closest(\'tr\').remove()">Remove</button></td></tr>' for item in parsed['items']) if entry.kind=='BILL' else ''
        item_form=('<h3>Review item details</h3><div class="table"><table><thead><tr><th>Item</th><th>MRP</th><th>Quantity</th><th>Unit</th><th>Rate</th><th>Amount</th><th>Action</th></tr></thead><tbody id="invoice-items">'+item_rows+'</tbody></table></div><button type="button" onclick="addInvoiceItem()">Add missing item</button>') if entry.kind=='BILL' else ''
        item_form += """<script>function addInvoiceItem(){const row=document.createElement('tr');[['name','Item'],['mrp','MRP'],['quantity','Quantity'],['unit','Unit'],['rate','Rate'],['amount','Amount']].forEach(([key,label])=>{const cell=document.createElement('td');cell.dataset.label=label;const input=document.createElement('input');input.name='item_'+key;input.required=true;input.setAttribute('aria-label',label);cell.append(input);row.append(cell);});const cell=document.createElement('td');const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.onclick=()=>row.remove();cell.append(remove);row.append(cell);document.getElementById('invoice-items').append(row);row.querySelector('input').focus();}</script>""" if entry.kind=='BILL' else ''
        customer_note=f"<p>Extracted customer: {escape(parsed.get('customer_name','Not detected'))} · {escape(parsed.get('customer_phone',''))}</p><p>{escape(parsed.get('customer_address',''))}</p>"
        warnings=''.join(f'<p class="error">{escape(w)}</p>' for w in parsed['warnings'])
        if parsed.get('previous_balance'):
            customer_note+=f"<p>Previous balance: {parsed['previous_balance']} · Current balance: {parsed.get('current_balance','Not detected')}. These are cumulative balances, not new invoice amounts.</p>"
        if entry.kind=='BILL' and not parsed['tax_lines']:customer_note+='<p>Separate GST/tax amounts are not shown or detected. Verify the original; no tax rate will be assumed.</p>'
        bill_fields=(f'<label>Due date<input type="date" name="due_date" value="{escape(parsed.get("due_date",""),quote=True)}"></label><label>Amount already received for this invoice<input type="number" name="received" step="0.01" min="0" value="{parsed.get("received","0.00")}" required></label>'+item_form) if entry.kind=='BILL' else ''
        clients=db.query(Client).order_by(Client.business_name).all()
        options=''.join(f'<option value="{c.id}">{escape(c.business_name)} — {escape(c.phone or "")}</option>' for c in clients)
        form='' if entry.status=='CONFIRMED' else f'''<form method="post">{hidden(request)}<label>Match registered client<select name="client_id" required><option value="">Select client</option>{options}</select></label><label>Invoice / receipt reference<input name="reference" maxlength="50" value="{escape(reference,quote=True)}" required></label><label>Document date<input name="document_date" type="date" value="{parsed.get('document_date','')}" required></label><label>Total amount<input name="amount" type="number" min="0.01" max="9999999999.99" step="0.01" value="{escape(amount,quote=True)}" required></label>{bill_fields}<label>For collection: existing ESONE bill ID<input name="bill_id" type="number" min="1"></label><label>Payment mode<input name="payment_mode" maxlength="30" value="{escape(parsed.get('payment_mode',''),quote=True)}"></label><label>Reviewed details / line items / taxes<textarea name="details" maxlength="100000">{escape(entry.extracted_text)}</textarea></label><label><input type="checkbox" name="adjust_balance" value="yes">Update current outstanding balance (leave unchecked when this history is already included in the current balance).</label><label><input type="checkbox" name="confirmed" value="yes" required>I checked the client, amount, date and all details against the original document.</label><button>Confirm and add to ledger</button></form>'''
        if entry.status=='CONFIRMED':
            saved=json.loads(entry.reviewed_data)
            saved_rows=''.join('<tr>'+''.join(f'<td>{escape(str(item[key]))}</td>' for key in ['name','mrp','quantity','unit','rate','amount'])+'</tr>' for item in saved.get('items',[]))
            form=f'<h3>Saved reviewed record</h3><p>Invoice / receipt: {escape(saved["reference"])} · Date: {saved["document_date"]} · Amount: {saved["amount"]} · Received: {saved.get("received") or "Not specified"}</p>'
            if saved_rows:form+='<div class="table"><table><tr><th>Item</th><th>MRP</th><th>Quantity</th><th>Unit</th><th>Rate</th><th>Amount</th></tr>'+saved_rows+'</table></div>'
        return HTMLResponse(page('Review document',f'<p>{escape(entry.filename)} · {entry.kind} · {entry.status}</p><a href="/imports/{identity}/original">Download original</a><details><summary>Extracted text</summary><pre style="white-space:pre-wrap">{escape(entry.extracted_text)}</pre></details>{customer_note}{warnings}{form}'))

@router.get('/imports/{identity}/original')
def original(identity:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        entry=db.get(DocumentImport,identity)
        if not entry:return HTMLResponse('Not found',404)
        return Response(entry.original,media_type=entry.media_type,headers={'Content-Disposition':'attachment; filename="esone-document"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.post('/imports/{identity}')
def confirm(identity:int,request:Request,csrf:str=Form(...),client_id:int=Form(...),reference:str=Form(...),document_date:str=Form(...),amount:str=Form(...),bill_id:str=Form(''),payment_mode:str=Form(''),details:str=Form(''),confirmed:str=Form(''),adjust_balance:str=Form(''),due_date:str=Form(''),received:str=Form('0'),item_name:list[str]=Form([]),item_mrp:list[str]=Form([]),item_quantity:list[str]=Form([]),item_unit:list[str]=Form([]),item_rate:list[str]=Form([]),item_amount:list[str]=Form([])):
    denied=guard(request,csrf)
    if denied is not None:return denied
    from datetime import date
    try:
        value=Decimal(amount)
        if not value.is_finite() or value<=0 or value>Decimal('9999999999.99') or value!=value.quantize(Decimal('.01')):raise ValueError()
        date.fromisoformat(document_date)
        if confirmed!='yes' or not reference.strip() or len(reference)>50 or len(details)>100000 or len(payment_mode)>30:raise ValueError()
        linked=int(bill_id) if bill_id else None
        if due_date:date.fromisoformat(due_date)
        paid=Decimal(received)
        if not paid.is_finite() or paid<0 or paid>value or paid!=paid.quantize(Decimal('.01')):raise ValueError()
        columns=[item_name,item_mrp,item_quantity,item_unit,item_rate,item_amount]
        if len(item_name)>500 or any(len(c)!=len(item_name) for c in columns):raise ValueError()
        reviewed_items=[]
        for name,mrp,quantity,unit,rate,line_amount in zip(*columns):
            if not name.strip() or len(name)>300 or len(unit)>20:raise ValueError()
            nums=[Decimal(x.replace(',','')) for x in [mrp,quantity,rate,line_amount]]
            if any(not x.is_finite() or x<0 or x>Decimal('9999999999.99') for x in nums) or nums[1]<=0:raise ValueError()
            if any(x!=x.quantize(Decimal('.01')) for x in [nums[0],nums[2],nums[3]]):raise ValueError()
            reviewed_items.append(dict(name=name.strip(),mrp=str(nums[0]),quantity=str(nums[1]),unit=unit,rate=str(nums[2]),amount=str(nums[3])))
    except (ValueError,InvalidOperation):return HTMLResponse('Check amount, date, reference and confirmation.',400)
    with SessionLocal.begin() as db:
        entry=db.query(DocumentImport).filter_by(id=identity).with_for_update().first()
        if not entry:return HTMLResponse('Not found',404)
        if entry.kind=='BALANCE_SHEET':return HTMLResponse('Use the outstanding sheet review form.',400)
        if entry.status=='CONFIRMED':return RedirectResponse(f'/imports/{identity}',303)
        client=db.query(Client).filter_by(id=client_id).with_for_update().first()
        if not client:return HTMLResponse('Select a registered client',400)
        if entry.kind=='BILL':
            if db.query(SalesOrder).filter_by(order_number=reference.strip()).first():return HTMLResponse('This invoice reference already exists.',409)
        elif linked:
            bill=db.query(SalesOrder,Activity).join(Activity,Activity.id==SalesOrder.activity_id).filter(SalesOrder.id==linked,Activity.client_id==client_id).first()
            if not bill:return HTMLResponse('The linked bill does not belong to this client.',400)
        else:return HTMLResponse('Select the matching ESONE bill ID. Import the old bill first if required.',400)
        if entry.kind=='COLLECTION' and db.query(CollectionActivity).join(Activity,Activity.id==CollectionActivity.activity_id).filter(Activity.client_id==client_id,CollectionActivity.payment_reference==reference.strip()).first():return HTMLResponse('This collection reference already exists for the client.',409)
        activity=Activity(client_id=client_id,activity_type='SALES_ORDER' if entry.kind=='BILL' else 'COLLECTION',source='DOCUMENT_IMPORT',status='COMPLETED',completed_at=now(),created_by=request.session['user_id'],title=reference.strip(),notes=details)
        db.add(activity);db.flush()
        initial_collection_id=None
        if entry.kind=='BILL':
            db.add(SalesOrder(activity_id=activity.id,order_number=reference.strip(),order_source='EXTERNAL_BILLING',status='IMPORTED',subtotal=value,discount_amount=0,total_amount=value))
            if paid:
                receipt=Activity(client_id=client_id,activity_type='COLLECTION',source='DOCUMENT_IMPORT',status='COMPLETED',completed_at=now(),created_by=request.session['user_id'],parent_activity_id=activity.id,title='Payment recorded on imported invoice')
                db.add(receipt);db.flush();initial_collection_id=receipt.id
                db.add(CollectionActivity(activity_id=receipt.id,channel='DOCUMENT_IMPORT',outcome='RECEIVED',amount_received=paid,payment_mode=payment_mode,payment_reference=f'IMPORT-{identity}-RECEIVED',accounts_status='VERIFIED',accounts_verified_at=now()))
            if adjust_balance=='yes':client.outstanding_amount=(client.outstanding_amount or Decimal(0))+value-paid
        else:
            db.add(CollectionActivity(activity_id=activity.id,channel='DOCUMENT_IMPORT',outcome='RECEIVED',amount_received=value,payment_mode=payment_mode,payment_reference=reference.strip(),accounts_status='VERIFIED',accounts_verified_at=now()))
            if adjust_balance=='yes':client.outstanding_amount=(client.outstanding_amount or Decimal(0))-value
        entry.status='CONFIRMED';entry.confirmed_at=now();entry.activity_id=activity.id
        entry.reviewed_data=json.dumps(dict(client_id=client_id,reference=reference.strip(),document_date=document_date,amount=str(value),bill_id=linked,payment_mode=payment_mode,details=details,adjust_balance=adjust_balance=='yes',due_date=due_date,received=str(paid) if entry.kind=='BILL' else None,items=reviewed_items,extracted_fields=parse_invoice(entry.extracted_text),initial_collection_activity_id=initial_collection_id))
        db.add(AuditLog(user_id=request.session['user_id'],entity_type='DOCUMENT_IMPORT',entity_id=identity,action='CONFIRM',new_value=entry.reviewed_data))
    return RedirectResponse(f'/imports/{identity}',303)
