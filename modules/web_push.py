"""Opt-in, device-bound standards-based Web Push. No application page caching."""
import asyncio
import base64
import hashlib
import json
import logging
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,FileResponse
from sqlalchemy.exc import IntegrityError
from database.db import SessionLocal
from database.models import WebPushKey,WebPushSubscription,WebPushDelivery,EmployeeDevice,User,NotificationRead
from modules.device_access import require_device
from modules.workflows import page,hidden,now
from modules.team import staff_access as guard

router=APIRouter()
log=logging.getLogger(__name__)

def b64(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def keys(db):
    item=db.get(WebPushKey,1)
    if not item:
        key=ec.generate_private_key(ec.SECP256R1())
        item=WebPushKey(id=1,private_key=b64(key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())),public_key=b64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)))
        try:
            with db.begin_nested():db.add(item);db.flush()
        except IntegrityError:item=db.get(WebPushKey,1)
    return item

def valid_subscription(data):
    try:
        endpoint=data['endpoint']
        if not isinstance(endpoint,str):raise ValueError()
        parts=urlsplit(endpoint)
        if not isinstance(endpoint,str) or len(endpoint)>4096:raise ValueError()
        if parts.scheme!='https' or parts.port not in (None,443) or parts.username or parts.password or parts.fragment:raise ValueError()
        host=parts.hostname or ''
        if not (host in {'fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'} or host.endswith('.push.services.mozilla.com') or host.endswith('.push.apple.com')):raise ValueError()
        public=data['keys']['p256dh'];auth=data['keys']['auth']
        for value,length in [(public,65),(auth,16)]:
            if not isinstance(value,str) or len(value)>120:raise ValueError()
            decoded=base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
            if len(decoded)!=length:raise ValueError()
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),base64.urlsafe_b64decode(public+'='*(-len(public)%4)))
        return endpoint,public,auth
    except (ValueError,TypeError,KeyError):raise HTTPException(400,'Invalid or unsupported browser push subscription.')

def send(db,subscription,payload):
    from pywebpush import webpush,WebPushException
    key=keys(db)
    try:
        webpush(subscription_info={'endpoint':subscription.endpoint,'keys':{'p256dh':subscription.p256dh,'auth':subscription.auth}},data=json.dumps(payload),vapid_private_key=key.private_key,vapid_claims={'sub':'https://esone.theearthshine.com'},ttl=3600,timeout=10)
        return True
    except WebPushException as error:
        status=error.response.status_code if error.response is not None else None
        if status in {404,410}:subscription.enabled=False
        log.warning('Push delivery failed for subscription %s (status %s)',subscription.id,status)
        return False
    except Exception:
        log.warning('Push delivery unavailable for subscription %s',subscription.id)
        return False

@router.get('/permissions',response_class=HTMLResponse)
def permissions(request:Request):
    if not request.session.get('user_id'):
        from fastapi.responses import RedirectResponse
        return RedirectResponse('/login',303)
    with SessionLocal.begin() as db:
        device=require_device(db,request);public=keys(db).public_key
        identity=f'{device.user_id}:{device.id}'
    content=f'''<div id="permission-setup" data-device="{identity}" data-key="{public}">{hidden(request)}<p>Set up this browser once. Permissions can be changed later in browser settings.</p><style>.permission-row{{padding:16px 0;border-bottom:1px solid #ddd}}.permission-row span{{display:block;margin:6px 0}}[hidden]{{display:none!important}}</style>
<div class="permission-row"><strong>📍 Location</strong><span id="location-status" role="status">Checking…</span><button type="button" id="allow-location">Enable Location</button></div>
<div class="permission-row"><strong>📷 Camera</strong><span id="camera-status" role="status">Checking…</span><button type="button" id="allow-camera">Enable Camera</button></div>
<div class="permission-row"><strong>🔔 Notifications</strong><span id="notification-status" role="status">Checking…</span><button type="button" id="allow-notifications">Enable Notifications</button> <button type="button" id="test-notification" hidden>Send Test Notification</button> <button type="button" id="skip-notifications">Skip for now</button> <button type="button" id="disable-notifications" hidden>Turn off notifications</button></div>
<p id="setup-message" role="status"></p><button type="button" id="setup-continue" disabled>Continue to Home</button><p id="push-install" hidden>On iPhone/iPad, install ESONE using Share → Add to Home Screen, then open it from that icon to enable push notifications.</p><p>If permission is blocked, allow it in this site's browser settings.</p></div><script src="/assets/permissions.js?v=1" defer></script>'''
    if request.session.get('role') in {'SUPER_ADMIN','MANAGEMENT','OFFICE'}:content+='<p><a href="/command-center">Open Command Center</a></p>'
    return HTMLResponse(page('Set up ESONE',content),headers={'Cache-Control':'no-store'})

@router.get('/assets/permissions.js',include_in_schema=False)
def setup_script():return FileResponse(Path(__file__).with_name('permissions.js'),media_type='application/javascript',headers={'Cache-Control':'no-cache'})

@router.get('/assets/push-worker.js',include_in_schema=False)
def worker_script():return FileResponse(Path(__file__).with_name('push_worker.js'),media_type='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

async def payload(request):
    raw=await request.body()
    if len(raw)>8192:raise HTTPException(413,'Push request too large.')
    try:
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError()
        if not isinstance(data.get('csrf',''),str) or len(data.get('csrf',''))>200:raise ValueError()
        return data
    except (ValueError,TypeError):raise HTTPException(400,'Invalid push request.')

@router.post('/push/subscribe')
async def subscribe(request:Request):
    data=await payload(request)
    denied=guard(request,data.get('csrf',''))
    if denied is not None:return denied
    endpoint,public,auth=valid_subscription(data.get('subscription',{}))
    with SessionLocal.begin() as db:
        device=require_device(db,request)
        item=db.query(WebPushSubscription).filter_by(endpoint_hash=hashlib.sha256(endpoint.encode()).hexdigest()).first()
        if item and item.enabled and (item.user_id!=device.user_id or item.device_id!=device.id):raise HTTPException(409,'This push subscription belongs to another browser account. Reset notifications and retry.')
        if not item:
            item=WebPushSubscription(endpoint=endpoint,endpoint_hash=hashlib.sha256(endpoint.encode()).hexdigest());db.add(item)
        if not item.enabled or item.user_id!=device.user_id:item.created_at=now()
        item.user_id=device.user_id;item.device_id=device.id;item.p256dh=public;item.auth=auth;item.enabled=True
        item.credential_fingerprint=request.session['credential_fingerprint']
        if not item.created_at:item.created_at=now()
        db.flush()
        db.query(WebPushSubscription).filter(WebPushSubscription.device_id==device.id,WebPushSubscription.id!=item.id).update({'enabled':False})
    return JSONResponse({'subscribed':True},headers={'Cache-Control':'no-store'})

@router.post('/push/unsubscribe')
async def unsubscribe(request:Request):
    data=await payload(request);denied=guard(request,data.get('csrf',''))
    if denied is not None:return denied
    with SessionLocal.begin() as db:
        device=require_device(db,request)
        db.query(WebPushSubscription).filter_by(user_id=device.user_id,device_id=device.id).update({'enabled':False})
    return {'subscribed':False}

@router.post('/push/test')
async def test_push(request:Request):
    data=await payload(request);denied=guard(request,data.get('csrf',''))
    if denied is not None:return denied
    with SessionLocal.begin() as db:
        device=require_device(db,request)
        item=db.query(WebPushSubscription).filter_by(user_id=device.user_id,device_id=device.id,enabled=True).first()
        if not item:raise HTTPException(409,'Enable notifications first.')
        if item.last_test_at and item.last_test_at>now()-timedelta(seconds=30):raise HTTPException(429,'Wait 30 seconds before sending another test.')
        item.last_test_at=now()
        ok=send(db,item,{'title':'ESONE test notification','body':'Notifications are ready for this browser.','url':'/notifications','tag':'esone-test'})
    return JSONResponse({'sent':ok},status_code=200 if ok else 503)

def dispatch():
    from modules.notifications import inbox
    with SessionLocal.begin() as db:
        subscriptions=db.query(WebPushSubscription).join(EmployeeDevice,EmployeeDevice.id==WebPushSubscription.device_id).join(User,User.id==WebPushSubscription.user_id).filter(WebPushSubscription.enabled==True,EmployeeDevice.status=='APPROVED',User.is_active==True).with_for_update(of=WebPushSubscription,skip_locked=True).all()
        cached={}
        for subscription in subscriptions:
            uid=subscription.user_id
            user=db.get(User,uid)
            if subscription.credential_fingerprint!=hashlib.sha256(user.password_hash.encode()).hexdigest():
                subscription.enabled=False;continue
            if uid not in cached:
                user=db.get(User,uid);request=SimpleNamespace(session={'user_id':uid,'role':user.role})
                cached[uid]=inbox(db,request)
            read=db.get(NotificationRead,uid)
            floor=max(subscription.created_at,read.read_at if read else subscription.created_at)
            for title,url,stamp in cached[uid][:50]:
                if stamp<=floor:continue
                digest=hashlib.sha256(f'{title}|{url}|{stamp.isoformat()}'.encode()).hexdigest()
                item=db.query(WebPushDelivery).filter_by(subscription_id=subscription.id,event_key=digest).first()
                if item and (item.delivered or item.attempts>=5 or item.retry_at and item.retry_at>now()):continue
                if not item:item=WebPushDelivery(subscription_id=subscription.id,event_key=digest,attempts=0);db.add(item)
                item.attempts+=1
                item.delivered=send(db,subscription,{'title':'ESONE update','body':'You have a new activity update or reminder. Tap to view.','url':url,'tag':digest})
                item.retry_at=now()+timedelta(minutes=5*item.attempts)
                if not subscription.enabled:break

async def push_clock():
    while True:
        try:await asyncio.to_thread(dispatch)
        except Exception:log.warning('Push dispatcher unavailable; will retry')
        await asyncio.sleep(60)
