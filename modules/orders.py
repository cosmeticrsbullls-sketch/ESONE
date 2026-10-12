"""Sales order capture, immutable line-price snapshots and explicit WhatsApp actions."""
from html import escape
from secrets import token_urlsafe
from fastapi import APIRouter,Request,Form
from fastapi.responses import HTMLResponse,RedirectResponse
from database.db import SessionLocal
from database.models import User,Client,Activity,SalesOrder,OrderLine,CommunicationLog,AuditLog
from modules.catalog import CATALOG,price_lines
from modules.team import staff_access,MANAGEMENT
from modules.workflows import page,hidden,now,audit,clients_select,salon_field
from modules.pdf_reports import pdf_response,share_button,SHARE_SCRIPT
router=APIRouter()

def order_access(request):
    denied=staff_access(request)
    if denied is not None:return denied
    if request.session.get('role') not in MANAGEMENT|{'SALES'}:return HTMLResponse('Access Denied',403)

def permitted(request,a):return request.session.get('role') in MANAGEMENT or a.created_by==request.session['user_id']

@router.get('/orders',response_class=HTMLResponse)
def orders(request:Request):
    denied=order_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        query=db.query(SalesOrder,Activity,Client).join(Activity,Activity.id==SalesOrder.activity_id).join(Client,Client.id==Activity.client_id)
        if request.session.get('role') not in MANAGEMENT:query=query.filter(Activity.created_by==request.session['user_id'])
        rows=''.join(f'<tr><td><a href="/orders/{o.id}">{escape(o.order_number or str(o.id))}</a></td><td>{escape(c.business_name)}</td><td>₹{o.total_amount}</td><td>{escape(o.status)}</td></tr>' for o,a,c in query.order_by(SalesOrder.id.desc()).limit(500).all())
    return page('Orders','<a class="primary" href="/orders/new">Book Order</a><div class="table"><table><tr><th>Order</th><th>Salon</th><th>Total</th><th>Status</th></tr>'+rows+'</table></div>')

@router.get('/orders/new',response_class=HTMLResponse)
def new_order(request:Request,client_id:int=0):
    denied=order_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:clients=clients_select(db,client_id)
    lines=''.join(f'<tr data-mrp="{mrp}"><td>{escape(name)}<small>{sku}</small></td><td>₹{mrp}</td><td><input aria-label="Quantity {name}" name="qty_{sku}" type="number" min="0" max="10000" step="1" value="0"></td><td><input aria-label="Discount percent {name}" name="discount_{sku}" type="number" min="0" max="100" step="0.01" value="0"></td><td class="line-total">₹0.00</td></tr>' for sku,name,mrp in CATALOG)
    script='''<script>const f=document.querySelector('#order-form');f.addEventListener('input',()=>{let total=0;f.querySelectorAll('tr[data-mrp]').forEach(r=>{const inputs=r.querySelectorAll('input');const qty=Number(inputs[0].value);const discount=Number(inputs[1].value);const value=Math.round(Number(r.dataset.mrp)*qty*(100-discount))/100;total+=value;r.querySelector('.line-total').textContent='₹'+value.toFixed(2);});document.querySelector('#order-total').textContent='₹'+total.toFixed(2);});</script>'''
    return page('Book Order',f'<form id="order-form" method="post" action="/orders">{hidden(request)}<input type="hidden" name="submission" value="{token_urlsafe(24)}">{salon_field(clients,"/orders/new")}<div class="full table"><table><tr><th>SKU</th><th>MRP</th><th>Qty</th><th>Discount %</th><th>Amount</th></tr>{lines}</table></div><h2 class="full">Total: <span id="order-total">₹0.00</span></h2><label>Payment terms<input name="payment_terms" maxlength="200"></label><label>Delivery address<textarea name="delivery_address" maxlength="2000"></textarea></label><label>Notes<textarea name="notes" maxlength="4000"></textarea></label><button>Save Order &amp; Continue to WhatsApp</button><p>Order booking is not an invoice or payment receipt. Amounts use MRP less your entered discount; existing billing remains separate.</p></form>'+script)

@router.post('/orders')
async def book_order(request:Request):
    denied=order_access(request)
    if denied is not None:return denied
    f=await request.form();denied=staff_access(request,str(f.get('csrf','')))
    if denied is not None:return denied
    try:
        lines,subtotal,total=price_lines(f);cid=int(f.get('client_id','0'))
        submission=str(f.get('submission',''));terms=str(f.get('payment_terms','')).strip();address=str(f.get('delivery_address','')).strip();notes=str(f.get('notes','')).strip()
        if not 16<=len(submission)<=80 or len(terms)>200 or len(address)>2000 or len(notes)>4000:raise ValueError('Invalid order details')
    except ValueError as e:return HTMLResponse(escape(str(e)),400)
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        prior=db.query(AuditLog).filter_by(user_id=request.session['user_id'],action='ORDER_BOOKED',new_value=submission).first()
        if prior:return RedirectResponse(f'/orders/{prior.entity_id}',303)
        c=db.get(Client,cid)
        if not c:return HTMLResponse('Salon not found',404)
        a=Activity(client_id=cid,activity_type='ORDER',source='SALES',status='OPEN',title='Order booked',notes=notes,created_by=request.session['user_id'],assigned_user_id=request.session['user_id'],created_at=now());db.add(a);db.flush()
        o=SalesOrder(activity_id=a.id,order_source='ESONE',subtotal=subtotal,discount_amount=subtotal-total,total_amount=total,payment_terms=terms,delivery_address=address or c.address,created_at=now());db.add(o);db.flush();o.order_number=f'ESONE-{now():%Y%m}-{o.id:06d}'
        db.add_all([OrderLine(order_id=o.id,**line) for line in lines]);audit(db,request,'SalesOrder',o.id,'ORDER_BOOKED',new=submission);oid=o.id
    return RedirectResponse(f'/orders/{oid}',303)

def get_order(db,oid,request):
    o=db.get(SalesOrder,oid)
    if not o:return None
    a=db.get(Activity,o.activity_id)
    if not permitted(request,a):return None
    return o,a,db.get(Client,a.client_id),db.query(OrderLine).filter_by(order_id=oid).order_by(OrderLine.id).all()

@router.get('/orders/{order_id}',response_class=HTMLResponse)
def detail(order_id:int,request:Request):
    denied=order_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        found=get_order(db,order_id,request)
        if not found:return HTMLResponse('Order not found or access denied',404)
        o,a,c,lines=found
        rows=''.join(f'<tr><td>{escape(l.name)}</td><td>{l.quantity}</td><td>₹{l.mrp}</td><td>{l.discount_percent}%</td><td>₹{l.amount}</td></tr>' for l in lines)
        content=f'<h2>{escape(o.order_number or str(o.id))}</h2><p>{escape(c.business_name)} · {escape(o.status)}</p><div class="table"><table><tr><th>Product</th><th>Qty</th><th>MRP</th><th>Discount</th><th>Amount</th></tr>{rows}</table></div><h2>Total ₹{o.total_amount}</h2>'+share_button(f'/orders/{order_id}/pdf',f'ESONE_order_{order_id}.pdf')
        content+=f'<form method="post" action="/orders/{order_id}/send">{hidden(request)}<button>Send Order via connected WhatsApp</button><p>Sends the order confirmation to the salon’s registered WhatsApp number when the approved template is configured.</p></form>'
        logs=db.query(CommunicationLog).filter_by(activity_id=a.id,purpose='ORDER_CONFIRMATION').order_by(CommunicationLog.id.desc()).limit(5).all()
        content+=''.join(f'<p>WhatsApp: {escape(l.status)} · {escape(l.failure_reason or "")}</p>' for l in logs)
    return page('Order Details',content+SHARE_SCRIPT)

@router.get('/orders/{order_id}/pdf')
def order_pdf(order_id:int,request:Request):
    denied=order_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        found=get_order(db,order_id,request)
        if not found:return HTMLResponse('Order not found or access denied',404)
        o,a,c,lines=found
        rows=[[l.name,l.quantity,l.mrp,str(l.discount_percent)+'%',l.amount] for l in lines]
        return pdf_response('Order '+str(o.order_number),['Product','Qty','MRP (INR)','Discount','Amount (INR)'],rows,f'ESONE_order_{order_id}.pdf',f'{c.business_name} | Total INR {o.total_amount} | {o.payment_terms or ""} | Order confirmation - not tax invoice')

@router.post('/orders/{order_id}/send')
def send_order(order_id:int,request:Request,csrf:str=Form('')):
    denied=order_access(request)
    if denied is not None:return denied
    denied=staff_access(request,csrf)
    if denied is not None:return denied
    from modules.order_delivery import send_confirmation,DeliveryError
    with SessionLocal.begin() as db:
        # Serialize sends; accepted messages cannot be resent accidentally.
        db.query(SalesOrder).filter_by(id=order_id).with_for_update().first()
        found=get_order(db,order_id,request)
        if not found:return HTMLResponse('Order not found or access denied',404)
        o,a,c,lines=found
        if db.query(CommunicationLog).filter_by(activity_id=a.id,purpose='ORDER_CONFIRMATION',status='ACCEPTED').first():return HTMLResponse('WhatsApp already accepted this order confirmation.',409)
        from datetime import timedelta
        recent=db.query(CommunicationLog).filter_by(activity_id=a.id,purpose='ORDER_CONFIRMATION').filter(CommunicationLog.created_at>now()-timedelta(minutes=5)).first()
        if recent:return HTMLResponse('Wait five minutes before retrying a failed order send. Check WhatsApp first to avoid duplicate delivery.',429)
        log=CommunicationLog(client_id=c.id,activity_id=a.id,purpose='ORDER_CONFIRMATION',recipient=c.whatsapp_phone or c.phone,send_mode='API',created_by=request.session['user_id'],created_at=now());db.add(log)
        try:
            log.provider_message_id=send_confirmation(c.whatsapp_phone or c.phone,c.business_name,o.order_number,str(o.total_amount));log.status='ACCEPTED';log.sent_at=now()
        except DeliveryError as e:log.status='FAILED';log.failure_reason=str(e)
        audit(db,request,'SalesOrder',order_id,'ORDER_WHATSAPP',new=log.status)
    return RedirectResponse(f'/orders/{order_id}',303)
