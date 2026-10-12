"""Live management inbox derived from audited business activity, no invented tasks."""
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from html import escape
from fastapi import APIRouter,Request,Form
from fastapi.responses import HTMLResponse,RedirectResponse
from sqlalchemy import or_
from database.db import SessionLocal
from database.models import Activity,User,Client,Attendance,PromiseToPay,NotificationRead,AuditLog,DemoBooking,SalesOrder
from modules.team import staff_access,MANAGEMENT
from modules.workflows import page,hidden,now
from modules.operations import business_today,queues
router=APIRouter()

def inbox(db,request):
    manager=request.session.get('role') in MANAGEMENT;uid=request.session['user_id'];today=business_today();zone=ZoneInfo('Asia/Kolkata')
    lower=datetime.combine(today,time.min).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    upper=lower+timedelta(days=1)
    people={u.id:u.full_name for u in db.query(User).all()};items=[]
    query=db.query(Activity,Client).join(Client,Client.id==Activity.client_id)
    if not manager:query=query.filter(or_(Activity.assigned_user_id==uid,Activity.created_by==uid))
    # Scheduled demo timestamps use India local time; generic scheduled dates use their stored business value.
    due_end=datetime.combine(today+timedelta(days=1),time.min)
    for a,c in query.filter(or_(Activity.created_at>=lower,Activity.updated_at>=lower,Activity.status.in_(['OPEN','BOOKED','IN_PROGRESS','CREATED']))).order_by(Activity.id.desc()).limit(1000).all():
        recent=(a.created_at and lower<=a.created_at<upper) or (a.completed_at and lower<=a.completed_at<upper)
        pending=a.status in {'OPEN','BOOKED','IN_PROGRESS','CREATED'}
        overdue=pending and a.scheduled_at is not None and a.scheduled_at<due_end
        if not recent and not pending:continue
        title=f'{people.get(a.created_by or a.assigned_user_id,"Unassigned")} · {a.activity_type} · {c.business_name} · {a.status}'
        if overdue:title='Missed / due activity: '+title
        elif pending:title='Pending: '+title
        else:title='Today: '+title
        url='/activity-reports'
        if a.activity_type=='FIELD_VISIT':url=f'/visits/{a.id}'
        elif a.activity_type=='DEMO':
            d=db.query(DemoBooking).filter_by(activity_id=a.id).first()
            if d:url=f'/demos/{d.id}'
        elif a.activity_type=='ORDER':
            o=db.query(SalesOrder).filter_by(activity_id=a.id).first()
            if o:url=f'/orders/{o.id}'
        items.append((title,url,a.updated_at or a.created_at or lower))
    punches=db.query(Attendance).filter(or_(Attendance.punch_in_at>=lower,Attendance.punch_out_at==None))
    if not manager:punches=punches.filter_by(user_id=uid)
    for p in punches.all():
        items.append((f'{people.get(p.user_id,"")} · '+('Punch out pending' if not p.punch_out_at else 'Attendance completed'),'/attendance',p.punch_out_at or p.punch_in_at))
    if manager:
        for kind in ['ptp','courtesy']:
            _,rows=queues(db,kind)
            for r in rows:items.append((('PTP due / overdue: '+str(r[2])) if kind=='ptp' else ('Courtesy call due: '+str(r[1])),'/operations?kind='+kind,lower))
        for event in db.query(AuditLog).filter(AuditLog.created_at>=lower,AuditLog.created_at<upper,AuditLog.action.in_(['MANAGEMENT_CLOSE','PROFILE_UPDATED','ADMIN_PASSWORD_RESET','PUNCH_IN','PUNCH_OUT'])).order_by(AuditLog.id.desc()).limit(500):
            items.append((f'{people.get(event.user_id,"Management")} · {event.action.replace("_"," ")}', '/activity-reports',event.created_at))
    return sorted(items,key=lambda x:x[2],reverse=True)

@router.get('/notifications',response_class=HTMLResponse)
def notifications(request:Request):
    denied=staff_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        items=inbox(db,request);read=db.get(NotificationRead,request.session['user_id']);read_at=read.read_at if read else datetime.min
    content=f'<p>{len(items)} activity and pending reminders. Business date {business_today()} (India).</p><form method="post">{hidden(request)}<button>Mark current updates read</button></form>'
    content+=''.join(f'<article class="card"><strong>{"New · " if stamp>read_at else ""}{escape(title)}</strong><p><a href="{url}">Open details</a></p></article>' for title,url,stamp in items) or '<p>No activities or pending reminders.</p>'
    return page('Notifications / Messages',content)

@router.post('/notifications')
def mark_read(request:Request,csrf:str=Form('')):
    denied=staff_access(request,csrf)
    if denied is not None:return denied
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        r=db.get(NotificationRead,request.session['user_id'])
        if not r:r=NotificationRead(user_id=request.session['user_id']);db.add(r)
        r.read_at=now()
    return RedirectResponse('/notifications',303)

def inbox_card(request):
    with SessionLocal() as db:
        items=inbox(db,request);r=db.get(NotificationRead,request.session['user_id']);stamp=r.read_at if r else datetime.min
    unread=sum(i[2]>stamp for i in items)
    return f'<a class="secondary notification-badge" href="/notifications">Notifications / Messages · {unread} new · {len(items)} activities &amp; reminders</a><script>setInterval(async()=>{{try{{const r=await fetch("/notifications/count");if(!r.ok)return;const d=await r.json();document.querySelector(".notification-badge").textContent="Notifications / Messages · "+d.unread+" new · "+d.total+" activities & reminders";}}catch(e){{}}}},60000);</script>'


@router.get('/notifications/count')
def notification_count(request:Request):
    denied=staff_access(request)
    if denied is not None:return denied
    from fastapi.responses import JSONResponse
    with SessionLocal() as db:
        items=inbox(db,request);read=db.get(NotificationRead,request.session['user_id']);stamp=read.read_at if read else datetime.min
    return JSONResponse({'unread':sum(i[2]>stamp for i in items),'total':len(items)},headers={'Cache-Control':'no-store'})
