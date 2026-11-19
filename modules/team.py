from modules.duty import require_duty, on_duty, notice, active_field_work
"""Employee profiles and GPS attendance, without editing system evidence."""
from datetime import date
from html import escape
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from database.db import SessionLocal
from database.models import User, EmployeeProfile, Attendance
from modules.workflows import hidden, page, now, audit
from modules.field_intake import valid_gps
from modules.operations import access
from secrets import compare_digest
import math
router=APIRouter()
MANAGEMENT={'SUPER_ADMIN','MANAGEMENT','OFFICE'}

def staff_access(request,csrf=None):
    if not request.session.get('user_id'):return RedirectResponse('/login',303)
    if csrf is not None and (not csrf or not compare_digest(csrf,request.session.get('workflow_csrf',''))):return HTMLResponse('Reload the form and try again.',403)

GPS_SCRIPT='''<script>document.querySelectorAll('[data-gps-form]').forEach(f=>{f.addEventListener('submit',e=>{if(f.dataset.ready==='yes')return;e.preventDefault();const b=f.querySelector('button');b.disabled=true;b.textContent='Getting GPS…';if(!navigator.geolocation){b.disabled=false;f.querySelector('[role=status]').textContent='GPS is unavailable. Open ESONE in a location-enabled browser.';return;}navigator.geolocation.getCurrentPosition(p=>{for(const [k,v] of Object.entries({latitude:p.coords.latitude,longitude:p.coords.longitude,accuracy:p.coords.accuracy}))f.elements[k].value=v;f.dataset.ready='yes';f.requestSubmit();},()=>{b.disabled=false;b.textContent='Retry GPS';f.querySelector('[role=status]').textContent='Allow location access and enable GPS to punch attendance.';},{enableHighAccuracy:true,timeout:20000,maximumAge:0});});});</script>'''

def gps_link(lat,lon):
    return f'<a target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&amp;query={lat},{lon}">View GPS on map</a>' if lat is not None and lon is not None else '—'

@router.get('/attendance',response_class=HTMLResponse)
def attendance(request:Request,employee_id:int=0):
    denied=staff_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        manager=request.session.get('role') in MANAGEMENT
        if not manager and employee_id not in {0,request.session['user_id']}:return HTMLResponse('Access Denied',403)
        query=db.query(Attendance)
        if not manager or employee_id:query=query.filter_by(user_id=employee_id or request.session['user_id'])
        records=query.order_by(Attendance.id.desc()).limit(500 if manager else 31).all()
        people={u.id:u.full_name for u in db.query(User).all()}
        opened=db.query(Attendance).filter_by(user_id=request.session['user_id'],punch_out_at=None).first()
        options='<option value="0">All employees</option>'+''.join(f'<option value="{uid}" {"selected" if uid==employee_id else ""}>{escape(name)}</option>' for uid,name in people.items())
        filter_form=f'<form><label>Employee<select name="employee_id">{options}</select></label><button>Show Attendance</button></form>' if manager else ''
        blocked=bool(opened and active_field_work(db,request.session['user_id']))
        blocked_message='<p role="status">Complete your active Visit or Demo before Punch Out.</p>' if blocked else ''
        disabled=' disabled aria-disabled="true"' if blocked else ''
        action='OUT' if opened else 'IN'
        rows=''.join(f'<tr><td>{escape(people.get(r.user_id,''))}</td><td>{r.punch_in_at} UTC</td><td>{gps_link(r.in_latitude,r.in_longitude)} · {r.in_accuracy:.0f} m</td><td>{str(r.punch_out_at)+" UTC" if r.punch_out_at else "Pending punch out"}</td><td>{gps_link(r.out_latitude,r.out_longitude)}</td><td><a href="/attendance/{r.id}/share">Share</a></td></tr>' for r in records)
    return page('Attendance',filter_form+blocked_message+f'<p>Actual punch times and GPS are recorded automatically.</p><form method="post" data-gps-form>{hidden(request)}<input type="hidden" name="action" value="{action}"><input type="hidden" name="latitude"><input type="hidden" name="longitude"><input type="hidden" name="accuracy"><button{disabled}>Punch {action.title()}</button><p role="status"></p></form><div class="table"><table><tr><th>Employee</th><th>Punch in</th><th>In GPS</th><th>Punch out</th><th>Out GPS</th><th>Share</th></tr>{rows}</table></div>'+GPS_SCRIPT)

@router.post('/attendance')
def punch(request:Request,action:str=Form(...),latitude:float=Form(...),longitude:float=Form(...),accuracy:float=Form(...),csrf:str=Form('')):
    denied=staff_access(request,csrf)
    if denied is not None:return denied
    if action not in {'IN','OUT'} or not valid_gps(latitude,longitude) or not math.isfinite(accuracy) or not 0<=accuracy<=200:return HTMLResponse('Use a fresh GPS reading accurate to 200 metres or better.',400)
    with SessionLocal.begin() as db:
        db.query(User).filter_by(id=request.session['user_id']).with_for_update().one()
        opened=db.query(Attendance).filter_by(user_id=request.session['user_id'],punch_out_at=None).with_for_update().first()
        if action=='IN':
            if opened:return HTMLResponse('Punch out the open attendance first.',409)
            record=Attendance(user_id=request.session['user_id'],punch_in_at=now(),in_latitude=latitude,in_longitude=longitude,in_accuracy=accuracy);db.add(record);db.flush()
        else:
            if not opened:return HTMLResponse('Punch in before punching out.',409)
            if active_field_work(db, request.session['user_id']):
                return HTMLResponse('<p>Complete your active Visit or Demo before Punch Out.</p><a href="/visits">My visits</a> · <a href="/demos">My demos</a>',409)
            record=opened;record.punch_out_at=now();record.out_latitude=latitude;record.out_longitude=longitude;record.out_accuracy=accuracy
        audit(db,request,'Attendance',record.id,'PUNCH_'+action)
    return RedirectResponse('/workspace',303)

@router.get('/employees',response_class=HTMLResponse)
def employees(request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        rows=''
        for u,p in db.query(User,EmployeeProfile).outerjoin(EmployeeProfile,EmployeeProfile.user_id==User.id).order_by(User.full_name).all():
            rows+=f'<tr><td><a href="/employees/{u.id}">{escape(u.full_name)}</a></td><td>{escape(u.email)}</td><td>{escape(u.role)}</td><td>{"Active" if u.is_active else "Inactive"}</td><td>{escape(p.employee_code or "") if p else ""}</td><td>{escape(p.phone or "") if p else ""}</td><td>{escape(p.base_city or "") if p else ""}</td></tr>'
    return page('Employee Master','<p>Registered accounts appear here. Profile edits preserve login email, role and approval.</p><a href="/users">Account registration / access</a><div class="table"><table><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Code</th><th>Phone</th><th>Base city</th></tr>'+rows+'</table></div>')

FIELDS={'employee_code':40,'phone':20,'designation':100,'department':100,'base_city':100,'joining_date':10,'emergency_contact':100}
@router.get('/employees/{user_id}',response_class=HTMLResponse)
def profile(user_id:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        u=db.get(User,user_id);p=db.get(EmployeeProfile,user_id)
        if not u:return HTMLResponse('Employee not found',404)
        inputs=''.join(f'<label>{key.replace("_"," ").title()}<input name="{key}" maxlength="{limit}" type="{"date" if key=="joining_date" else "text"}" value="{escape(str(getattr(p,key) or "") if p else "",quote=True)}"></label>' for key,limit in FIELDS.items())
        return page('Employee Details',f'<h2>{escape(u.full_name)}</h2><p>{escape(u.email)} · {escape(u.role)}</p><form method="post">{hidden(request)}{inputs}<button>Save Details</button></form>')

@router.post('/employees/{user_id}')
async def save_profile(user_id:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    form=await request.form();denied=staff_access(request,str(form.get('csrf','')))
    if denied is not None:return denied
    values={key:str(form.get(key,'')).strip() for key in FIELDS}
    if any(len(values[k])>limit for k,limit in FIELDS.items()):return HTMLResponse('Detail too long',400)
    try:
        if values['joining_date']:date.fromisoformat(values['joining_date'])
    except ValueError:return HTMLResponse('Invalid joining date',400)
    with SessionLocal.begin() as db:
        if not db.query(User).filter_by(id=user_id).with_for_update().first():return HTMLResponse('Employee not found',404)
        code=values['employee_code'] or None
        if code and db.query(EmployeeProfile).filter(EmployeeProfile.employee_code==code,EmployeeProfile.user_id!=user_id).first():return HTMLResponse('Employee code already used',409)
        p=db.get(EmployeeProfile,user_id)
        if not p:p=EmployeeProfile(user_id=user_id);db.add(p)
        for key,value in values.items():setattr(p,key,value or None)
        p.updated_at=now();audit(db,request,'EmployeeProfile',user_id,'PROFILE_UPDATED')
    return RedirectResponse('/employees',303)

def business_text(value):
    return ' '.join((value or '').casefold().split())


def business_phone(value):
    digits = ''.join(char for char in (value or '') if char.isdecimal())
    if len(digits) == 12 and digits.startswith('91'):
        return digits[2:]
    if len(digits) == 11 and digits.startswith('0'):
        return digits[1:]
    return digits


@router.get('/business-search')
def business_search(request: Request, q: str = ''):
    denied = staff_access(request)
    if denied is not None:
        return denied
    if len(q) > 200:
        return HTMLResponse('Search must be 200 characters or fewer.', 400)
    term = business_text(q)
    phone = business_phone(q)
    if not term:
        return JSONResponse({'matches': []}, headers={'Cache-Control': 'no-store'})
    from database.models import Client
    with SessionLocal() as db:
        matches = []
        for client in db.query(Client).order_by(Client.business_name, Client.id):
            name_match = term in business_text(client.business_name)
            phone_match = bool(phone) and phone in business_phone(client.phone)
            if name_match or phone_match:
                matches.append({
                    'id': client.id, 'name': client.business_name,
                    'phone': client.phone or '', 'area': client.area or client.city or '',
                    'active': client.status != 'INACTIVE',
                })
            if len(matches) == 20:
                break
    return JSONResponse({'matches': matches}, headers={'Cache-Control': 'no-store'})


@router.get('/salons/new', response_class=HTMLResponse)
def salon_new(request: Request, return_to: str = ''):
    denied = staff_access(request)
    if denied is not None:
        return denied
    content = f'''
    <style>
      .business-registration {{max-width:720px}}
      .business-registration [hidden] {{display:none!important}}
      .business-registration .business-results {{margin:0;padding:0;list-style:none;border:1px solid #cbd5df;border-radius:8px;overflow:hidden}}
      .business-registration .business-results button {{display:block;width:100%;text-align:left;border-radius:0;margin:0;padding:14px;white-space:normal}}
      .business-registration .business-results small {{display:block}}
      .business-registration label {{display:block;margin:16px 0}}
      .business-registration input,.business-registration select {{width:100%;max-width:100%}}
      .business-registration .notice {{padding:12px;background:#fff7e5;border-radius:8px}}
    </style>
    <div class="business-registration">
      <p>Search first to check whether the business is already registered.</p>
      <label for="registration-search">Business name or mobile number</label>
      <input id="registration-search" type="search" maxlength="200" autocomplete="off"
             placeholder="Type business name or mobile" aria-controls="registration-results">
      <p id="registration-status" role="status" aria-live="polite"></p>
      <ul id="registration-results" class="business-results" aria-label="Matching businesses" hidden></ul>
      <section id="registered-business" hidden>
        <h2>Already registered</h2><p id="registered-business-name"></p>
        <p>Select this business when starting Sales, Collection, Demo or Order.</p>
        <a class="primary" href="/workspace">Back to Home</a>
      </section>
      <button type="button" id="add-business" hidden>+ Register New Business</button>
      <form id="business-registration-form" method="post" action="/salons/new" hidden>
        {hidden(request)}
        <label>Business name<input name="business_name" maxlength="200" required></label>
        <label>Mobile number<input name="phone" type="tel" maxlength="20" required></label>
        <label>Business type<select name="client_type"><option value="SALON">Salon</option><option value="DISTRIBUTOR">Distributor</option><option value="ACADEMY">Academy</option><option value="OTHER">Other</option></select></label>
        <details><summary>Additional details (optional)</summary>
          <label>Contact person<input name="contact_person" maxlength="150"></label>
          <label>Area<input name="area" maxlength="120"></label>
          <label>City<input name="city" maxlength="120"></label>
          <label>Address<textarea name="address" maxlength="500"></textarea></label>
        </details>
        <p id="registration-error" role="alert" hidden></p>
        <button type="submit">Save Business</button>
      </form>
      <p>GPS is captured when an employee checks in for a visit.</p>
      <p><a href="/workspace">Home</a></p>
      <noscript>Enable JavaScript to search and register a business.</noscript>
    </div>
    <script src="/business-registration.js?v=1" defer></script>'''
    return HTMLResponse(page('Add Business', content), headers={'Cache-Control': 'no-store'})


@router.get('/business-registration.js', include_in_schema=False)
def business_registration_script():
    from pathlib import Path
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).with_name('business_registration.js'),
                        media_type='application/javascript')


@router.post('/salons/new')
async def salon_create(request: Request):
    denied = staff_access(request)
    if denied is not None:
        return denied
    form = await request.form()
    denied = staff_access(request, str(form.get('csrf', '')))
    if denied is not None:
        return denied
    fields = {'business_name': 200, 'phone': 20, 'contact_person': 150,
              'area': 120, 'city': 120, 'address': 500}
    values = {key: str(form.get(key, '')).strip() for key in fields}
    client_type = str(form.get('client_type', 'SALON'))
    invalid = (not values['business_name'] or not business_phone(values['phone'])
               or client_type not in {'SALON', 'DISTRIBUTOR', 'ACADEMY', 'OTHER'}
               or any(len(values[key]) > limit for key, limit in fields.items()))
    if invalid:
        return JSONResponse({'detail': 'Enter a business name, mobile number and valid business type.'}, status_code=400)
    from database.models import Client
    with SessionLocal.begin() as db:
        # All registration paths acquire user locks in the same order.
        db.query(User).order_by(User.id).with_for_update().all()
        denied = require_duty(db, request, office_work=True)
        if denied is not None:
            return denied
        name = business_text(values['business_name'])
        phone = business_phone(values['phone'])
        matches = [
            client for client in db.query(Client).order_by(Client.id)
            if business_text(client.business_name) == name or business_phone(client.phone) == phone
        ]
        if matches:
            return JSONResponse({
                'detail': 'This business is already registered. Select the existing business.',
                'matches': [{'name': c.business_name, 'phone': c.phone or '',
                             'active': c.status != 'INACTIVE'} for c in matches[:20]],
            }, status_code=409)
        client = Client(
            **values, client_type=client_type, created_by=request.session['user_id'],
            assigned_sales_id=request.session['user_id'] if request.session['role'] == 'SALES' else None,
        )
        db.add(client)
        db.flush()
        audit(db, request, 'Client', client.id, 'SALON_REGISTERED')
        label = client.business_name
    request.session['business_registration_notice'] = (
        f'Business registered successfully: {label}. Select it when starting an activity.'
    )
    if 'application/json' in request.headers.get('accept', ''):
        return JSONResponse({'redirect': '/workspace'})
    return RedirectResponse('/workspace', 303)
