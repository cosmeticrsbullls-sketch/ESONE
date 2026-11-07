"""Read-only team activity and private activity sharing; no invented live GPS."""
import json
import math
import os
from datetime import datetime, time, timedelta, timezone
from html import escape
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from database.db import SessionLocal
from database.models import Activity, Attendance, Client, CollectionActivity, DemoBooking, User, Visit, SalesOrder
from modules.operations import access, business_today
from modules.workflows import now, page
from modules.pdf_reports import pdf_response, share_button, SHARE_SCRIPT

router = APIRouter()
MANAGEMENT = {'SUPER_ADMIN', 'MANAGEMENT', 'OFFICE'}
ZONE = ZoneInfo('Asia/Kolkata')

def utc_boundary(day):
    return datetime.combine(day, time.min, ZONE).astimezone(timezone.utc).replace(tzinfo=None)

def gps(lat, lon):
    return lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180

def map_url(lat, lon):
    return 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': f'{lat},{lon}'})

def team_data(db):
    today = business_today(); lower = utc_boundary(today); upper = utc_boundary(today+timedelta(days=1)); month = utc_boundary(today.replace(day=1))
    people = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    activities = db.query(Activity).all()
    visits = {v.activity_id: v for v in db.query(Visit).all()}
    demos = {d.activity_id: d for d in db.query(DemoBooking).all()}
    salons = {c.id: c for c in db.query(Client).all()}
    punches = db.query(Attendance).order_by(Attendance.punch_in_at.desc()).all()
    result=[]
    for user in people:
        attendance=next((p for p in punches if p.user_id==user.id),None)
        on_duty=bool(attendance and attendance.punch_out_at is None and lower <= attendance.punch_in_at < upper)
        owned=[a for a in activities if (a.assigned_user_id or a.created_by)==user.id or (a.id in demos and demos[a.id].assigned_educator_id==user.id)]
        completed=[a for a in activities if (a.assigned_user_id or a.created_by)==user.id and a.id in visits and visits[a.id].visit_type in {'SALES','COLLECTION','COURTESY'} and a.status=='COMPLETED' and a.completed_at is not None]
        today_count=sum(lower <= a.completed_at < upper for a in completed)
        month_count=sum(month <= a.completed_at < upper for a in completed)
        active=sorted([a for a in owned if a.status=='IN_PROGRESS'],key=lambda a:a.updated_at or a.created_at or datetime.min,reverse=True)
        label='No activity in progress' if on_duty else ('Punch-out recorded' if attendance and attendance.punch_out_at else 'Not punched in today')
        salon='—';activity_id=None
        if active:
            a=active[0];v=visits.get(a.id);label=(v.visit_type.title()+' Visit' if v else a.activity_type.replace('_',' ').title())+' in progress'
            if len(active)>1:label+=f' (+{len(active)-1} more)'
            salon=salons[a.client_id].business_name if a.client_id in salons else 'Unknown salon';activity_id=a.id
        samples=[]
        def add(stamp,lat,lon,source):
            if stamp and gps(lat,lon):samples.append((stamp,lat,lon,source))
        if attendance:
            add(attendance.punch_in_at,attendance.in_latitude,attendance.in_longitude,'Punch-in')
            add(attendance.punch_out_at,attendance.out_latitude,attendance.out_longitude,'Punch-out')
        for a in owned:
            if a.id in visits:
                v=visits[a.id];add(v.check_in_at,v.check_in_latitude,v.check_in_longitude,'Visit check-in');add(v.check_out_at,v.check_out_latitude,v.check_out_longitude,'Visit checkout')
            if a.id in demos:
                d=demos[a.id];add(d.started_at,d.execution_latitude,d.execution_longitude,'Demo execution')
        latest=max(samples,key=lambda s:s[0]) if samples else None
        # Off-duty employees retain counters; precise locations are only exposed during duty.
        location=None
        if latest and on_duty:
            stamp,lat,lon,source=latest
            location=dict(latitude=lat,longitude=lon,source=source,recorded_at=stamp.isoformat()+'Z',time=stamp.replace(tzinfo=timezone.utc).astimezone(ZONE).strftime('%d %b %Y %I:%M %p'),age_minutes=max(0,int((now()-stamp).total_seconds()/60)),url=map_url(lat,lon))
        result.append(dict(id=user.id,name=user.full_name,on_duty=on_duty,activity=label,salon=salon,activity_id=activity_id,today_visits=today_count,month_visits=month_count,location=location,open_activities=len(active),attendance_unclosed=bool(attendance and not attendance.punch_out_at and not on_duty)))
    return result

@router.get('/live-activity/data')
def live_data(request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:rows=team_data(db)
    return JSONResponse({'employees':rows,'updated_at':now().isoformat()+'Z'},headers={'Cache-Control':'no-store'})

@router.get('/live-activity',response_class=HTMLResponse)
def live_page(request:Request):
    denied=access(request)
    if denied is not None:return denied
    key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
    content='''<p><a href="/command-center">← Command Center</a></p><p>Recorded work activity · completed Sales, Collection and Courtesy visits · India calendar dates.</p><div id="team-summary" role="status"></div><div id="team-map" style="height:300px;border:1px solid #ddd;border-radius:12px;margin:18px 0;display:grid;place-items:center">Google Map connection is not configured. Use each employee’s View last location link.</div><p>Locations are last recorded GPS evidence, not continuous live tracking. Off-duty locations are hidden. Updates refresh every minute.</p><div class="table"><table><thead><tr><th>Employee</th><th>Status</th><th>Recorded activity</th><th>Salon / Location</th><th>Today visits</th><th>This month visits</th><th>Last GPS update (India)</th></tr></thead><tbody id="team-rows"></tbody></table></div><p id="team-error" role="status"></p>'''
    script=r'''<script>
(()=>{let map=null,circles=[],rows=[];const body=document.getElementById('team-rows'),error=document.getElementById('team-error');
function cell(row,text){const el=document.createElement('td');el.textContent=text;el.dataset.label=document.querySelectorAll('thead th')[row.children.length].textContent;row.append(el);return el;}
function paintMap(){if(!map)return;circles.forEach(c=>c.setMap(null));circles=[];const bounds=new google.maps.LatLngBounds();let count=0;rows.forEach(e=>{if(!e.location)return;const l=e.location,pos={lat:l.latitude,lng:l.longitude};bounds.extend(pos);count++;const circle=new google.maps.Circle({map,center:pos,radius:150,fillColor:'#ae842d',fillOpacity:0.8,strokeColor:'#805d1c',strokeWeight:2});circles.push(circle);circle.addListener('click',()=>{const box=document.createElement('div');box.textContent=e.name+' · '+e.activity+' · '+l.age_minutes+' min ago';new google.maps.InfoWindow({position:pos,content:box}).open({map});});});if(count){map.fitBounds(bounds);if(count===1)map.setZoom(14);}}
window.esoneTeamMap=()=>{const el=document.getElementById('team-map');el.textContent='';el.style.display='block';map=new google.maps.Map(el,{center:{lat:22.5,lng:71.5},zoom:6});paintMap();};
window.gm_authFailure=()=>{document.getElementById('team-map').textContent='Map unavailable. Use View last location below.';};
async function refresh(){try{const r=await fetch('/live-activity/data',{cache:'no-store'});if(!r.ok||r.redirected)throw Error();const data=await r.json();rows=data.employees;body.replaceChildren();rows.forEach(e=>{const tr=document.createElement('tr');cell(tr,e.name);cell(tr,e.on_duty?'On Duty':e.attendance_unclosed?'Attendance unclosed':'Off Duty');const work=cell(tr,e.activity);if(e.activity_id){const a=document.createElement('a');a.href='/activities/'+e.activity_id+'/share';a.textContent=' Activity details / Share';work.append(document.createElement('br'),a);}const place=cell(tr,e.salon);if(e.location){const a=document.createElement('a');a.href=e.location.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='View last location ↗';place.append(document.createElement('br'),a);}cell(tr,String(e.today_visits));cell(tr,String(e.month_visits));cell(tr,e.location?e.location.time+' · '+e.location.age_minutes+' min ago · '+e.location.source:'—');body.append(tr);});document.getElementById('team-summary').textContent=rows.length+' employees · '+rows.filter(e=>e.on_duty).length+' on duty · '+rows.reduce((n,e)=>n+e.today_visits,0)+' visits today · '+rows.reduce((n,e)=>n+e.month_visits,0)+' this month';error.textContent=rows.length?'':'No active employee accounts.';paintMap();}catch(e){error.textContent='Could not refresh. Displayed data may be outdated. Reload to try again.';}}
refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);
})();</script>'''
    if key:script+='<script async src="https://maps.googleapis.com/maps/api/js?'+escape(urlencode({'key':key,'callback':'esoneTeamMap','loading':'async'}),quote=True)+'"></script>'
    return HTMLResponse(page('Live Activity',content+script),headers={'Cache-Control':'no-store'})


def permitted(request,a,db):
    if request.session.get('role') in MANAGEMENT:return True
    uid=request.session['user_id']
    d=db.query(DemoBooking).filter_by(activity_id=a.id).first()
    return uid in {a.created_by,a.assigned_user_id} or bool(d and d.assigned_educator_id==uid)

@router.get('/activities/{activity_id}/share',response_class=HTMLResponse)
def activity_share(activity_id:int,request:Request):
    from modules.team import staff_access
    denied=staff_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        a=db.get(Activity,activity_id)
        if not a or not permitted(request,a,db):return HTMLResponse('Activity not found',404)
        c=db.get(Client,a.client_id)
        content=f'<h2>{escape(a.activity_type)} · {escape(c.business_name if c else "")}</h2><p>{escape(a.status)}</p><p>{escape(a.notes or "")}</p>'
    return page('Activity Details / Share',content+share_button(f'/activities/{activity_id}/pdf',f'ESONE_activity_{activity_id}.pdf')+SHARE_SCRIPT)

@router.get('/activities/{activity_id}/pdf')
def activity_pdf(activity_id:int,request:Request):
    from modules.team import staff_access
    denied=staff_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        a=db.get(Activity,activity_id)
        if not a or not permitted(request,a,db):return HTMLResponse('Activity not found',404)
        order=db.query(SalesOrder).filter_by(activity_id=a.id).first()
        if order:return RedirectResponse(f'/orders/{order.id}/pdf',303)
        c=db.get(Client,a.client_id);u=db.get(User,a.assigned_user_id or a.created_by) if (a.assigned_user_id or a.created_by) else None
        rows=[['Activity',a.activity_type],['Employee',u.full_name if u else 'Unassigned'],['Salon',c.business_name if c else ''],['Status',a.status],['Created (UTC)',a.created_at],['Completed (UTC)',a.completed_at],['Notes',a.notes or '']]
        v=db.query(Visit).filter_by(activity_id=a.id).first()
        if v:rows.extend([['Visit type',v.visit_type],['Check-in (UTC)',v.check_in_at],['Check-out (UTC)',v.check_out_at]])
        d=db.query(DemoBooking).filter_by(activity_id=a.id).first()
        if d:rows.extend([['Treatment',d.product_or_treatment],['Scheduled (India)',d.demo_date],['Result',d.conversion_status]])
        collection=db.query(CollectionActivity).filter_by(activity_id=a.id).first()
        if collection:rows.append(['Amount received (INR)',collection.amount_received or 0])
    return pdf_response('Activity Details',['Field','Value'],rows,filename=f'ESONE_activity_{activity_id}.pdf')

@router.get('/attendance/{record_id}/share',response_class=HTMLResponse)
@router.get('/attendance/{record_id}/pdf')
def attendance_share(record_id:int,request:Request):
    from modules.team import staff_access
    denied=staff_access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        p=db.get(Attendance,record_id)
        if not p or (request.session.get('role') not in MANAGEMENT and p.user_id!=request.session['user_id']):return HTMLResponse('Attendance not found',404)
        u=db.get(User,p.user_id)
        rows=[['Employee',u.full_name],['Punch-in (UTC)',p.punch_in_at],['Punch-out (UTC)',p.punch_out_at or 'Pending'],['In GPS',f'{p.in_latitude}, {p.in_longitude}'],['Out GPS',f'{p.out_latitude}, {p.out_longitude}' if p.punch_out_at else '—']]
    if request.url.path.endswith('/pdf'):return pdf_response('Attendance',['Field','Value'],rows,filename=f'ESONE_attendance_{record_id}.pdf')
    return page('Attendance / Share',share_button(f'/attendance/{record_id}/pdf',f'ESONE_attendance_{record_id}.pdf')+SHARE_SCRIPT)
