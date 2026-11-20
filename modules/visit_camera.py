"""Fresh browser capture challenge and private, durable visit evidence."""
from modules.workflows import now as utc_now
import base64
import hashlib
import math
import secrets
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import Response, FileResponse
from PIL import Image, UnidentifiedImageError
from database.db import SessionLocal
from database.models import User, Client, Activity, VisitCameraChallenge, VisitPhoto, AuditLog
from modules.device_access import require_device, check_csrf, digest
from modules.duty import require_duty

router=APIRouter()


def widget():
    return '''<section class="visit-camera"><h3>Fresh salon photo</h3><p>Use the rear camera to photograph the salon. Gallery upload is unavailable. Allow camera and location permissions.</p><video autoplay muted playsinline hidden style="width:100%;max-width:480px"></video><img alt="Salon photo preview" hidden style="width:100%;max-width:480px"><input type="hidden" name="photo_nonce"><input type="hidden" name="photo_data"><button type="button" data-camera-open>Open Camera</button><button type="button" data-camera-capture hidden>Capture</button><p data-camera-message role="status" aria-live="polite"></p></section><script src="/visit-camera.js?v=2" defer></script>'''


@router.get('/visit-camera.js', include_in_schema=False)
def script():
    return FileResponse(Path(__file__).with_suffix('.js'),media_type='application/javascript')


@router.post('/visit-camera/challenge')
def challenge(request:Request, csrf:str=Form(''), client_id:int=Form(...), latitude:float=Form(...), longitude:float=Form(...), accuracy:float=Form(...)):
    if request.session.get('role') not in {'SALES','SUPER_ADMIN','MANAGEMENT','OFFICE'}: raise HTTPException(403,'Access denied')
    check_csrf(request,csrf)
    if not all(math.isfinite(x) for x in (latitude,longitude,accuracy)) or not(-90<=latitude<=90 and -180<=longitude<=180 and 0<=accuracy<=200):
        raise HTTPException(400,'GPS accuracy must be within 200 metres. Retry outdoors.')
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session.get('user_id')).with_for_update().one()
        device=require_device(db,request)
        denied=require_duty(db,request)
        if denied is not None:return denied
        client=db.get(Client,client_id)
        if not client or client.status=='INACTIVE': raise HTTPException(400,'Select a registered active business first.')
        # Bound the number of outstanding challenges without touching used evidence.
        db.query(VisitCameraChallenge).filter_by(user_id=device.user_id, used_at=None).delete()
        raw=secrets.token_urlsafe(32); now=utc_now()
        db.add(VisitCameraChallenge(token_hash=digest(raw),user_id=device.user_id,device_id=device.id,client_id=client_id,latitude=latitude,longitude=longitude,accuracy=accuracy,created_at=now,expires_at=now+timedelta(minutes=5)))
    return {'nonce':raw,'expires_in':300}


def validate_photo(db,request,client_id,latitude,longitude,nonce,data):
    device=require_device(db,request)
    now=utc_now()
    record=db.query(VisitCameraChallenge).filter_by(token_hash=digest(nonce)).with_for_update().first() if nonce else None
    if not record or record.used_at or record.expires_at<=now or record.user_id!=device.user_id or record.device_id!=device.id or record.client_id!=client_id:
        raise HTTPException(409,'Take a fresh salon photo on this device for the selected business.')
    if abs(record.latitude-latitude)>0.000001 or abs(record.longitude-longitude)>0.000001:
        raise HTTPException(409,'Photo and visit GPS do not match. Retake the photo.')
    if not data.startswith('data:image/jpeg;base64,') or len(data)>1_400_000:
        raise HTTPException(400,'A camera JPEG photo below 1 MB is required.')
    try:
        raw=base64.b64decode(data.split(',',1)[1],validate=True)
        with Image.open(BytesIO(raw)) as image:
            if image.format!='JPEG' or not(160<=image.width<=2000 and 120<=image.height<=2000):
                raise ValueError('size')
            image.load(); image=image.convert('RGB'); image.thumbnail((960,960))
            out=BytesIO();image.save(out,format='JPEG',quality=80)
            jpeg=out.getvalue()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(400,'Invalid camera photo. Retake it.')
    photo_digest=hashlib.sha256(jpeg).hexdigest()
    if db.query(VisitPhoto).filter_by(digest=photo_digest).first():
        raise HTTPException(409,'This photo was already used. Take a new salon photo.')
    return record,jpeg,photo_digest


def save_photo(db,request,activity_id,client_id,evidence):
    record,jpeg,photo_digest=evidence
    record.used_at=utc_now()
    db.add(VisitPhoto(activity_id=activity_id,client_id=client_id,user_id=record.user_id,device_id=record.device_id,challenge_id=record.id,captured_at=record.created_at,received_at=record.used_at,latitude=record.latitude,longitude=record.longitude,accuracy=record.accuracy,digest=photo_digest,jpeg=jpeg))
    db.add(AuditLog(user_id=record.user_id,entity_type='Activity',entity_id=activity_id,action='VISIT_PHOTO',new_value=f'device={record.device_id};sha256={photo_digest}'))


@router.get('/activities/{activity_id}/photo')
def photo(activity_id:int,request:Request):
    from modules.live_activity import permitted
    with SessionLocal() as db:
        a=db.get(Activity,activity_id)
        if not a or not permitted(request,a,db): raise HTTPException(404,'Photo not found')
        item=db.query(VisitPhoto).filter_by(activity_id=activity_id).first()
        if not item: raise HTTPException(404,'No check-in photo recorded for this visit')
        return Response(item.jpeg,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
