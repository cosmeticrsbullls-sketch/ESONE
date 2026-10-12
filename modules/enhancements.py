"""Workspaces, audited management closure and account password changes."""
from html import escape
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, AuditLog, User, VerificationOTP, Visit
from modules.security import hash_password, verify_password
from modules.workflows import guard, hidden, now, page

router = APIRouter()
MANAGEMENT = {'SUPER_ADMIN', 'MANAGEMENT', 'OFFICE'}

def map_link(label, latitude, longitude):
    return f'<a href="https://www.google.com/maps/search/?api=1&amp;query={float(latitude)},{float(longitude)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'

@router.get('/workspace', response_class=HTMLResponse)
def workspace(request: Request):
    if not request.session.get('user_id'): return RedirectResponse('/',303)
    content = '<div class="workspace-buttons"><a href="/workspace/sales">Sales</a><a href="/workspace/collection">Collection</a><a href="/workspace/demo">Demo</a></div>'
    if request.session.get('role') in MANAGEMENT:
        content += '<p><a href="/command-center">Open Command Center</a></p>'
    return HTMLResponse(page('Home',content))

@router.get('/workspace/{section}', response_class=HTMLResponse)
def section(request: Request, section: str):
    if not request.session.get('user_id'): return RedirectResponse('/',303)
    management = request.session.get('role') in MANAGEMENT
    options = {
      'sales':[('Start sales visit','/field/intake'),('My visits','/visits')]+([('Clients','/clients'),('Sales reports','/operations?kind=visits')] if management else []),
      'collection':[('Start collection visit','/field/intake'),('My visits','/visits')]+([('Record collection call','/calls/new'),('Collection reports','/operations'),('Import bills and previous collections','/imports')] if management else []),
      'demo':[]+([('Book and manage demos','/demos'),('Demo reports','/operations?kind=demos')] if management else [])}
    if section not in options: return HTMLResponse('Not found',404)
    links=''.join(f'<p><a class="secondary" href="{url}">{label}</a></p>' for label,url in options[section])
    if section=='demo' and not management:
        from database.models import DemoBooking, Client
        with SessionLocal() as db:
            bookings=db.query(DemoBooking,Activity,Client).join(Activity,Activity.id==DemoBooking.activity_id).join(Client,Client.id==Activity.client_id).filter(DemoBooking.assigned_educator_id==request.session['user_id']).order_by(DemoBooking.demo_date).all()
            links += ''.join(f'<article class="card"><h3>{escape(c.business_name)}</h3><p>{escape(str(d.product_or_treatment or ""))} · {escape(str(d.demo_date or ""))} · {escape(a.status)}</p></article>' for d,a,c in bookings) or '<p>No demos assigned. Contact Command Center for demo bookings.</p>'
    return HTMLResponse(page(section.title(),'<a href="/workspace">← Home</a>'+links))

@router.post('/visits/{activity_id}/management-close')
def management_close(activity_id:int, request:Request, reason:str=Form(...), csrf:str=Form(...)):
    denied=guard(request,csrf)
    if denied is not None:return denied
    reason=reason.strip()
    if not 10 <= len(reason) <= 2000:return HTMLResponse('Provide a closure reason of 10–2000 characters.',400)
    with SessionLocal.begin() as db:
        activity=db.query(Activity).filter(Activity.id==activity_id).with_for_update().first()
        visit=db.query(Visit).filter(Visit.activity_id==activity_id).first()
        if activity is None or visit is None:return HTMLResponse('Visit not found',404)
        if activity.status!='IN_PROGRESS':return HTMLResponse('Only an in-progress visit can be closed.',409)
        activity.status='COMPLETED';activity.completed_at=now()
        # Administrative completion does not manufacture employee checkout evidence.
        db.add(AuditLog(user_id=request.session['user_id'],entity_type='VISIT',entity_id=activity_id,action='MANAGEMENT_CLOSE',old_value='IN_PROGRESS',new_value=reason))
        for otp in db.query(VerificationOTP).filter_by(activity_id=activity_id,purpose='VISIT_END',status='PENDING'):
            otp.status='CANCELLED'
    return RedirectResponse(f'/visits/{activity_id}',303)

@router.get('/account/password', response_class=HTMLResponse)
def password_page(request:Request):
    if not request.session.get('user_id'):return RedirectResponse('/',303)
    return HTMLResponse(page('Change password',f'<form method="post">{hidden(request)}<label>Current password<input type="password" name="current_password" autocomplete="current-password" required></label><label>New password<input type="password" name="new_password" minlength="8" autocomplete="new-password" required></label><label>Confirm new password<input type="password" name="confirm_password" autocomplete="new-password" required></label><button>Change password</button></form>'))

@router.post('/account/password')
def password_change(request:Request,current_password:str=Form(...),new_password:str=Form(...),confirm_password:str=Form(...),csrf:str=Form(...)):
    from secrets import compare_digest
    if not request.session.get('user_id'):return RedirectResponse('/',303)
    if not csrf or not compare_digest(csrf,request.session.get('workflow_csrf','')):return HTMLResponse('Reload and try again',403)
    if new_password!=confirm_password or len(new_password)<8 or len(new_password.encode())>72:return HTMLResponse('Passwords must match and contain at least 8 characters (maximum 72 UTF-8 bytes).',400)
    with SessionLocal.begin() as db:
        user=db.get(User,request.session['user_id'])
        if not user or not user.is_active or not verify_password(current_password,user.password_hash):return HTMLResponse('Current password is incorrect.',400)
        user.password_hash=hash_password(new_password)
        db.add(AuditLog(user_id=user.id,entity_type='USER',entity_id=user.id,action='PASSWORD_CHANGE'))
    request.session.clear()
    return RedirectResponse('/login',303)
