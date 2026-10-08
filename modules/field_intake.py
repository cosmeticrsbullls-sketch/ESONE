"""Location-first field onboarding; no schema changes or startup writes."""
import math
from datetime import datetime
from secrets import compare_digest, token_urlsafe
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, AuditLog, Client, User, Visit
from modules.workflows import token

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
    return f'''<div class="card field-intake"><h2>Field Visit</h2>
<style>.field-intake [hidden]{{display:none!important}}.field-intake label{{display:grid;gap:7px;margin:14px 0}}.field-intake input,.field-intake select,.field-intake textarea{{width:100%}}.field-intake fieldset{{border:0;padding:0;margin:0}}.field-intake .field-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}}.field-intake button{{margin:8px 6px 8px 0}}@media(max-width:600px){{.field-intake .field-grid{{grid-template-columns:1fr}}.field-intake button{{width:100%}}}}</style>
<button type="button" id="find-business">📍 CHECK IN VISIT</button>
<p id="field-message" role="status" aria-live="polite"></p>
<section id="field-picker" hidden><h3>Select business</h3>
<label>Search registered entries <input id="business-search" type="search" placeholder="Name / mobile / area"></label>
<label>Nearby businesses / first visits <select id="business-select"></select></label>
<p id="business-help"></p><button type="button" id="show-registration">+ ADD NEW VISIT — REGISTER NEW BUSINESS</button></section>
<form id="field-form" method="post" action="/field/start" hidden>
<input type="hidden" name="csrf" value="{token(request)}"><input type="hidden" name="submission" value="{token_urlsafe(24)}">
<input type="hidden" name="latitude"><input type="hidden" name="longitude"><input type="hidden" name="client_id">
<h3 id="visit-form-title">Visit details</h3><p id="selected-business"></p>
<fieldset id="field-registration" hidden disabled><legend>New business details</legend><div class="field-grid">
<label>Business name * <input name="business_name" required maxlength="200"></label>
<label>Business type <select name="client_type"><option value="SALON">Salon</option><option value="DISTRIBUTOR">Distributor</option><option value="ACADEMY">Academy</option><option value="OTHER">Other</option></select></label>
<label>Owner / contact person <input name="contact_person" maxlength="150"></label>
<label>Mobile * <input name="phone" type="tel" required maxlength="20"></label>
<label>Area <input name="area" maxlength="120"></label><label>City <input name="city" maxlength="120"></label>
<label>Address <input name="address" maxlength="500"></label><label>Pincode <input name="pincode" inputmode="numeric" maxlength="12"></label></div></fieldset>
<label>Visit purpose <select name="visit_type"><option value="SALES">Sales</option><option value="COURTESY">Courtesy</option><option value="COLLECTION">Collection</option></select></label>
<label>Visit notes <textarea name="notes" maxlength="4000" placeholder="Purpose / products to discuss / other details"></textarea></label>
<button type="submit">START VISIT</button><button type="button" id="choose-existing">← BACK TO BUSINESS LIST</button>
</form><script src="/field/intake.js?v=2" defer></script></div>'''


@router.get('/field/nearby')
def nearby(request: Request, latitude: float, longitude: float):
    denied = access(request)
    if denied is not None: return denied
    if not valid_gps(latitude, longitude): return HTMLResponse('Invalid GPS coordinates.', 400)
    nearby_items, unmapped = [], []
    with SessionLocal() as db:
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
def start(request: Request, latitude: float=Form(...), longitude: float=Form(...), visit_type: str=Form(...), csrf: str=Form(''), submission: str=Form(''), client_id: str=Form(''), business_name: str=Form(''), client_type: str=Form('SALON'), phone: str=Form(''), contact_person: str=Form(''), area: str=Form(''), city: str=Form(''), address: str=Form(''), pincode: str=Form(''), notes: str=Form('')):
    denied = access(request)
    if denied is not None: return denied
    if not csrf or not compare_digest(csrf, request.session.get('workflow_csrf', '')):
        return HTMLResponse('Please reload the form and try again.', 403)
    if not valid_gps(latitude, longitude) or visit_type not in {'SALES', 'COURTESY', 'COLLECTION'} or not 16 <= len(submission) <= 80:
        return HTMLResponse('Invalid visit details.', 400)
    if client_id and not client_id.isdecimal(): return HTMLResponse('Select a valid registered business.', 400)
    if not client_id and (not business_name.strip() or not phone.strip() or client_type not in {'SALON', 'DISTRIBUTOR', 'ACADEMY', 'OTHER'}):
        return HTMLResponse('Business name, mobile and valid business type are required.', 400)
    if any(len(value)>limit for value,limit in [(business_name,200),(phone,20),(contact_person,150),(area,120),(city,120),(address,500),(pincode,12),(notes,4000)]):
        return HTMLResponse('Business details are too long.', 400)
    with SessionLocal.begin() as db:
        uid = request.session['user_id']
        if client_id:
            db.query(User).filter_by(id=uid).with_for_update().one()
        else:
            # Lock in a consistent order before checking duplicate registrations.
            db.query(User).order_by(User.id).with_for_update().all()
        prior = db.query(AuditLog).filter_by(user_id=uid, action='FIELD_INTAKE', new_value=submission).first()
        if prior: return RedirectResponse(f'/visits/{prior.entity_id}', 303)
        if client_id:
            c = db.query(Client).filter_by(id=int(client_id)).with_for_update().first()
            if not c: return HTMLResponse('Business not found.', 404)
            if c.status == 'INACTIVE': return HTMLResponse('This business is inactive.', 409)
            if c.latitude is not None and c.longitude is not None:
                if not valid_gps(c.latitude,c.longitude) or distance(latitude,longitude,c.latitude,c.longitude)>RADIUS:
                    return HTMLResponse('Location mismatch. Check your location again.', 409)
            else:
                c.latitude, c.longitude = latitude, longitude
                db.add(AuditLog(user_id=uid,entity_type='Client',entity_id=c.id,action='GPS_REGISTERED',new_value=f'{latitude},{longitude}'))
        else:
            if db.query(Client).filter((Client.phone==phone.strip()) | (Client.business_name==business_name.strip())).first():
                return HTMLResponse('A business with this name or mobile already exists. Choose it from registered businesses, or ask management to review its location.', 409)
            c = Client(business_name=business_name.strip(), client_type=client_type, phone=phone.strip(), contact_person=contact_person.strip() or None, area=area.strip() or None, city=city.strip() or None, address=address.strip() or None, pincode=pincode.strip() or None, status='LEAD', client_category='B', latitude=latitude, longitude=longitude, created_by=uid, assigned_sales_id=uid if request.session['role']=='SALES' else None)
            db.add(c); db.flush()
            db.add(AuditLog(user_id=uid,entity_type='Client',entity_id=c.id,action='FIELD_REGISTERED',new_value=f'{latitude},{longitude}'))
        a = Activity(client_id=c.id,activity_type='FIELD_VISIT',source='FIELD',status='IN_PROGRESS',title=f'{visit_type} Visit',notes=notes.strip() or None,assigned_user_id=uid,created_by=uid)
        db.add(a); db.flush()
        v = Visit(activity_id=a.id,visit_type=visit_type,check_in_at=datetime.now(),check_in_latitude=latitude,check_in_longitude=longitude)
        db.add(v); db.flush()
        db.add(AuditLog(user_id=uid,entity_type='Activity',entity_id=a.id,action='FIELD_INTAKE',new_value=submission))
        db.add(AuditLog(user_id=uid,entity_type='VISIT',entity_id=v.id,action='START',new_value='location verified during field intake'))
        identity = a.id
    return RedirectResponse(f'/visits/{identity}',303)


@router.get('/field/intake.js', include_in_schema=False)
def script():
    from fastapi.responses import FileResponse
    from pathlib import Path
    return FileResponse(Path(__file__).with_name('field_intake.js'),media_type='application/javascript')
