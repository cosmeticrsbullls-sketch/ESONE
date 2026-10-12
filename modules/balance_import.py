"""Review and import outstanding snapshots; never invent collection receipts."""
import json
from decimal import Decimal, InvalidOperation
from html import escape
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, DocumentImport, SalesOrder
from modules.workflows import guard, hidden, now, page

router=APIRouter()
def phone_key(value):
    digits=''.join(c for c in str(value or '') if c.isdigit())
    return digits[-10:] if len(digits) in (10,12) else digits

def balance_review(entry,request,db):
    source=json.loads(entry.extracted_text);records=source['records']
    if entry.status=='CONFIRMED':
        saved=json.loads(entry.reviewed_data)
        rows=''.join(f"<tr><td>{escape(r['source_row']['customer_name'])}</td><td>{escape(r['reference'])}</td><td>{r['document_date']}</td><td>{r['bill_amount']}</td><td>{r['outstanding']}</td></tr>" for r in saved['records'])
        return HTMLResponse(page('Outstanding import confirmed',f'<p>{len(saved["records"])} selected bills imported. {saved["unselected_rows"]} rows skipped. This file cannot be posted twice.</p><a href="/imports/{entry.id}/original">Download original sheet</a><div class="table"><table><tr><th>Client</th><th>Invoice</th><th>Date</th><th>Bill amount</th><th>Outstanding snapshot</th></tr>{rows}</table></div>'))
    clients=db.query(Client).order_by(Client.business_name).all()
    options=''.join(f'<option value="{c.id}">{escape(c.business_name)} — {escape(c.phone or "")}</option>' for c in clients)
    rows=''
    for index,record in enumerate(records):
        matches=[c for c in clients if phone_key(c.phone) and phone_key(c.phone)==phone_key(record['phone'])]
        if not matches:matches=[c for c in clients if c.business_name.strip().casefold()==record['customer_name'].casefold()]
        selected=matches[0].id if len(matches)==1 else None
        choices=options.replace(f'value="{selected}"',f'value="{selected}" selected',1) if selected else options
        rows+=f'''<tr><td><input type="checkbox" name="selected" value="{index}"></td><td>{escape(record['customer_name'])}<br>{escape(record['phone'])}<br>{escape(record['area'])}<br>Source: {escape(record['sheet'])}, row {record['row']}</td><td><select name="client_id"><option value="">New client / not matched</option>{choices}</select></td><td><input name="reference" maxlength="50" value="{escape(record['reference'],quote=True)}" required></td><td>{record['document_date']}</td><td>{record['bill_amount']}</td><td><input name="balance" type="number" min="0" step="0.01" value="{record['outstanding']}" required></td></tr>'''
    warnings=''.join(f'<p class="error">{escape(w)}</p>' for w in source['warnings'])
    return HTMLResponse(page('Review outstanding bills',f'''<p>{len(records)} bill rows. Detected outstanding: {source['total_outstanding']}. {source['ignored_summary_rows']} subtotal rows excluded.</p><p>This is an outstanding snapshot, not a payment receipt history. Review client matches and full invoice references, then select the rows to import.</p>{warnings}<form method="post" action="/imports/{entry.id}/balances">{hidden(request)}<div class="table"><table><tr><th>Import</th><th>Source customer</th><th>Registered client</th><th>Invoice reference</th><th>Bill date</th><th>Bill amount</th><th>Outstanding</th></tr>{rows}</table></div><label><input type="checkbox" name="create_missing" value="yes">Create registered clients for selected unmatched rows using the displayed name, phone and area.</label><label><input type="checkbox" name="adjust_balance" value="yes">Add these outstanding amounts to current client balances. Leave unchecked if the balances already include this history.</label><label><input type="checkbox" name="confirmed" value="yes" required>I reviewed selected rows, matches, invoice references and balances, and verified there are no business records beyond the scanned rows.</label><button>Confirm selected outstanding records</button></form>'''))

@router.post('/imports/{identity}/balances')
def confirm_balances(identity:int,request:Request,csrf:str=Form(...),selected:list[int]=Form([]),client_id:list[str]=Form([]),reference:list[str]=Form([]),balance:list[str]=Form([]),create_missing:str=Form(''),adjust_balance:str=Form(''),confirmed:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if confirmed!='yes' or not selected:return HTMLResponse('Review and select at least one row.',400)
    with SessionLocal.begin() as db:
        entry=db.query(DocumentImport).filter_by(id=identity).with_for_update().first()
        if not entry or entry.kind!='BALANCE_SHEET':return HTMLResponse('Outstanding sheet not found',404)
        if entry.status=='CONFIRMED':return RedirectResponse(f'/imports/{identity}',303)
        source=json.loads(entry.extracted_text);records=source['records'];indexes=sorted(set(selected))
        if any(len(v)!=len(records) for v in [client_id,reference,balance]) or any(i<0 or i>=len(records) for i in indexes):return HTMLResponse('Reload the complete review form.',400)
        # Validate the entire selection before writing anything; no partial imports.
        plan=[];refs=set()
        try:
            for index in indexes:
                row=records[index];ref=reference[index].strip();value=Decimal(balance[index]);total=Decimal(row['bill_amount'])
                if not ref or len(ref)>50 or ref in refs or not value.is_finite() or value<0 or value>total or total>Decimal('9999999999.99') or value!=value.quantize(Decimal('.01')):raise ValueError()
                refs.add(ref)
                if db.query(SalesOrder).filter_by(order_number=ref).first():return HTMLResponse('A selected invoice reference already exists. Unselect that row or correct the full reference.',409)
                cid=int(client_id[index]) if client_id[index] else None
                if cid and not db.get(Client,cid):raise ValueError()
                if not cid and (create_missing!='yes' or not row['customer_name'] or len(row['customer_name'])>200 or len(row['phone'])>20 or len(row['area'])>120):raise ValueError()
                plan.append((index,row,ref,value,total,cid))
        except (ValueError,InvalidOperation):return HTMLResponse('Check selected client matches, invoice references and balances. No records were added.',400)
        # Deterministic client lock order prevents cross-client import deadlocks.
        locked={cid:db.query(Client).filter_by(id=cid).with_for_update().one() for cid in sorted({p[5] for p in plan if p[5]})}
        created={};imported=[]
        for index,row,ref,value,total,cid in plan:
            if cid:client=locked[cid]
            else:
                key=(row['customer_name'].casefold(),phone_key(row['phone']))
                client=created.get(key)
                if client is None:
                    client=Client(business_name=row['customer_name'],phone=row['phone'],area=row['area'],client_type='OTHER',status='ACTIVE',created_by=request.session['user_id'],outstanding_amount=0)
                    db.add(client);db.flush();created[key]=client
                    db.add(AuditLog(user_id=request.session['user_id'],entity_type='CLIENT',entity_id=client.id,action='IMPORT_CREATE'))
            activity=Activity(client_id=client.id,activity_type='SALES_ORDER',source='OPENING_BALANCE_IMPORT',status='COMPLETED',created_by=request.session['user_id'],completed_at=now(),title=ref,notes='Imported historical bill and outstanding snapshot; payment receipt details unavailable.')
            db.add(activity);db.flush()
            order=SalesOrder(activity_id=activity.id,order_number=ref,order_source='EXTERNAL_BILLING',status='IMPORTED',subtotal=total,discount_amount=0,total_amount=total)
            db.add(order);db.flush()
            if adjust_balance=='yes':client.outstanding_amount=(client.outstanding_amount or Decimal(0))+value
            imported.append(dict(source_index=index,client_id=client.id,order_id=order.id,activity_id=activity.id,reference=ref,document_date=row['document_date'],bill_amount=str(total),outstanding=str(value),unallocated_reduction=str(total-value),source_row=row))
        entry.status='CONFIRMED';entry.confirmed_at=now();entry.reviewed_data=json.dumps(dict(records=imported,adjust_balance=adjust_balance=='yes',unselected_rows=len(records)-len(indexes)))
        db.add(AuditLog(user_id=request.session['user_id'],entity_type='DOCUMENT_IMPORT',entity_id=entry.id,action='CONFIRM_BALANCES',new_value=entry.reviewed_data))
    return RedirectResponse(f'/imports/{identity}',303)
