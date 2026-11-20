"""Browser class policy, not hardware attestation. Existing users retain Both."""
import re
from html import escape
from fastapi import APIRouter,Request,Form
from fastapi.responses import HTMLResponse,RedirectResponse
from database.db import SessionLocal
from database.models import User,UserAccessPolicy,EmployeeDevice,WebPushSubscription,AuditLog
from modules.workflows import hidden,page,now
from modules.team import staff_access

router=APIRouter()
LABELS={'MOBILE':'Mobile Only','WEB':'Computer / Web Only','BOTH':'Both'}

def mobile_agent(agent):return bool(re.search(r'Android|iPhone|iPad|iPod|Mobile',agent,re.I))

def is_mobile(request):return request.headers.get('sec-ch-ua-mobile')=='?1' or mobile_agent(request.headers.get('user-agent',''))

def access_type(db,user):
    if user.role=='SUPER_ADMIN':return 'BOTH'
    policy=db.get(UserAccessPolicy,user.id)
    return policy.access_type if policy else 'BOTH'

def allowed(db,user,request):
    kind=access_type(db,user)
    return kind=='BOTH' or (kind=='MOBILE')==is_mobile(request)

def permissions_required(db,user,request):
    return user.role!='SUPER_ADMIN' and access_type(db,user)!='WEB' and is_mobile(request)

def revoke_devices(db,actor,target,reason):
    devices=db.query(EmployeeDevice).filter_by(user_id=target.id).all()
    for device in devices:
        device.status='REVOKED';device.reviewed_by=actor.id;device.reviewed_at=now()
        db.add(AuditLog(user_id=actor.id,entity_type='EmployeeDevice',entity_id=device.id,action='DEVICE_REVOKE',new_value=reason))
    db.query(WebPushSubscription).filter_by(user_id=target.id).update({'enabled':False})

def admin(request,csrf=None):
    if csrf is not None and not csrf.isascii():return HTMLResponse('Reload the form and retry.',403)
    denied=staff_access(request,csrf)
    if denied is not None:return denied
    if request.session.get('role')!='SUPER_ADMIN':return HTMLResponse('Super Admin access required.',403)

def target_user(db,identity):return db.query(User).filter_by(id=identity).with_for_update().first()

@router.get('/access-type-denied',response_class=HTMLResponse)
def denied_page(request:Request):
    if not request.session.get('user_id'):return RedirectResponse('/login',303)
    with SessionLocal() as db:
        user=db.get(User,request.session['user_id']);label=LABELS[access_type(db,user)]
    return HTMLResponse(page('Device type not allowed',f'<p>This account is set to <strong>{label}</strong>. Use the permitted device or ask Super Admin to update Team &amp; Access.</p><a href="/logout">Sign out</a>'),status_code=403)

@router.get('/command-center/access/{user_id}',response_class=HTMLResponse)
def settings(user_id:int,request:Request):
    denied=admin(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        user=db.get(User,user_id)
        if not user:return HTMLResponse('Employee not found',404)
        kind=access_type(db,user)
        devices=db.query(EmployeeDevice).filter_by(user_id=user_id).all()
        rows=''.join(f'<li>#{d.id} · {escape(d.label)} · {escape(d.status)}</li>' for d in devices) or '<li>No browser registered.</li>'
    content=f'<h2>{escape(user.full_name)}</h2><p>Access: {LABELS[kind]}</p>'
    if user.role=='SUPER_ADMIN':content+='<p>Super Admin always has Both access and no permissions setup.</p>'
    else:
        options=''.join(f'<option value="{value}" {"selected" if value==kind else ""}>{label}</option>' for value,label in LABELS.items())
        content+=f'<form method="post" action="/command-center/access/{user_id}">{hidden(request)}<label>Access type<select name="access_type" required>{options}</select></label><p>Changing access type resets device approvals. The employee must request approval again on the permitted device.</p><label>Reason<input name="reason" maxlength="500" required></label><button>Save Access Type</button></form>'
        content+=f'<h2>Reset device</h2><ul>{rows}</ul><form method="post" action="/command-center/access/{user_id}/reset-device">{hidden(request)}<label>Reason<input name="reason" maxlength="500" required></label><label><input type="checkbox" name="confirmed" value="yes" required> Revoke all current browsers and require fresh device approval</label><p>Employee records, reports and password are preserved.</p><button>Reset Device</button></form>'
    if user.id!=request.session['user_id'] and user.is_active:content+=f'<p><a class="secondary" href="/command-center/passwords/{user_id}">Reset Password</a></p>'
    content+='<a href="/users">← Team &amp; Access</a>'
    return HTMLResponse(page('Employee Access',content),headers={'Cache-Control':'no-store'})

@router.post('/command-center/access/{user_id}')
def save_access(user_id:int,request:Request,access_type:str=Form(''),reason:str=Form(''),csrf:str=Form('')):
    denied=admin(request,csrf)
    if denied is not None:return denied
    if access_type not in LABELS or not 1<=len(reason.strip())<=500:return HTMLResponse('Choose an access type and provide a reason.',400)
    with SessionLocal.begin() as db:
        target=target_user(db,user_id);actor=db.get(User,request.session['user_id'])
        if not target:return HTMLResponse('Employee not found',404)
        if target.role=='SUPER_ADMIN':return HTMLResponse('Super Admin must retain Both access.',403)
        policy=db.get(UserAccessPolicy,user_id)
        old=policy.access_type if policy else 'BOTH'
        if old!=access_type:
            if not policy:policy=UserAccessPolicy(user_id=user_id);db.add(policy)
            policy.access_type=access_type;policy.updated_by=actor.id;policy.updated_at=now()
            revoke_devices(db,actor,target,'Access type changed by Super Admin')
            db.add(AuditLog(user_id=actor.id,entity_type='USER',entity_id=user_id,action='ACCESS_TYPE_CHANGED',old_value=old,new_value=access_type+': '+reason.strip()))
    return RedirectResponse(f'/command-center/access/{user_id}',303)

@router.post('/command-center/access/{user_id}/reset-device')
def reset_device(user_id:int,request:Request,reason:str=Form(''),confirmed:str=Form(''),csrf:str=Form('')):
    denied=admin(request,csrf)
    if denied is not None:return denied
    if confirmed!='yes' or not 1<=len(reason.strip())<=500:return HTMLResponse('Confirm device reset and provide a reason.',400)
    with SessionLocal.begin() as db:
        target=target_user(db,user_id);actor=db.get(User,request.session['user_id'])
        if not target:return HTMLResponse('Employee not found',404)
        if target.role=='SUPER_ADMIN':return HTMLResponse('Use individual device review for Super Admin browsers.',403)
        revoke_devices(db,actor,target,'Command Center device reset')
        db.add(AuditLog(user_id=actor.id,entity_type='USER',entity_id=user_id,action='ADMIN_DEVICE_RESET',new_value=reason.strip()))
    return RedirectResponse(f'/command-center/access/{user_id}',303)
