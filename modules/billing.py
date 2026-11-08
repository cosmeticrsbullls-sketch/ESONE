"""Command Center billing preview. No invoice issuance or ledger writes."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from io import BytesIO
import re
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from database.db import SessionLocal
from database.models import Client, SalesOrder, OrderLine
from modules.catalog import CATALOG
from modules.operations import access, business_today
from modules.workflows import hidden, page
from modules.team import staff_access

router=APIRouter()
PENNY=Decimal('.01')
COMPANIES={
 'GST':dict(name='SHIVAM EXPORT',gstin='24AJFPD0113P2ZK',address='D/202, DEVNANDAN PARK SOCIETY, OPP. HARIOM VILLA BUNGLOWS, AHMEDABAD-382350',bank='KOTAK MAHINDRA BANK LIMITED, GURUKUL BRANCH',account='8000240012',ifsc='KKBK0002602'),
 'NON_GST':dict(name='SHIVAM COSMETICS',gstin='',address='D/33, UTTAMNAGAR, NR. KOTHIYA HOSPITAL, THAKKARNAGAR-NIKOL ROAD, NIKOL, AHMEDABAD-382350',bank='INDUSIND BANK, MANINAGAR',account='257567240012',ifsc='INDB0000175')}
# Starting values from the supplied sample, editable for office review.
SAMPLE_GST={sku:('5' if sku in {'ES-08','ES-10','ES-12'} else '18') for sku,_,_ in CATALOG}
STATE_CODES={'01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','26','27','29','30','31','32','33','34','35','36','37','38'}
CSS='''<style>.billing-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin:24px 0}.billing-options a{display:grid;gap:10px;min-height:140px;padding:24px;border:1px solid #d6b56c;border-radius:14px;background:#fff8e8;text-decoration:none}.billing-options strong{font-size:24px}.billing-preview{border:1px solid #d9dfe6;padding:24px;border-radius:12px}.billing-draft{color:#986a16;font-weight:700}.billing-lines input{min-width:90px;width:100%}.billing-summary{margin:20px 0 20px auto;max-width:400px}.billing-summary p{display:flex;justify-content:space-between;gap:20px}.billing-parties{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:600px){.billing-options,.billing-parties{grid-template-columns:1fr}.billing-preview{padding:12px}}@media print{.esone-sidebar,.esone-topbar,.billing-actions{display:none!important}.esone-app{padding:0!important}.esone-app main{margin:0!important}}</style>'''

def money(value):return f'{value:,.2f}'

def amount_words(value):
    ones=['Zero','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen']
    tens=['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety']
    def words(n):
        if n<20:return ones[n]
        if n<100:return tens[n//10]+(' '+words(n%10) if n%10 else '')
        for unit,label in [(10000000,'Crore'),(100000,'Lakh'),(1000,'Thousand'),(100,'Hundred')]:
            if n>=unit:return words(n//unit)+' '+label+(' '+words(n%unit) if n%unit else '')
    return words(int(value))+' Rupees Only'

def decimal(value,maximum='9999999999.99'):
    try:
        number=Decimal(str(value))
        if not number.is_finite() or number<0 or number>Decimal(maximum) or number!=number.quantize(PENNY):raise ValueError()
        return number
    except (InvalidOperation,ValueError):raise ValueError('Enter non-negative amounts with at most two decimal places.') from None

def calculate(lines,kind,state,received=Decimal(0)):
    if kind not in COMPANIES:raise ValueError('Choose GST or Non-GST.')
    if kind=='GST' and state not in STATE_CODES:raise ValueError('Choose a valid place-of-supply state code.')
    result=[]
    for row in lines:
        qty=row['quantity'];rate=decimal(row['rate']);discount=decimal(row['discount'],'100');tax_rate=decimal(row.get('gst','0'),'28') if kind=='GST' else Decimal(0)
        if isinstance(qty,bool) or not isinstance(qty,int) or not 1<=qty<=10000:raise ValueError('Quantity must be a whole number from 1 to 10000.')
        gross=rate*qty;net=(gross*(100-discount)/100).quantize(PENNY,rounding=ROUND_HALF_UP)
        taxable=(net*100/(100+tax_rate)).quantize(PENNY,rounding=ROUND_HALF_UP)
        tax=net-taxable;cgst=(tax/2).quantize(PENNY,rounding=ROUND_HALF_UP) if kind=='GST' and state=='24' else Decimal(0)
        sgst=tax-cgst if kind=='GST' and state=='24' else Decimal(0)
        result.append({**row,'rate':rate,'discount':discount,'gst':tax_rate,'gross':gross,'discount_amount':gross-net,'net':net,'taxable':taxable,'cgst':cgst,'sgst':sgst,'igst':tax if kind=='GST' and state!='24' else Decimal(0)})
    if not result:raise ValueError('Add at least one product.')
    totals={key:sum((row[key] for row in result),Decimal(0)) for key in ['gross','discount_amount','net','taxable','cgst','sgst','igst']}
    total=totals['net'].quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    received=decimal(received)
    if received>total:raise ValueError('Received amount cannot exceed the draft bill total.')
    totals.update(total=total,round_off=total-totals['net'],received=received,balance=total-received)
    return result,totals

@router.get('/billing',response_class=HTMLResponse)
def choose_kind(request:Request):
    denied=access(request)
    if denied is not None:return denied
    return page('Generate Sales Bill',CSS+'<p><a href="/command-center">← Command Center</a></p><div class="billing-options"><a href="/billing/source?kind=GST"><strong>GST</strong><span>SHIVAM EXPORT</span><small>Selling prices include GST</small></a><a href="/billing/source?kind=NON_GST"><strong>NON-GST</strong><span>SHIVAM COSMETICS</span><small>No GST charged</small></a></div>')

@router.get('/billing/source',response_class=HTMLResponse)
def choose_source(request:Request,kind:str=''):
    denied=access(request)
    if denied is not None:return denied
    if kind not in COMPANIES:return HTMLResponse('Choose GST or Non-GST.',400)
    with SessionLocal() as db:
        orders=db.query(SalesOrder).filter(SalesOrder.status=='PLACED').order_by(SalesOrder.id.desc()).limit(200).all()
        clients={c.id:c.business_name for c in db.query(Client).all()}
        from database.models import Activity
        rows=''
        for order in orders:
            a=db.get(Activity,order.activity_id)
            rows+=f'<tr><td>{escape(order.order_number or str(order.id))}</td><td>{escape(clients.get(a.client_id,""))}</td><td>₹{money(order.total_amount)}</td><td><a href="/billing/new?kind={kind}&amp;order_id={order.id}">Use this order</a></td></tr>'
    return page('Generate Sales Bill',CSS+f'<p><a href="/billing">← GST / Non-GST</a></p><h2>{COMPANIES[kind]["name"]}</h2><div class="billing-options"><a href="#sales-orders"><strong>From Sales Order</strong><span>Select an order below</span></a><a href="/billing/new?kind={kind}"><strong>New Sales Bill</strong><span>Create without a sales order</span></a></div><h2 id="sales-orders">Sales orders</h2><div class="table"><table><tr><th>Order</th><th>Customer</th><th>Order value</th><th>Action</th></tr>{rows or "<tr><td colspan=4>No placed orders available.</td></tr>"}</table></div>')


def source_order(db,order_id):
    from database.models import Activity
    order=db.get(SalesOrder,order_id) if order_id else None
    if order_id and (not order or order.status!='PLACED'):raise ValueError('Order is unavailable for billing preview.')
    a=db.get(Activity,order.activity_id) if order else None
    lines=db.query(OrderLine).filter_by(order_id=order.id).all() if order else []
    return order,a,lines

@router.get('/billing/new',response_class=HTMLResponse)
def new_bill(request:Request,kind:str='',order_id:int=0,client_id:int=0):
    denied=access(request)
    if denied is not None:return denied
    if kind not in COMPANIES:return HTMLResponse('Choose GST or Non-GST.',400)
    with SessionLocal() as db:
        try:order,a,lines=source_order(db,order_id)
        except ValueError as error:return HTMLResponse(escape(str(error)),404)
        if a:client_id=a.client_id
        clients=db.query(Client).order_by(Client.business_name).all();client=db.get(Client,client_id) if client_id else None
        options='<option value="">Select registered customer</option>'+''.join(f'<option value="{c.id}" data-name="{escape(c.business_name,quote=True)}" data-address="{escape(c.address or "",quote=True)}" data-phone="{escape(c.phone or "",quote=True)}" {"selected" if c.id==client_id else ""}>{escape(c.business_name)}</option>' for c in clients)
        if client_id and not client:return HTMLResponse('Customer not found.',404)
        items={row.sku:row for row in lines};catalog={sku:(name,Decimal(mrp)) for sku,name,mrp in CATALOG}
        for row in lines:catalog[row.sku]=(row.name,row.mrp)
        rows=''
        for sku,(name,mrp) in catalog.items():
            row=items.get(sku);qty=row.quantity if row else 0;rate=row.mrp if row else mrp;discount=row.discount_percent if row else 0
            tax=f'<td><input aria-label="HSN {escape(name)}" name="hsn_{sku}" value="3305" maxlength="8"></td><td><input aria-label="GST percent {escape(name)}" name="gst_{sku}" type="number" min="0" max="28" step="0.01" value="{SAMPLE_GST.get(sku,"18")}"></td>' if kind=='GST' else ''
            rows+=f'<tr><td>{escape(name)}</td><td>₹{money(mrp)}</td><td><input aria-label="Quantity {escape(name)}" name="qty_{sku}" type="number" min="0" max="10000" step="1" value="{qty}"></td><td><input aria-label="Unit price {escape(name)}" name="rate_{sku}" type="number" min="0" step="0.01" value="{rate}"></td><td><input aria-label="Discount percent {escape(name)}" name="discount_{sku}" type="number" min="0" max="100" step="0.01" value="{discount}"></td>{tax}</tr>'
        name=client.business_name if client else '';address=(order.delivery_address if order else '') or (client.address if client else '') or '';phone=client.phone if client else ''
        source=f'<p>Source order: {escape(order.order_number or str(order.id))}</p>' if order else '<p>Direct sales bill preview</p>'
    tax_fields='<label>Customer GSTIN (leave blank for unregistered customer)<input name="customer_gstin" maxlength="15"></label><label>Place of supply — state code<input name="state_code" pattern="[0-9]{2}" maxlength="2" placeholder="24 Gujarat / 23 Madhya Pradesh" required></label>' if kind=='GST' else ''
    form=f'''{CSS}<p><a href="/billing/source?kind={kind}">← Choose order / new bill</a></p><h2>{COMPANIES[kind]['name']}</h2>{source}<p class="billing-draft">Draft preview only · no invoice number assigned · no ledger entry</p><form method="post" action="/billing/preview">{hidden(request)}<input type="hidden" name="kind" value="{kind}"><input type="hidden" name="order_id" value="{order_id}"><label>Registered customer<select name="client_id" required>{options}</select></label><label>Billing name<input name="customer_name" maxlength="200" value="{escape(name,quote=True)}" required></label><label>Billing address<textarea name="customer_address" maxlength="1000" required>{escape(address)}</textarea></label><label>Contact number<input name="customer_phone" maxlength="20" value="{escape(phone or '',quote=True)}"></label>{tax_fields}<label>Bill date<input type="date" name="bill_date" value="{business_today()}" required></label><label>Due date<input type="date" name="due_date" value="{business_today()+timedelta(days=30)}" required></label><label>Transport name<input name="transport" maxlength="150"></label><label>Vehicle number<input name="vehicle" maxlength="30"></label><label>Delivery location<input name="delivery_location" maxlength="300"></label><label>Payment mode<select name="payment_mode"><option>Credit</option><option>Cash</option><option>Bank Transfer</option><option>UPI</option></select></label><div class="full table"><table class="billing-lines"><tr><th>Product</th><th>MRP</th><th>Qty</th><th>Unit price {'including GST' if kind=='GST' else ''}</th><th>Discount %</th>{'<th>HSN</th><th>GST %</th>' if kind=='GST' else ''}</tr>{rows}</table></div><p class="full">{'GST is extracted from the discounted selling price, not added again. HSN and GST rates start from your sample; review each product.' if kind=='GST' else 'No GST is charged on this draft.'}</p><label>Received amount (preview only)<input name="received" type="number" min="0" step="0.01" value="0"></label><label>Notes<textarea name="notes" maxlength="2000"></textarea></label><button>Preview Sales Bill</button></form>'''
    if not order_id:
        form+='''<script>(()=>{const picker=document.querySelector('select[name=client_id]');picker.addEventListener('change',()=>{const selected=picker.selectedOptions[0];for(const [field,key] of [['customer_name','name'],['customer_address','address'],['customer_phone','phone']])document.querySelector('[name='+field+']').value=selected.dataset[key]||'';});})();</script>'''
    return page('Sales Bill Draft',form)


def read_bill(form,db):
    kind=str(form.get('kind',''));state=str(form.get('state_code','')).strip() if kind=='GST' else ''
    if kind not in COMPANIES:raise ValueError('Choose GST or Non-GST.')
    try:cid=int(form.get('client_id','0'));oid=int(form.get('order_id','0'))
    except ValueError:raise ValueError('Select a valid customer or order.') from None
    client=db.get(Client,cid)
    if not client:raise ValueError('Customer not found.')
    order,a,source_lines=source_order(db,oid)
    if a and a.client_id!=cid:raise ValueError('The customer must match the selected order.')
    catalog={sku:(name,Decimal(mrp)) for sku,name,mrp in CATALOG}
    for row in source_lines:catalog[row.sku]=(row.name,row.mrp)
    for key in form.keys():
        if key.startswith('qty_') and key[4:] not in catalog:raise ValueError('Unknown product.')
    lines=[]
    for sku,(name,mrp) in catalog.items():
        try:
            raw=str(form.get('qty_'+sku,'0'));qty=int(raw)
            if not 0<=qty<=10000 or str(qty)!=raw:raise ValueError()
        except ValueError:raise ValueError('Enter whole-number quantities from 0 to 10000.') from None
        if not qty:continue
        hsn=str(form.get('hsn_'+sku,'')).strip()
        if kind=='GST' and not re.fullmatch(r'[0-9]{4}|[0-9]{6}|[0-9]{8}',hsn):raise ValueError('Enter a 4, 6 or 8 digit HSN for each selected product.')
        lines.append(dict(sku=sku,name=name,mrp=mrp,quantity=qty,rate=str(form.get('rate_'+sku,mrp)),discount=str(form.get('discount_'+sku,'0')),gst=str(form.get('gst_'+sku,'')),hsn=hsn if kind=='GST' else ''))
    data={}
    for key,limit in [('customer_name',200),('customer_address',1000),('customer_phone',20),('transport',150),('vehicle',30),('delivery_location',300),('notes',2000)]:
        value=str(form.get(key,'')).strip()
        if len(value)>limit:raise ValueError('Bill detail is too long.')
        data[key]=value
    if not data['customer_name'] or not data['customer_address']:raise ValueError('Billing name and address are required.')
    gstin=str(form.get('customer_gstin','')).strip().upper() if kind=='GST' else ''
    if gstin and (not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',gstin)):raise ValueError('Check the customer GSTIN format.')
    try:bill_date=date.fromisoformat(str(form.get('bill_date','')));due_date=date.fromisoformat(str(form.get('due_date','')))
    except ValueError:raise ValueError('Enter valid bill and due dates.') from None
    if due_date<bill_date:raise ValueError('Due date cannot be before bill date.')
    mode=str(form.get('payment_mode','Credit'))
    if mode not in {'Credit','Cash','Bank Transfer','UPI'}:raise ValueError('Choose a valid payment mode.')
    lines,totals=calculate(lines,kind,state,str(form.get('received','0')))
    return dict(**data,kind=kind,state=state,company=COMPANIES[kind],customer_gstin=gstin,bill_date=str(bill_date),due_date=str(due_date),order_id=oid,order_number=order.order_number if order else '',client_id=cid,payment_mode=mode,lines=lines,totals=totals,existing_outstanding=client.outstanding_amount or Decimal(0))


def preview_html(data):
    d=data;c=d['company'];t=d['totals'];gst=d['kind']=='GST'
    headers=['Product']+([] if gst else ['MRP'])+['Qty','Unit','Unit price','Discount %']+(['HSN','GST %','Taxable','CGST','SGST','IGST'] if gst else [])+['Amount']
    rows=''
    for row in d['lines']:
        cells=[row['name']]+([] if gst else [money(row['mrp'])])+[row['quantity'],'Pcs',money(row['rate']),str(row['discount'])]+([row['hsn'],str(row['gst']),money(row['taxable']),money(row['cgst']),money(row['sgst']),money(row['igst'])] if gst else [])+[money(row['net'])]
        rows+='<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in cells)+'</tr>'
    summary=[('Before discount',t['gross']),('Discount',t['discount_amount'])]+([('Taxable value',t['taxable']),('CGST',t['cgst']),('SGST',t['sgst']),('IGST',t['igst'])] if gst else [])+[('Subtotal',t['net']),('Round off',t['round_off']),('Total',t['total']),('Received (preview)',t['received']),('Bill balance',t['balance']),('Existing outstanding',d['existing_outstanding']),('Projected outstanding',d['existing_outstanding']+t['balance'])]
    return f'''<div class="billing-preview"><p class="billing-draft">DRAFT — NOT ISSUED</p><h2>{c['name']}</h2><p>{escape(c['address'])}<br>Phone: 7567240012 · s.shivamexport@gmail.com{('<br>GSTIN: '+c['gstin']) if gst else ''}</p><div class="billing-parties"><div><h3>Bill To</h3><strong>{escape(d['customer_name'])}</strong><p>{escape(d['customer_address'])}<br>{escape(d['customer_phone'])}{('<br>GSTIN: '+d['customer_gstin']) if d['customer_gstin'] else ''}</p></div><div><p>Bill date: {d['bill_date']}<br>Due date: {d['due_date']}<br>Source order: {escape(d['order_number'] or 'Direct bill')}<br>Place of supply state: {escape(d['state'] or '—')}<br>Payment mode: {d['payment_mode']}</p><p>Transport: {escape(d['transport'])}<br>Vehicle: {escape(d['vehicle'])}<br>Delivery: {escape(d['delivery_location'])}</p></div></div><div class="table"><table><tr>{''.join('<th>'+h+'</th>' for h in headers)}</tr>{rows}</table></div><div class="billing-summary">{''.join('<p><span>'+label+'</span><strong>₹'+money(value)+'</strong></p>' for label,value in summary)}</div><p><strong>Amount in words:</strong> {amount_words(t['total'])}</p><p>Bank: {c['bank']}<br>Account: {c['account']} · IFSC: {c['ifsc']}</p><p>{escape(d['notes'])}</p><p class="billing-draft">Preview only. No invoice number, payment receipt or outstanding entry has been created.</p></div>'''

@router.post('/billing/preview')
async def preview(request:Request):
    denied=access(request)
    if denied is not None:return denied
    form=await request.form();denied=staff_access(request,str(form.get('csrf','')))
    if denied is not None:return denied
    try:
        with SessionLocal() as db:data=read_bill(form,db)
    except (ValueError,InvalidOperation) as error:return HTMLResponse(page('Check Bill Details','<p>'+escape(str(error))+'</p><p>Use browser Back to correct your draft.</p>'),400)
    if str(form.get('output',''))=='pdf':return Response(bill_pdf(data),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="ESONE_draft_sales_bill.pdf"','Cache-Control':'no-store'})
    controls='<div class="billing-actions"><p>Review this draft before invoice issuance is enabled.</p><p>Your browser saves the PDF in Downloads.</p><form method="post" action="/billing/preview" data-download-form>'+''.join(f'<input type="hidden" name="{escape(str(k),quote=True)}" value="{escape(str(v),quote=True)}">' for k,v in form.multi_items() if k!='output')+'<button name="output" value="pdf">Download Draft PDF</button></form><p>Use browser Back to edit this preview.</p></div>'
    return HTMLResponse(page('Sales Bill Preview',CSS+preview_html(data)+controls),headers={'Cache-Control':'no-store'})


def bill_pdf(data):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from modules.pdf_reports import pdfmetrics  # Register the shared multilingual report font.
    buffer=BytesIO();styles=getSampleStyleSheet()
    for style in styles.byName.values():style.fontName='ESONE';style.shaping=1
    styles['BodyText'].fontSize=8;styles['BodyText'].leading=11
    def cell(value):return Paragraph(escape(str(value)),styles['BodyText'])
    c=data['company'];gst=data['kind']=='GST';t=data['totals']
    story=[Paragraph('DRAFT — NOT ISSUED',styles['Title']),Paragraph(c['name'],styles['Heading1']),cell(c['address']),cell('7567240012 | s.shivamexport@gmail.com')]
    if gst:story.append(cell('GSTIN: '+c['gstin']))
    story += [Spacer(1,14),cell('Bill To: '+data['customer_name']),cell(data['customer_address']),cell('Phone: '+data['customer_phone']+(' | GSTIN: '+data['customer_gstin'] if data['customer_gstin'] else '')),cell('Date: '+data['bill_date']+' | Due: '+data['due_date']+' | Place of supply: '+(data['state'] or '—')),cell('Source order: '+(data['order_number'] or 'Direct bill')),cell('Transport: '+data['transport']+' | Vehicle: '+data['vehicle']+' | Delivery: '+data['delivery_location']),Spacer(1,14)]
    headers=['Product']+([] if gst else ['MRP'])+['Qty','Unit','Rate incl. GST' if gst else 'Rate','Disc %']+(['HSN','GST %','Taxable','CGST','SGST','IGST'] if gst else [])+['Amount']
    rows=[[cell(h) for h in headers]]
    for row in data['lines']:
        values=[row['name']]+([] if gst else [money(row['mrp'])])+[row['quantity'],'Pcs',money(row['rate']),row['discount']]+([row['hsn'],row['gst'],money(row['taxable']),money(row['cgst']),money(row['sgst']),money(row['igst'])] if gst else [])+[money(row['net'])]
        rows.append([cell(v) for v in values])
    size=landscape(A4) if gst else A4;width=size[0]-56;weights=([3.4,.45,.45,.9,.6,.65,.55,1,.85,.85,.85,1] if gst else [3.4,.9,.45,.45,.9,.6,1]);table=Table(rows,colWidths=[width*w/sum(weights) for w in weights],repeatRows=1,splitInRow=1)
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.HexColor('#dddddd')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee4cc')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story += [table,Spacer(1,14)]
    summary_start=len(story)
    for label,key in [('Taxable value','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),('Subtotal','net'),('Round off','round_off'),('Total','total'),('Received (preview)','received'),('Balance','balance')]:
        if not gst and key in {'taxable','cgst','sgst','igst'}:continue
        story.append(cell(label+': INR '+money(t[key])))
    story += [cell('Amount in words: '+amount_words(t['total'])),cell('Existing outstanding: INR '+money(data['existing_outstanding'])),cell('Projected outstanding: INR '+money(data['existing_outstanding']+t['balance'])),cell('Payment mode: '+data['payment_mode']),Spacer(1,12),cell('Bank: '+c['bank']),cell('Account: '+c['account']+' | IFSC: '+c['ifsc']),cell(data['notes']),Spacer(1,12),cell('Preview only. No invoice number, payment receipt or ledger entry has been created.')]
    story[summary_start:]=[KeepTogether(story[summary_start:])]
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawString(28,18,'ESONE | DRAFT — NOT ISSUED');canvas.drawRightString(size[0]-28,18,'Page '+str(doc.page))
    SimpleDocTemplate(buffer,pagesize=size,leftMargin=28,rightMargin=28,topMargin=28,bottomMargin=35).build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
