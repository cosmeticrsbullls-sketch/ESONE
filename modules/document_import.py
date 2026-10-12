"""Bounded local OCR, original retention, reviewed and atomic ledger imports."""
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, CollectionActivity, DocumentImport, SalesOrder
from modules.operations import access
from modules.workflows import guard, hidden, now, page

router=APIRouter()
MAX_BYTES=10*1024*1024

def extract_document(data):
    """No external document transfer. Limits prevent oversized OCR workloads."""
    if data.startswith(b'%PDF-'):
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted or not 1<=len(reader.pages)<=20:raise ValueError('Use an unencrypted PDF with at most 20 pages.')
        text='\n'.join(p.extract_text() or '' for p in reader.pages)
        if len(text.strip())>=30:return text[:100000],'application/pdf'
        if not shutil.which('pdftoppm') or not shutil.which('tesseract'):raise ValueError('Scanned PDF OCR needs server OCR setup. Use a text PDF meanwhile.')
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.pdf';source.write_bytes(data)
            subprocess.run(['pdftoppm','-scale-to','2000','-png',str(source),str(Path(directory)/'page')],check=True,timeout=45,capture_output=True)
            texts=[ocr_image(p) for p in sorted(Path(directory).glob('page-*.png'))]
            return '\n'.join(texts)[:100000],'application/pdf'
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {'JPEG','PNG','WEBP'} or image.width*image.height>20000000:raise ValueError('Use JPEG, PNG or WebP up to 20 megapixels.')
        image.load()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image.png';image.convert('RGB').save(path)
            return ocr_image(path),'image/'+({'JPEG':'jpeg','PNG':'png','WEBP':'webp'}[image.format])

def ocr_image(path):
    if not shutil.which('tesseract'):raise ValueError('Photo OCR needs administrator server setup. Use a text PDF meanwhile.')
    result=subprocess.run(['tesseract',str(path),'stdout','-l','eng'],check=True,capture_output=True,timeout=30)
    return result.stdout.decode('utf-8',errors='replace')[:100000]

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
    return HTMLResponse(page('Import bills and collections',f'<p>Capture or upload a document, review the extracted text and ledger fields, then confirm. No ledger entries are created before confirmation.</p><form method="post" enctype="multipart/form-data">{hidden(request)}<label>Document type<select name="kind"><option value="BILL">Bill</option><option value="COLLECTION">Previous collection</option></select></label><label>Capture photo<input type="file" name="photo" accept="image/*" capture="environment"></label><label>Or upload image / PDF<input type="file" name="document" accept="image/jpeg,image/png,image/webp,application/pdf"></label><button>Extract and review</button></form>{rows}'))

@router.post('/imports')
async def upload(request:Request,kind:str=Form(...),csrf:str=Form(...),photo:UploadFile|None=File(None),document:UploadFile|None=File(None)):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if kind not in {'BILL','COLLECTION'}:return HTMLResponse('Invalid document type',400)
    selected=photo if photo and photo.filename else document
    if not selected or not selected.filename:return HTMLResponse('Choose a photo or document.',400)
    data=await selected.read(MAX_BYTES+1);await selected.close()
    if not data or len(data)>MAX_BYTES:return HTMLResponse('Document must be between 1 byte and 10 MB.',400)
    digest=hashlib.sha256(data).hexdigest()
    with SessionLocal() as db:
        existing=db.query(DocumentImport).filter_by(digest=digest).first()
        if existing:return RedirectResponse(f'/imports/{existing.id}',303)
    from starlette.concurrency import run_in_threadpool
    try:text,media=await run_in_threadpool(extract_document,data)
    except Exception:
        # Parser errors must never expose document content or filesystem paths.
        return HTMLResponse(page('Extraction unavailable','<p>This file could not be read. Use a clear JPEG/PNG/WebP or unencrypted text PDF up to 20 pages. Photo/scanned PDF processing requires the server OCR runtime.</p>'),422)
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
        reference,amount=suggestions(entry.extracted_text)
        clients=db.query(Client).order_by(Client.business_name).all()
        options=''.join(f'<option value="{c.id}">{escape(c.business_name)} — {escape(c.phone or "")}</option>' for c in clients)
        form='' if entry.status=='CONFIRMED' else f'''<form method="post">{hidden(request)}<label>Match registered client<select name="client_id" required><option value="">Select client</option>{options}</select></label><label>Invoice / receipt reference<input name="reference" maxlength="50" value="{escape(reference,quote=True)}" required></label><label>Document date<input name="document_date" type="date" required></label><label>Total amount<input name="amount" type="number" min="0.01" max="9999999999.99" step="0.01" value="{escape(amount,quote=True)}" required></label><label>For collection: existing ESONE bill ID<input name="bill_id" type="number" min="1"></label><label>Payment mode<input name="payment_mode" maxlength="30"></label><label>Reviewed details / line items / taxes<textarea name="details" maxlength="100000">{escape(entry.extracted_text)}</textarea></label><label><input type="checkbox" name="adjust_balance" value="yes">Update current outstanding balance (leave unchecked when this history is already included in the current balance).</label><label><input type="checkbox" name="confirmed" value="yes" required>I checked the client, amount, date and all details against the original document.</label><button>Confirm and add to ledger</button></form>'''
        return HTMLResponse(page('Review document',f'<p>{escape(entry.filename)} · {entry.kind} · {entry.status}</p><a href="/imports/{identity}/original">Download original</a><details><summary>Extracted text</summary><pre style="white-space:pre-wrap">{escape(entry.extracted_text)}</pre></details>{form}'))

@router.get('/imports/{identity}/original')
def original(identity:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        entry=db.get(DocumentImport,identity)
        if not entry:return HTMLResponse('Not found',404)
        return Response(entry.original,media_type=entry.media_type,headers={'Content-Disposition':'attachment; filename="esone-document"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.post('/imports/{identity}')
def confirm(identity:int,request:Request,csrf:str=Form(...),client_id:int=Form(...),reference:str=Form(...),document_date:str=Form(...),amount:str=Form(...),bill_id:str=Form(''),payment_mode:str=Form(''),details:str=Form(''),confirmed:str=Form(''),adjust_balance:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    from datetime import date
    try:
        value=Decimal(amount)
        if not value.is_finite() or value<=0 or value>Decimal('9999999999.99') or value!=value.quantize(Decimal('.01')):raise ValueError()
        date.fromisoformat(document_date)
        if confirmed!='yes' or not reference.strip() or len(reference)>50 or len(details)>100000 or len(payment_mode)>30:raise ValueError()
        linked=int(bill_id) if bill_id else None
    except (ValueError,InvalidOperation):return HTMLResponse('Check amount, date, reference and confirmation.',400)
    with SessionLocal.begin() as db:
        entry=db.query(DocumentImport).filter_by(id=identity).with_for_update().first()
        if not entry:return HTMLResponse('Not found',404)
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
        if entry.kind=='BILL':
            db.add(SalesOrder(activity_id=activity.id,order_number=reference.strip(),order_source='EXTERNAL_BILLING',status='IMPORTED',subtotal=value,discount_amount=0,total_amount=value))
            if adjust_balance=='yes':client.outstanding_amount=(client.outstanding_amount or Decimal(0))+value
        else:
            db.add(CollectionActivity(activity_id=activity.id,channel='DOCUMENT_IMPORT',outcome='RECEIVED',amount_received=value,payment_mode=payment_mode,payment_reference=reference.strip(),accounts_status='VERIFIED',accounts_verified_at=now()))
            if adjust_balance=='yes':client.outstanding_amount=(client.outstanding_amount or Decimal(0))-value
        entry.status='CONFIRMED';entry.confirmed_at=now();entry.activity_id=activity.id
        entry.reviewed_data=json.dumps(dict(client_id=client_id,reference=reference.strip(),document_date=document_date,amount=str(value),bill_id=linked,payment_mode=payment_mode,details=details,adjust_balance=adjust_balance=='yes'))
        db.add(AuditLog(user_id=request.session['user_id'],entity_type='DOCUMENT_IMPORT',entity_id=identity,action='CONFIRM',new_value=entry.reviewed_data))
    return RedirectResponse(f'/imports/{identity}',303)
