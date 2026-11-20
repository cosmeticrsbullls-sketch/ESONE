"""Browser approval. Cookie possession is not hardware or identity attestation."""
from modules.workflows import now as utc_now
import hashlib
import os
import secrets
from html import escape
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import User, EmployeeDevice, AuditLog
from modules.workflows import hidden, page

router = APIRouter()
COOKIE = 'esone_device'
REVIEWERS = {'SUPER_ADMIN', 'MANAGEMENT', 'OFFICE'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def current_device(db, request):
    raw = request.cookies.get(COOKIE, '')
    if not 32 <= len(raw) <= 128:
        return None
    return db.query(EmployeeDevice).filter_by(user_id=request.session.get('user_id'), token_hash=digest(raw)).first()


def require_device(db, request):
    device = current_device(db, request)
    if not device or device.status != 'APPROVED':
        raise HTTPException(403, 'This browser requires Command Center approval. Open /device-access.')
    return device


def enroll(db, request, user):
    # Caller holds the user lock. A Super Admin can bootstrap approval access.
    raw = request.cookies.get(COOKIE, '')
    if not 32 <= len(raw) <= 128:
        raw = secrets.token_urlsafe(32)
    device = db.query(EmployeeDevice).filter_by(user_id=user.id, token_hash=digest(raw)).first()
    if device is None:
        root = user.role == 'SUPER_ADMIN'
        device = EmployeeDevice(user_id=user.id, token_hash=digest(raw), status='APPROVED' if root else 'PENDING', label=request.headers.get('user-agent', 'Browser')[:250], created_at=utc_now(), reviewed_at=utc_now() if root else None, reviewed_by=user.id if root else None)
        db.add(device); db.flush()
        db.add(AuditLog(user_id=user.id, entity_type='EmployeeDevice', entity_id=device.id, action='DEVICE_BOOTSTRAP' if root else 'DEVICE_REQUEST', new_value=device.status))
    elif user.role == 'SUPER_ADMIN' and device.status == 'REVOKED':
        last_revoke = db.query(AuditLog).filter_by(entity_type='EmployeeDevice', entity_id=device.id, action='DEVICE_REVOKE').order_by(AuditLog.id.desc()).first()
        if last_revoke and last_revoke.new_value == 'Super Admin bootstrap on replacement browser':
            device.status = 'APPROVED'
            device.reviewed_at = utc_now(); device.reviewed_by = user.id
            db.add(AuditLog(user_id=user.id, entity_type='EmployeeDevice', entity_id=device.id, action='DEVICE_BOOTSTRAP', new_value='Restored previous Super Admin browser'))
    return device, raw


def cookie(response, raw):
    response.set_cookie(COOKIE, raw, max_age=365*24*3600, httponly=True, secure=os.getenv('RENDER', '').lower() == 'true', samesite='lax')
    return response


@router.get('/device-access', response_class=HTMLResponse)
def access_page(request: Request):
    if not request.session.get('user_id'):
        return RedirectResponse('/login', 303)
    with SessionLocal.begin() as db:
        user = db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        device, raw = enroll(db, request, user)
        body = f'<h2>Device approval</h2><p>Request #{device.id} · <strong>{escape(device.status)}</strong></p><p>Browser: {escape(device.label)}</p><p>New browsers require Command Center approval. Super Admin may use multiple browsers. For other users, approval of a replacement revokes the previous browser.</p>'
        if device.status == 'APPROVED':
            body += '<a href="/permissions">Continue to ESONE</a>'
        else:
            body += '<p>Ask Command Center to verify you and approve this request.</p><a href="/device-access">Refresh approval status</a>'
            if device.status in {'REJECTED', 'REVOKED'}:
                body += f'<form method="post" action="/device-access/request">{hidden(request)}<button>Request approval again</button></form>'
        body += '<p><a href="/logout">Sign out</a></p>'
        return cookie(HTMLResponse(page('Device approval', body), headers={'Cache-Control':'no-store'}), raw)


@router.post('/device-access/request')
def retry(request: Request, csrf: str = Form('')):
    if not request.session.get('user_id'): return RedirectResponse('/login', 303)
    check_csrf(request, csrf)
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        device = current_device(db, request)
        if not device: raise HTTPException(400, 'Open the device approval page first.')
        if device.status in {'REJECTED','REVOKED'}:
            device.status = 'PENDING'
            device.reviewed_at = None; device.reviewed_by = None
            db.add(AuditLog(user_id=device.user_id, entity_type='EmployeeDevice',entity_id=device.id,action='DEVICE_REQUEST',new_value='PENDING'))
    return RedirectResponse('/device-access',303)


def check_csrf(request, csrf):
    if not csrf or not secrets.compare_digest(csrf, request.session.get('workflow_csrf','')):
        raise HTTPException(403, 'Reload the page and try again.')


@router.get('/command-center/devices', response_class=HTMLResponse)
def review_page(request: Request):
    if request.session.get('role') not in REVIEWERS: raise HTTPException(403, 'Access denied')
    with SessionLocal() as db:
        rows=[]
        for device, user in db.query(EmployeeDevice,User).join(User,User.id==EmployeeDevice.user_id).order_by(EmployeeDevice.id.desc()).limit(200):
            actions=''
            if device.user_id != request.session['user_id']:
                choices = ['APPROVE','REJECT'] if device.status=='PENDING' else ['REVOKE'] if device.status=='APPROVED' else []
                for action in choices:
                    actions += f'<form method="post" action="/command-center/devices/{device.id}">{hidden(request)}<input type="hidden" name="decision" value="{action}"><button>{action.title()}</button></form>'
            rows.append(f'<tr><td>#{device.id} {escape(user.full_name)}</td><td>{escape(device.label)}</td><td>{escape(device.status)}</td><td>{device.created_at}</td><td>{actions}</td></tr>')
    return HTMLResponse(page('Device approvals','<h2>Device approvals</h2><p>Verify the employee before approving. For non-Super-Admin users, approving a replacement immediately revokes their other browser. Super Admin may use multiple approved browsers. You cannot approve your own request. Super Admin bootstrap access is recorded in the audit log.</p><table><tr><th>Employee</th><th>Browser</th><th>Status</th><th>Requested (UTC)</th><th>Review</th></tr>'+''.join(rows)+'</table>'))


@router.post('/command-center/devices/{device_id}')
def review(device_id:int, request:Request, decision:str=Form(''), csrf:str=Form('')):
    if request.session.get('role') not in REVIEWERS: raise HTTPException(403,'Access denied')
    check_csrf(request, csrf)
    with SessionLocal.begin() as db:
        item=db.get(EmployeeDevice,device_id)
        if not item: raise HTTPException(404,'Device not found')
        # Lock reviewer and employee in a consistent order; recheck reviewer after lock.
        db.query(User).filter(User.id.in_([item.user_id,request.session['user_id']])).order_by(User.id).with_for_update().all()
        require_device(db,request)
        db.refresh(item)
        if item.user_id == request.session['user_id']: raise HTTPException(403,'Another Command Center user must review your request')
        if decision in {'APPROVE','REJECT'} and item.status == 'PENDING':
            if decision == 'APPROVE' and db.get(User,item.user_id).role != 'SUPER_ADMIN':
                for old in db.query(EmployeeDevice).filter_by(user_id=item.user_id,status='APPROVED').all():
                    old.status='REVOKED'
                    db.add(AuditLog(user_id=request.session['user_id'],entity_type='EmployeeDevice',entity_id=old.id,action='DEVICE_REVOKE',new_value='replacement approved'))
            item.status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        elif decision=='REVOKE' and item.status=='APPROVED': item.status='REVOKED'
        else: raise HTTPException(409,'Request already reviewed or invalid action')
        item.reviewed_by=request.session['user_id'];item.reviewed_at=utc_now()
        db.add(AuditLog(user_id=item.reviewed_by,entity_type='EmployeeDevice',entity_id=item.id,action='DEVICE_'+decision,new_value=item.status))
    return RedirectResponse('/command-center/devices',303)
