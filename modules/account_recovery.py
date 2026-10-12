"""Single-use email reset links. SMTP settings stay in the server environment."""
import hashlib
import os
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from secrets import compare_digest, token_urlsafe
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import PasswordReset, User, AuditLog
from modules.security import hash_password
from modules.workflows import hidden, now, page

router=APIRouter()
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def csrf_ok(request,csrf):return bool(csrf) and compare_digest(csrf,request.session.get('workflow_csrf',''))

def mail_settings():
    keys=['SMTP_HOST','SMTP_USERNAME','SMTP_PASSWORD','SMTP_FROM','ESONE_PUBLIC_URL']
    config={key:os.getenv(key,'').strip() for key in keys}
    if not all(config.values()) or not config['ESONE_PUBLIC_URL'].startswith('https://'):return None
    return config

@router.get('/forgot-password',response_class=HTMLResponse)
def forgot(request:Request):
    return HTMLResponse(page('Forgot password',f'<form method="post">{hidden(request)}<label>Registered email<input type="email" name="email" autocomplete="email" required></label><button>Email reset link</button></form>'))

@router.post('/forgot-password')
def send_reset(request:Request,email:str=Form(...),csrf:str=Form(...)):
    if not csrf_ok(request,csrf):return HTMLResponse('Reload and try again',403)
    config=mail_settings()
    if config is None:return HTMLResponse(page('Email setup required','<p>Password recovery email needs administrator configuration.</p>'),503)
    with SessionLocal.begin() as db:
        user=db.query(User).filter_by(email=email.strip().lower(),is_active=True).with_for_update().first()
        if user:
            recent=db.query(PasswordReset).filter(PasswordReset.user_id==user.id,PasswordReset.created_at>now()-timedelta(minutes=5)).first()
            if not recent:
                raw=token_urlsafe(32)
                reset=PasswordReset(user_id=user.id,token_hash=digest(raw),password_fingerprint=digest(user.password_hash),created_at=now(),expires_at=now()+timedelta(minutes=30))
                db.add(reset)
                message=EmailMessage();message['From']=config['SMTP_FROM'];message['To']=user.email;message['Subject']='ESONE password reset'
                message.set_content('Use this link within 30 minutes to reset your ESONE password:\n'+config['ESONE_PUBLIC_URL'].rstrip('/')+'/reset-password?token='+raw+'\nIf you did not request this, ignore this message.')
                try:
                    with smtplib.SMTP(config['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=15) as smtp:
                        smtp.starttls(context=ssl.create_default_context());smtp.login(config['SMTP_USERNAME'],config['SMTP_PASSWORD']);smtp.send_message(message)
                except (OSError,smtplib.SMTPException,ValueError):
                    # Uniform response protects account existence; retry can issue a new link.
                    db.expunge(reset)
    return HTMLResponse(page('Check your email','<p>If this is an approved registered account, a reset link will be sent. Check spam too.</p>'))

@router.get('/reset-password',response_class=HTMLResponse)
def reset_form(request:Request,token:str=''):
    from html import escape
    return HTMLResponse(page('Reset password',f'<form method="post">{hidden(request)}<input type="hidden" name="token" value="{escape(token,quote=True)}"><label>New password<input type="password" name="password" autocomplete="new-password" minlength="8" required></label><label>Confirm password<input type="password" name="confirm" autocomplete="new-password" required></label><button>Reset password</button></form>'),headers={'Referrer-Policy':'no-referrer','Cache-Control':'no-store'})

@router.post('/reset-password')
def reset_password(request:Request,token:str=Form(...),password:str=Form(...),confirm:str=Form(...),csrf:str=Form(...)):
    if not csrf_ok(request,csrf):return HTMLResponse('Reload and try again',403)
    if password!=confirm or len(password)<8 or len(password.encode())>72:return HTMLResponse('Passwords must match and contain at least 8 characters (maximum 72 UTF-8 bytes).',400)
    with SessionLocal.begin() as db:
        reset=db.query(PasswordReset).filter_by(token_hash=digest(token)).with_for_update().first()
        user=db.query(User).filter_by(id=reset.user_id).with_for_update().first() if reset else None
        if not reset or reset.used_at or reset.expires_at<=now() or not user or not user.is_active or reset.password_fingerprint!=digest(user.password_hash):return HTMLResponse('This link is invalid or expired. Request a new reset link.',400)
        user.password_hash=hash_password(password);reset.used_at=now()
        db.add(AuditLog(user_id=user.id,entity_type='USER',entity_id=user.id,action='PASSWORD_RESET'))
    request.session.clear()
    return RedirectResponse('/login',303)
