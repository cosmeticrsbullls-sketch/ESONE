"""Management call and demo workflows using the existing schema."""
import json
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from secrets import compare_digest, token_urlsafe
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, CollectionActivity, DemoBooking, PromiseToPay, User
from modules.operations import access, business_today

router = APIRouter()
CALL_OUTCOMES = {'CONTACTED', 'NO_ANSWER', 'CALL_BACK', 'REFUSED', 'PTP'}

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def token(request):
    if not request.session.get('workflow_csrf'):
        request.session['workflow_csrf'] = token_urlsafe(32)
    return request.session['workflow_csrf']

def guard(request, csrf):
    denied = access(request)
    if denied is not None:
        return denied
    if not csrf or not compare_digest(csrf, request.session.get('workflow_csrf', '')):
        return HTMLResponse('Please reload the form and try again.', 403)

def audit(db, request, entity, identity, action, old=None, new=None):
    db.add(AuditLog(user_id=request.session['user_id'], entity_type=entity,
                    entity_id=identity, action=action, old_value=old, new_value=new))

def page(title, content):
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>ESONE {escape(title)}</title><style>body{{font:16px Arial;background:#f5f5f5;color:#222;margin:20px}}main{{max-width:1100px;margin:auto;background:white;padding:24px;border-radius:12px}}label{{display:block;margin:14px 0}}input,select,textarea,button{{padding:10px;max-width:100%;box-sizing:border-box}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}.table{{overflow:auto}}a{{color:#725700}}button{{cursor:pointer}}</style></head><body><main class="workflow"><nav><a href="/command-center">Command Center</a> · <a href="/operations">Reports</a> · <a href="/calls/new">Record Call</a> · <a href="/demos">Demos</a></nav><h1>{escape(title)}</h1>{content}</main><script>
document.querySelectorAll('form').forEach(form=>{{
const refresh=()=>{{
const ptp=form.querySelector('input[name=outcome][value=PTP]');const courtesy=form.querySelector('input[name=kind][value=COURTESY_CALL]');if(ptp&&courtesy){{ptp.disabled=courtesy.checked;if(ptp.disabled&&ptp.checked)form.querySelector('input[name=outcome][value=CONTACTED]').checked=true;}}
const data=new FormData(form);const outcome=data.get('outcome');const action=data.get('action');
form.querySelectorAll('[data-when]').forEach(el=>{{const type=el.dataset.when;const visible=type==='promise'?(outcome==='PTP'||outcome==='RESCHEDULED'):type==='other'?data.get('treatment')==='OTHER':type==='complete'?action==='COMPLETE':action==='COMPLETE'&&data.get('result')==='FOLLOW_UP';el.hidden=!visible;el.querySelectorAll('input,select').forEach(input=>{{input.disabled=!visible;input.required=visible;}});}});
}};form.addEventListener('change',refresh);refresh();
}});
</script></body></html>'''

def hidden(request):
    return f'<input type="hidden" name="csrf" value="{token(request)}">'

def choices(name, options, selected, title):
    items = ''.join(f'<label class="choice"><input type="radio" name="{name}" value="{value}" {"checked" if value==selected else ""}><span>{escape(label)}</span></label>' for value,label in options)
    return f'<fieldset class="choice-group" {'data-when="complete"' if name=="result" else ""}><legend>{escape(title)}</legend><div class="choice-options">{items}</div></fieldset>'


def clients_select(db, selected=0):
    return ''.join(f'<option value="{c.id}" {"selected" if c.id==selected else ""}>{escape(c.business_name)} · {escape(c.phone or "")}</option>' for c in db.query(Client).order_by(Client.business_name).all())

def amount(value):
    try:
        result=Decimal(value)
    except InvalidOperation:
        raise ValueError('Enter a valid promised amount.')
    if not result.is_finite() or result <= 0 or result > Decimal('9999999999.99') or result != result.quantize(Decimal('.01')):
        raise ValueError('Amount must be positive, with at most two decimal places.')
    return result

@router.get('/calls/new', response_class=HTMLResponse)
def call_form(request: Request, client_id: int=0, kind: str='COLLECTION'):
    denied=access(request)
    if denied is not None:return denied
    if kind not in {'COLLECTION','COURTESY_CALL'}:return HTMLResponse('Invalid call type',400)
    with SessionLocal() as db:options=clients_select(db,client_id)
    return page('Record Call',f'''<form method="post" action="/calls">{hidden(request)}<input type="hidden" name="submission" value="{token_urlsafe(24)}"><label>Salon <select name="client_id" required>{options}</select></label>{choices("kind", [("COLLECTION","Collection / Telecalling"),("COURTESY_CALL","Courtesy Call")], kind, "Call type")}{choices("outcome", [("CONTACTED","Contacted"),("NO_ANSWER","No answer"),("CALL_BACK","Call back"),("REFUSED","Refused"),("PTP","Promise to pay")], "CONTACTED", "Call outcome")}<label>Notes <textarea name="notes" maxlength="4000" required></textarea></label><label data-when="promise">PTP amount <input name="promised_amount" type="number" min="0.01" step="0.01"></label><label data-when="promise">PTP date <input name="promise_date" type="date"></label><button>Save Call</button><p>Recording a promise does not record a payment. CONTACTED clears the current courtesy reminder; unanswered calls stay due.</p></form>''')

@router.post('/calls')
def record_call(request: Request, client_id:int=Form(...), kind:str=Form(...), outcome:str=Form(...), notes:str=Form(...), csrf:str=Form(''), submission:str=Form(''), promised_amount:str=Form(''), promise_date:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if kind not in {'COLLECTION','COURTESY_CALL'} or outcome not in CALL_OUTCOMES or not notes.strip() or len(notes)>4000 or not 16<=len(submission)<=80:
        return HTMLResponse('Invalid call details.',400)
    if kind=='COURTESY_CALL' and outcome=='PTP':return HTMLResponse('Use a collection call to record PTP.',400)
    try:
        value=amount(promised_amount) if outcome=='PTP' else None
        promised=date.fromisoformat(promise_date) if outcome=='PTP' else None
        if promised and promised<business_today():raise ValueError('PTP date cannot be in the past.')
    except ValueError as error:return HTMLResponse(escape(str(error)),400)
    with SessionLocal.begin() as db:
        # Serialize submissions by operator and keep a durable replay marker.
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        if db.query(AuditLog).filter_by(user_id=request.session['user_id'],action='CALL_RECORDED',new_value=submission).first():
            return HTMLResponse('This call was already recorded.',409)
        client=db.query(Client).filter_by(id=client_id).with_for_update().first()
        if not client:return HTMLResponse('Client not found',404)
        parent=None
        if kind=='COURTESY_CALL':
            parent=db.query(Activity).filter_by(client_id=client_id,activity_type='FIELD_VISIT',status='COMPLETED').filter(Activity.completed_at.isnot(None)).order_by(Activity.completed_at.desc(),Activity.id.desc()).first()
            if not parent or parent.completed_at.date()+timedelta(days=7)>business_today():return HTMLResponse('No courtesy call is due for this salon.',409)
            done=db.query(Activity).filter_by(parent_activity_id=parent.id,activity_type='COURTESY_CALL',status='COMPLETED').first()
            if done:return HTMLResponse('This courtesy reminder is already completed.',409)
        a=Activity(client_id=client_id,activity_type=kind,source='TELECALLING',status='COMPLETED' if kind=='COLLECTION' or outcome=='CONTACTED' else 'OPEN',title=outcome,notes=notes.strip(),created_by=request.session['user_id'],parent_activity_id=parent.id if parent else None,created_at=now(),completed_at=now() if kind=='COLLECTION' or outcome=='CONTACTED' else None)
        db.add(a);db.flush()
        if kind=='COLLECTION':
            c=CollectionActivity(activity_id=a.id,channel='TELECALLING',outcome=outcome,amount_discussed=value)
            db.add(c);db.flush()
            if promised:db.add(PromiseToPay(collection_activity_id=c.id,client_id=client_id,promised_amount=value,promise_date=datetime.combine(promised,time.min),notes=notes.strip(),created_by=request.session['user_id']))
        audit(db,request,'Activity',a.id,'CALL_RECORDED',new=submission)
    return RedirectResponse(f'/clients/{client_id}/timeline',303)

@router.get('/ptps/{ptp_id}',response_class=HTMLResponse)
def ptp_form(ptp_id:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        p=db.get(PromiseToPay,ptp_id)
        if not p:return HTMLResponse('PTP not found',404)
        c=db.get(Client,p.client_id)
        summary=f'<p>{escape(c.business_name)} · ₹{p.promised_amount} · {p.promise_date.date()} · {escape(p.status)}</p>'
    return page('PTP Follow-up',summary+f'''<form method="post">{hidden(request)}{choices("outcome", [("BROKEN","Promise broken"),("CANCELLED","Cancel promise"),("RESCHEDULED","Reschedule")], "BROKEN", "Follow-up outcome")}<label>Notes <textarea name="notes" required maxlength="4000"></textarea></label><label data-when="promise">New promise date <input name="promise_date" type="date"></label><label data-when="promise">New amount <input name="promised_amount" type="number" step="0.01" min="0.01"></label><button>Save Follow-up</button><p>Payments require a separate verified receipt workflow. This form does not mark balances paid.</p></form>''')

@router.post('/ptps/{ptp_id}')
def ptp_followup(ptp_id:int,request:Request,outcome:str=Form(...),notes:str=Form(...),csrf:str=Form(''),promise_date:str=Form(''),promised_amount:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if outcome not in {'BROKEN','CANCELLED','RESCHEDULED'} or not notes.strip() or len(notes)>4000:return HTMLResponse('Invalid follow-up.',400)
    try:
        promised=date.fromisoformat(promise_date) if outcome=='RESCHEDULED' else None
        value=amount(promised_amount) if promised else None
        if promised and promised<business_today():raise ValueError('PTP date cannot be in the past.')
    except ValueError as error:return HTMLResponse(escape(str(error)),400)
    with SessionLocal.begin() as db:
        p=db.query(PromiseToPay).filter_by(id=ptp_id).with_for_update().first()
        if not p:return HTMLResponse('PTP not found',404)
        if p.status!='OPEN':return HTMLResponse('This PTP is already closed.',409)
        a=Activity(client_id=p.client_id,activity_type='COLLECTION',source='TELECALLING',status='COMPLETED',title=outcome,notes=notes.strip(),parent_activity_id=db.get(CollectionActivity,p.collection_activity_id).activity_id,created_by=request.session['user_id'],created_at=now(),completed_at=now())
        db.add(a);db.flush();c=CollectionActivity(activity_id=a.id,channel='TELECALLING',outcome=outcome,amount_discussed=value);db.add(c);db.flush()
        p.status=outcome
        if promised:db.add(PromiseToPay(client_id=p.client_id,collection_activity_id=c.id,promised_amount=value,promise_date=datetime.combine(promised,time.min),notes=notes.strip(),created_by=request.session['user_id']))
        audit(db,request,'PromiseToPay',p.id,'FOLLOW_UP',old='OPEN',new=json.dumps({'status':outcome,'activity_id':a.id}))
        cid=p.client_id
    return RedirectResponse(f'/clients/{cid}/timeline',303)

@router.get('/demos',response_class=HTMLResponse)
def demos(request:Request,status:str='',q:str=''):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        query=db.query(DemoBooking,Activity,Client).join(Activity,Activity.id==DemoBooking.activity_id).join(Client,Client.id==Activity.client_id)
        if status:query=query.filter(Activity.status==status)
        if q:query=query.filter(Client.business_name.ilike(f'%{q}%'))
        rows=''.join(f'<tr><td><a href="/demos/{d.id}">{d.id}</a></td><td>{escape(c.business_name)}</td><td>{escape(d.product_or_treatment or "")}</td><td>{d.demo_date}</td><td>{d.assigned_educator_id}</td><td>{escape(a.status)}</td><td>{escape(d.conversion_status or "")}</td></tr>' for d,a,c in query.order_by(DemoBooking.demo_date,DemoBooking.id).all())
    return page('Demo Bookings',f'<p><a href="/demos/new">Book Demo</a></p><form><input name="q" placeholder="Salon" value="{escape(q,quote=True)}"><select name="status"><option value="">All statuses</option>{"".join(f"<option {"selected" if s==status else ""}>{s}</option>" for s in ["BOOKED","IN_PROGRESS","COMPLETED","CANCELLED"])}</select><button>Filter</button></form><p>Demo times are displayed in India time. <a href="/operations?kind=demos">Demo history / filtered Excel</a></p><div class="table"><table><tr><th>ID</th><th>Salon</th><th>Treatment</th><th>Demo date</th><th>Educator ID</th><th>Status</th><th>Result</th></tr>{rows or "<tr><td colspan=7>No demo bookings.</td></tr>"}</table></div>')

@router.get('/demos/new',response_class=HTMLResponse)
def demo_form(request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        clients=clients_select(db)
        people=''.join(f'<option value="{u.id}">{escape(u.full_name)}</option>' for u in db.query(User).filter_by(is_active=True).order_by(User.full_name).all())
    return page('Book Demo',f'''<form method="post" action="/demos">{hidden(request)}<input type="hidden" name="submission" value="{token_urlsafe(24)}"><label>Salon <select name="client_id">{clients}</select></label><label>Treatment <select name="treatment"><option value="NanoBeen">NanoBeen / Nanoplastia</option><option value="BeenBotox">BeenBotox / Hair Botox</option><option value="KeraBeen">KeraBeen / Keratin</option><option value="OTHER">Other treatment</option></select></label><label data-when="other">Other treatment name <input name="custom_treatment" maxlength="200" placeholder="Enter treatment name"></label><label>Demo date / time (India) <input name="demo_at" type="datetime-local" required></label><label>Educator <select name="educator_id">{people}</select></label><label>Notes <textarea name="notes" maxlength="4000"></textarea></label><button>Book Demo</button></form>''')

@router.post('/demos')
def book_demo(request:Request,client_id:int=Form(...),educator_id:int=Form(...),treatment:str=Form(...),demo_at:str=Form(...),notes:str=Form(''),csrf:str=Form(''),submission:str=Form(''),custom_treatment:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    try:
        scheduled=datetime.fromisoformat(demo_at)
        if scheduled.tzinfo or scheduled<datetime.now(ZoneInfo('Asia/Kolkata')).replace(tzinfo=None):raise ValueError()
    except ValueError:return HTMLResponse('Choose a future India date and time.',400)
    if treatment == 'OTHER': treatment = custom_treatment
    if not treatment.strip() or len(treatment)>200 or len(notes)>4000 or not 16<=len(submission)<=80:return HTMLResponse('Invalid booking details.',400)
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        if db.query(AuditLog).filter_by(user_id=request.session['user_id'],action='DEMO_BOOKED',new_value=submission).first():return HTMLResponse('This demo was already booked.',409)
        if not db.get(Client,client_id):return HTMLResponse('Client not found',404)
        educator=db.get(User,educator_id)
        if not educator or not educator.is_active:return HTMLResponse('Select an active educator.',400)
        a=Activity(client_id=client_id,activity_type='DEMO',source='MANAGEMENT',status='BOOKED',title=treatment.strip(),notes=notes.strip(),scheduled_at=scheduled,assigned_user_id=educator_id,created_by=request.session['user_id'],created_at=now())
        db.add(a);db.flush();d=DemoBooking(activity_id=a.id,product_or_treatment=treatment.strip(),booking_source='MANAGEMENT',demo_date=scheduled,assigned_educator_id=educator_id)
        db.add(d);db.flush();identity=d.id;audit(db,request,'DemoBooking',d.id,'DEMO_BOOKED',new=submission)
    return RedirectResponse(f'/demos/{identity}',303)

@router.get('/demos/{demo_id}',response_class=HTMLResponse)
def demo_detail(demo_id:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        d=db.get(DemoBooking,demo_id)
        if not d:return HTMLResponse('Demo not found',404)
        a=db.get(Activity,d.activity_id);c=db.get(Client,a.client_id);u=db.get(User,d.assigned_educator_id)
        content=f'<p>{escape(c.business_name)} · {escape(d.product_or_treatment or "")} · {d.demo_date} (India)</p><p>Educator: {escape(u.full_name if u else "Unassigned")} · {escape(a.status)} · {escape(d.conversion_status or "")}</p><p>{escape(a.notes or "")}</p><p>Follow-up: {d.followup_at.date() if d.followup_at else "—"}</p><p>Started: {d.started_at or "—"} · Completed: {d.completed_at or "—"} (UTC)</p>'
        if a.status in {'BOOKED','IN_PROGRESS'}:
            actions=['START','CANCEL'] if a.status=='BOOKED' else ['COMPLETE']
            content+=f'''<form method="post">{hidden(request)}{choices("action", [(v,{"START":"Start Demo","CANCEL":"Cancel Booking","COMPLETE":"Complete Demo"}[v]) for v in actions], actions[0], "Demo action")}{choices("result", [("CONVERTED","Converted"),("NOT_CONVERTED","Not converted"),("FOLLOW_UP","Follow-up needed")], "CONVERTED", "Conversion result (completion only)")}<label>Notes / reason <textarea name="notes" maxlength="4000" required></textarea></label><label data-when="followup">Follow-up date <input name="followup" type="date"></label><button>Save</button></form>'''
    return page('Demo Details',content)

@router.post('/demos/{demo_id}')
def demo_transition(demo_id:int,request:Request,action:str=Form(...),result:str=Form('PENDING'),notes:str=Form(''),followup:str=Form(''),csrf:str=Form('')):
    denied=guard(request,csrf)
    if denied is not None:return denied
    if not notes.strip() or len(notes)>4000:return HTMLResponse('Notes are required (maximum 4000 characters).',400)
    try:
        due=date.fromisoformat(followup) if followup else None
        if due and due<business_today():raise ValueError()
    except ValueError:return HTMLResponse('Invalid follow-up date.',400)
    if action=='COMPLETE' and (result not in {'CONVERTED','NOT_CONVERTED','FOLLOW_UP'} or (result=='FOLLOW_UP' and not due)):return HTMLResponse('Choose a completion result and follow-up date when needed.',400)
    with SessionLocal.begin() as db:
        d=db.query(DemoBooking).filter_by(id=demo_id).with_for_update().first()
        if not d:return HTMLResponse('Demo not found',404)
        a=db.get(Activity,d.activity_id);old=a.status
        if action=='START' and old=='BOOKED':a.status='IN_PROGRESS';d.started_at=now()
        elif action=='CANCEL' and old=='BOOKED':a.status='CANCELLED';a.completed_at=now()
        elif action=='COMPLETE' and old=='IN_PROGRESS':
            a.status='COMPLETED';d.completed_at=now();a.completed_at=d.completed_at;d.conversion_status=result
            d.non_conversion_reason=notes.strip() if result=='NOT_CONVERTED' else None
            d.followup_at=datetime.combine(due,time.min) if due else None
        else:return HTMLResponse('This action is not available for the current demo status.',409)
        a.notes=(a.notes+'\n' if a.notes else '')+action+': '+notes.strip()
        audit(db,request,'DemoBooking',d.id,'STATUS_CHANGED',old=old,new=json.dumps({'status':a.status,'result':d.conversion_status}))
    return RedirectResponse(f'/demos/{demo_id}',303)
