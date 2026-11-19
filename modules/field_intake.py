"""One-form completed visits for registered businesses, with GPS and camera evidence."""
from modules.workflows import now as utc_now
from modules.duty import require_duty, on_duty, notice
import math
from secrets import compare_digest, token_urlsafe
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, User, Visit
from modules.workflows import token
from modules.visit_camera import widget, validate_photo, save_photo

router = APIRouter()
RADIUS = 200


def access(request):
    if not request.session.get('user_id'):
        return HTMLResponse('Please sign in again.', 401)
    if request.session.get('role') not in {'SALES', 'SUPER_ADMIN', 'MANAGEMENT', 'OFFICE'}:
        return HTMLResponse('Access Denied', 403)


def valid_gps(lat, lon):
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def distance(lat, lon, other_lat, other_lon):
    a = math.sin(math.radians(other_lat-lat)/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(other_lat))*math.sin(math.radians(other_lon-lon)/2)**2
    return 12742000 * math.asin(math.sqrt(min(1, max(0, a))))


def intake(request):
    with SessionLocal() as db:
        if not on_duty(db, request.session['user_id']):
            return f'<input type="hidden" name="csrf" value="{token(request)}">'+notice()+'<button disabled aria-disabled="true">📍 Find / Select Business — Punch In first</button>'
    return f'''<div class="card field-intake"><h2>Add Visit</h2><p>Select a business, fill in the visit details and tap Finish.</p>
<style>.field-intake [hidden]{{display:none!important}}.field-intake #field-submit-message{{padding:12px;border:1px solid #d7b666;border-radius:8px;background:#fff8e8;color:#795415}}.field-intake #field-submit-message.has-error{{border-color:#df9a92;background:#fff2ef;color:#9a3026}}.field-intake label{{display:grid;gap:7px;margin:14px 0}}.field-intake input,.field-intake select,.field-intake textarea{{width:100%}}.field-intake fieldset{{border:0;padding:0;margin:0}}.field-intake .field-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}}.field-intake button{{margin:8px 6px 8px 0}}@media(max-width:600px){{.field-intake .field-grid{{grid-template-columns:1fr}}.field-intake button{{width:100%}}}}</style>
<button type="button" id="find-business">📍 Find / Select Business</button>
<p id="field-message" role="status" aria-live="polite"></p>
<section id="field-picker" hidden><h3>Select business</h3>
<label>Search registered entries <input id="business-search" type="search" placeholder="Name / mobile / area"></label>
<label>Registered businesses near you / first GPS visits <select id="business-select"></select></label>
<p id="business-help"></p><p>Business missing? Register it using Add Business on Home, then return to start your visit.</p><a class="secondary" href="/workspace">Back to Home</a></section>
<form id="field-form" method="post" action="/field/start" hidden novalidate>
<input type="hidden" name="csrf" value="{token(request)}"><input type="hidden" name="submission" value="{token_urlsafe(24)}">
<input type="hidden" name="latitude"><input type="hidden" name="longitude"><input type="hidden" name="client_id">
<h3 id="visit-form-title">Visit details</h3><p id="selected-business"></p>
<label>Visit purpose <select name="visit_type"><option value="SALES">Sales</option><option value="COURTESY">Courtesy</option><option value="COLLECTION">Collection</option></select></label>
<label>Visit details / outcome * <textarea name="notes" required maxlength="4000" placeholder="Products discussed / result / next follow-up"></textarea></label>
<p id="field-submit-message" role="status" aria-live="polite" tabindex="-1" hidden></p>
{widget()}
<button type="submit">Finish</button><button type="button" id="choose-existing">← BACK TO BUSINESS LIST</button>
</form><script src="/field/intake.js?v=5" defer></script></div>'''


@router.get('/field/intake', response_class=HTMLResponse)
def intake_page(request: Request, visit_type: str="SALES"):
    if not request.session.get('user_id'):
        return RedirectResponse('/login', 303)
    denied = access(request)
    if denied is not None:
        return denied
    from modules.workflows import page
    if visit_type not in {'SALES','COLLECTION','COURTESY'}:return HTMLResponse('Invalid visit purpose',400)
    content=intake(request).replace(f'<option value="{visit_type}">',f'<option value="{visit_type}" selected>')
    return HTMLResponse(page('Add Visit', content))


@router.get('/field/nearby')
def nearby(request: Request, latitude: float, longitude: float):
    denied = access(request)
    if denied is not None: return denied
    if not valid_gps(latitude, longitude): return HTMLResponse('Invalid GPS coordinates.', 400)
    nearby_items, unmapped = [], []
    with SessionLocal() as db:
        denied=require_duty(db, request)
        if denied is not None:return denied
        for c in db.query(Client).filter(Client.status != 'INACTIVE').order_by(Client.business_name).all():
            item = {'id': c.id, 'name': c.business_name, 'type': c.client_type, 'area': c.area or c.city or '', 'phone': c.phone or ''}
            if c.latitude is None or c.longitude is None:
                unmapped.append(item)
            elif valid_gps(c.latitude, c.longitude):
                meters = distance(latitude, longitude, c.latitude, c.longitude)
                if meters <= RADIUS:
                    item['distance_m'] = round(meters)
                    nearby_items.append(item)
    nearby_items.sort(key=lambda item: item['distance_m'])
    return {'nearby': nearby_items, 'unmapped': unmapped, 'radius_m': RADIUS}


@router.post('/field/start')
def start(request: Request, latitude: float=Form(...), longitude: float=Form(...), visit_type: str=Form(...), csrf: str=Form(''), submission: str=Form(''), client_id: str=Form(''), notes: str=Form(''), photo_nonce: str=Form(''), photo_data: str=Form('')):
    denied = access(request)
    if denied is not None: return denied
    if not csrf or not compare_digest(csrf, request.session.get('workflow_csrf', '')):
        return HTMLResponse('Please reload the form and try again.', 403)
    if not valid_gps(latitude, longitude) or visit_type not in {'SALES', 'COURTESY', 'COLLECTION'} or not 16 <= len(submission) <= 80:
        return HTMLResponse('Invalid visit details.', 400)
    if client_id and not client_id.isdecimal(): return HTMLResponse('Select a valid registered business.', 400)
    if not client_id: return HTMLResponse('Register the business using Add Business on Home first.',400)
    if len(notes)>4000: return HTMLResponse('Visit details are too long.',400)
    with SessionLocal.begin() as db:
        uid = request.session['user_id']
        db.query(User).filter_by(id=uid).with_for_update().one()
        denied=require_duty(db, request)
        if denied is not None:return denied
        prior = db.query(AuditLog).filter_by(user_id=uid, action='FIELD_INTAKE', new_value=submission).first()
        if prior: return JSONResponse({'redirect':'/workspace'})
        if not client_id: return HTMLResponse('Register the business using Add Business on Home first.',400)
        c = db.query(Client).filter_by(id=int(client_id)).with_for_update().first()
        if not c: return HTMLResponse('Business not found.', 404)
        if c.status == 'INACTIVE': return HTMLResponse('This business is inactive.', 409)
        if c.latitude is not None and c.longitude is not None:
            if not valid_gps(c.latitude,c.longitude) or distance(latitude,longitude,c.latitude,c.longitude)>RADIUS:
                return HTMLResponse('Location mismatch. Check your location again.', 409)
        evidence=validate_photo(db,request,int(client_id),latitude,longitude,photo_nonce,photo_data)
        if not notes.strip(): return HTMLResponse('Enter visit details / outcome.',400)
        if c.latitude is None or c.longitude is None:
            c.latitude, c.longitude = latitude, longitude
            db.add(AuditLog(user_id=uid,entity_type='Client',entity_id=c.id,action='GPS_REGISTERED',new_value=f'{latitude},{longitude}'))
        a = Activity(client_id=c.id,activity_type='FIELD_VISIT',source='FIELD_FORM',status='COMPLETED',completed_at=utc_now(),title=f'{visit_type} Visit',notes=notes.strip() or None,assigned_user_id=uid,created_by=uid)
        db.add(a); db.flush()
        v = Visit(activity_id=a.id,visit_type=visit_type,check_in_at=utc_now(),check_in_latitude=latitude,check_in_longitude=longitude,outcome='VISIT_RECORDED')
        db.add(v); db.flush()
        save_photo(db,request,a.id,c.id,evidence)
        db.add(AuditLog(user_id=uid,entity_type='Activity',entity_id=a.id,action='FIELD_INTAKE',new_value=submission))
        db.add(AuditLog(user_id=uid,entity_type='VISIT',entity_id=v.id,action='VISIT_RECORDED',new_value='Single-form visit; GPS and salon photo recorded at Finish; duration not measured'))
    request.session['business_registration_notice']='Visit recorded successfully.'
    return JSONResponse({'redirect':'/workspace'})


@router.get('/field/intake.js', include_in_schema=False)
def script():
    from fastapi.responses import FileResponse
    from pathlib import Path
    return FileResponse(Path(__file__).with_name('field_intake.js'),media_type='application/javascript')
