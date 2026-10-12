"""Audited staff password resets without depending on email delivery."""
import json
from datetime import timedelta
from html import escape
from secrets import compare_digest
from fastapi import APIRouter,Form,Request
from fastapi.responses import HTMLResponse,RedirectResponse
from database.db import SessionLocal
from database.models import User,AuditLog,PasswordReset
from modules.security import hash_password,verify_password
from modules.workflows import hidden,now,page

router=APIRouter()
ADMIN_ROLES={'SUPER_ADMIN','MANAGEMENT'}
PROTECTED_ROLES={'SUPER_ADMIN','MANAGEMENT'}
REASONS={'FORGOT_PASSWORD','FIRST_LOGIN_HELP','SECURITY_RESET'}

def access(request):
    if not request.session.get('user_id'):return RedirectResponse('/login',303)
    if request.session.get('role') not in ADMIN_ROLES:return HTMLResponse('Access denied',403)

def eligible(actor,target):
    return target.id!=actor.id and target.is_active and (actor.role=='SUPER_ADMIN' or target.role not in PROTECTED_ROLES)

@router.get('/command-center/passwords',response_class=HTMLResponse)
def directory(request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        actor=db.get(User,request.session['user_id'])
        if not actor or not actor.is_active or actor.role not in ADMIN_ROLES:return HTMLResponse('Access denied',403)
        users=db.query(User).order_by(User.full_name).all()
        rows=''.join(f'<tr><td>{escape(user.full_name)}</td><td>{escape(user.email)}</td><td>{escape(user.role)}</td><td><a href="/command-center/passwords/{user.id}">Reset password</a></td></tr>' for user in users if eligible(actor,user))
    return HTMLResponse(page('Staff password reset','<p>Reset an approved employee\'s password when they cannot sign in. Current sessions and outstanding email-reset links will be invalidated. Employees can change the new password from their account after login.</p><p><a href="/account/password">Change your own password</a></p><div class="table"><table><tr><th>Name</th><th>Registered email</th><th>Role</th><th>Action</th></tr>'+rows+'</table></div>'),headers={'Cache-Control':'no-store'})

@router.get('/command-center/passwords/{user_id}',response_class=HTMLResponse)
def reset_form(user_id:int,request:Request,done:int=0):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        actor=db.get(User,request.session['user_id']);target=db.get(User,user_id)
        if not actor or not actor.is_active or actor.role not in ADMIN_ROLES:return HTMLResponse('Access denied',403)
        if not target:return HTMLResponse('User not found',404)
        if not eligible(actor,target):return HTMLResponse('Use your own Change Password page, or contact Super Admin for this account.',403)
        identity=f'<h2>{escape(target.full_name)}</h2><p>{escape(target.email)} · {escape(target.role)}</p>'
    if done and request.session.pop('management_password_reset_done',None)==user_id:
        return HTMLResponse(page('Password reset completed',identity+'<p>The password was reset and previous sessions were invalidated. Share the password you entered directly with the employee. The password is not displayed or saved in the audit record.</p><a href="/command-center/passwords">Return to staff list</a>'),headers={'Cache-Control':'no-store'})
    content=f'''{identity}<form method="post">{hidden(request)}<label>Your administrator password<input name="admin_password" type="password" autocomplete="current-password" required></label><label>New employee password<input name="new_password" type="password" autocomplete="new-password" minlength="8" required></label><label>Confirm employee password<input name="confirm_password" type="password" autocomplete="new-password" minlength="8" required></label><label>Reason<select name="reason"><option value="FORGOT_PASSWORD">Forgot password</option><option value="FIRST_LOGIN_HELP">First login help</option><option value="SECURITY_RESET">Security reset</option></select></label><label><input name="confirmed" value="yes" type="checkbox" required>I verified this employee's identity and intend to reset their password.</label><button>Reset employee password</button></form>'''
    return HTMLResponse(page('Reset employee password',content),headers={'Cache-Control':'no-store'})

@router.post('/command-center/passwords/{user_id}')
def reset(user_id:int,request:Request,csrf:str=Form(...),admin_password:str=Form(...),new_password:str=Form(...),confirm_password:str=Form(...),reason:str=Form(...),confirmed:str=Form('')):
    denied=access(request)
    if denied is not None:return denied
    if not csrf or not compare_digest(csrf,request.session.get('workflow_csrf','')):return HTMLResponse('Reload and try again.',403)
    if new_password!=confirm_password or len(new_password)<8 or len(new_password.encode())>72 or reason not in REASONS or confirmed!='yes':return HTMLResponse('Check matching passwords, reason and confirmation. Use at least 8 characters and at most 72 UTF-8 bytes.',400)
    with SessionLocal.begin() as db:
        # Consistent lock order prevents simultaneous cross-user resets deadlocking.
        users={u.id:u for u in db.query(User).filter(User.id.in_([request.session['user_id'],user_id])).order_by(User.id).with_for_update().all()}
        actor=users.get(request.session['user_id']);target=users.get(user_id)
        if not actor or not actor.is_active or actor.role not in ADMIN_ROLES:return HTMLResponse('Access denied',403)
        if not target:return HTMLResponse('User not found',404)
        if not eligible(actor,target):return HTMLResponse('This account cannot be reset by you.',403)
        failures=db.query(AuditLog).filter(AuditLog.user_id==actor.id,AuditLog.action=='ADMIN_PASSWORD_RESET_DENIED',AuditLog.created_at>now()-timedelta(minutes=15)).count()
        if failures>=5:return HTMLResponse('Too many incorrect administrator password attempts. Try again in 15 minutes.',429)
        if not verify_password(admin_password,actor.password_hash):
            db.add(AuditLog(user_id=actor.id,entity_type='USER',entity_id=target.id,action='ADMIN_PASSWORD_RESET_DENIED',new_value='WRONG_ADMIN_PASSWORD',created_at=now()))
            return HTMLResponse('Your administrator password is incorrect.',403)
        if verify_password(new_password,target.password_hash):return HTMLResponse('Choose a password different from the current employee password.',400)
        target.password_hash=hash_password(new_password)
        for link in db.query(PasswordReset).filter(PasswordReset.user_id==target.id,PasswordReset.used_at.is_(None)):
            link.used_at=now()
        db.add(AuditLog(user_id=actor.id,entity_type='USER',entity_id=target.id,action='ADMIN_PASSWORD_RESET',new_value=json.dumps({'reason':reason,'previous_sessions_invalidated':True})))
    request.session['management_password_reset_done']=user_id
    return RedirectResponse(f'/command-center/passwords/{user_id}?done=1',303)
