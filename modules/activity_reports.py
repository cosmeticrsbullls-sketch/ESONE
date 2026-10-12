"""Employee scoped daily/monthly activity and attendance reports."""
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from html import escape
from urllib.parse import urlencode
from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from database.db import SessionLocal
from database.models import Activity,User,Client,Attendance,SalesOrder,CollectionActivity,DemoBooking,DemoEducator
from modules.team import staff_access,MANAGEMENT,gps_link
from modules.workflows import page
from modules.operations import business_today,xlsx
from modules.pdf_reports import pdf_response,share_button,SHARE_SCRIPT
router=APIRouter()

def report_range(period,day,month,start,end):
    today=business_today()
    if start or end:
        first=start or end;last=end or start
    elif period=='daily':first=last=day or today
    elif period=='monthly':
        first=date.fromisoformat((month or today.strftime('%Y-%m'))+'-01');last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    else:raise ValueError('Choose daily or monthly report')
    if first>last or (last-first).days>366:raise ValueError('Choose a report range of at most one year')
    return first,last

def scope(request,employee_id):
    if request.session.get('role') not in MANAGEMENT:
        if employee_id and employee_id!=request.session['user_id']:raise PermissionError()
        return request.session['user_id']
    return employee_id

def report_data(db,employee_id,first,last):
    zone=ZoneInfo('Asia/Kolkata')
    lower=datetime.combine(first,time.min).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    upper=datetime.combine(last+timedelta(days=1),time.min).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    headers=['Employee','Activity','Salon','Status','Created / completed (India)','Details']
    query=db.query(Activity,Client).join(Client,Client.id==Activity.client_id).filter(or_((Activity.created_at>=lower)&(Activity.created_at<upper),(Activity.completed_at>=lower)&(Activity.completed_at<upper)))
    if employee_id:query=query.filter(or_(Activity.created_by==employee_id,Activity.assigned_user_id==employee_id))
    people={u.id:u.full_name for u in db.query(User).all()};rows=[]
    def local(dt):return dt.replace(tzinfo=timezone.utc).astimezone(zone).strftime('%d %b %Y %H:%M') if dt else ''
    for a,c in query.order_by(Activity.created_at.desc()).all():
        detail=a.title or ''
        if a.activity_type=='ORDER':
            o=db.query(SalesOrder).filter_by(activity_id=a.id).first()
            if o:detail=f'{o.order_number} | INR {o.total_amount}'
        elif a.activity_type=='COLLECTION':
            receipt=db.query(CollectionActivity).filter_by(activity_id=a.id).first()
            if receipt:detail+=f' | Received INR {receipt.amount_received or 0}'
        rows.append([people.get(a.created_by or a.assigned_user_id,'Unassigned'),a.activity_type,c.business_name,a.status,local(a.created_at)+(' / '+local(a.completed_at) if a.completed_at else ''),detail])
    punches=db.query(Attendance).filter(Attendance.punch_in_at>=lower,Attendance.punch_in_at<upper)
    if employee_id:punches=punches.filter_by(user_id=employee_id)
    for p in punches.order_by(Attendance.punch_in_at.desc()).all():
        detail=f'In GPS {p.in_latitude},{p.in_longitude} ({p.in_accuracy:.0f}m)'
        if p.punch_out_at:detail+=f' | Out {local(p.punch_out_at)} GPS {p.out_latitude},{p.out_longitude}'
        rows.append([people.get(p.user_id,''),'ATTENDANCE','', 'PUNCHED_OUT' if p.punch_out_at else 'PUNCH_OUT_PENDING',local(p.punch_in_at),detail])
    return headers,rows

@router.get('/activity-reports',response_class=HTMLResponse)
def activity_report(request:Request,employee_id:int=0,period:str='daily',day:date|None=None,month:str='',start:date|None=None,end:date|None=None):
    denied=staff_access(request)
    if denied is not None:return denied
    try:employee_id=scope(request,employee_id);first,last=report_range(period,day,month,start,end)
    except PermissionError:return HTMLResponse('Access Denied',403)
    except ValueError as e:return HTMLResponse(escape(str(e)),400)
    with SessionLocal() as db:
        headers,rows=report_data(db,employee_id,first,last)
        options='<option value="0">All employees</option>'+''.join(f'<option value="{u.id}" {"selected" if employee_id==u.id else ""}>{escape(u.full_name)}</option>' for u in db.query(User).order_by(User.full_name).all())
    params=urlencode(dict(employee_id=employee_id,start=first,end=last,period=period))
    employee=f'<label>Employee<select name="employee_id">{options}</select></label>' if request.session.get('role') in MANAGEMENT else ''
    form=f'<form>{employee}<label>Period<select name="period"><option value="daily" {"selected" if period=="daily" else ""}>Daily</option><option value="monthly" {"selected" if period=="monthly" else ""}>Monthly</option></select></label><label>Daily date<input type="date" name="day" value="{day or business_today()}"></label><label>Month<input type="month" name="month" value="{month or business_today().strftime("%Y-%m")}"></label><button>Show Report</button></form>'
    table='<div class="table"><table><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in r)+'</tr>' for r in rows)+'</table></div>'
    return page('Employee Activity Reports',f'<p>{first} to {last} (India) · {len(rows)} records. Activities show booking/creation date; attendance includes GPS evidence.</p>'+form+f'<a href="/activity-reports/export?{escape(params)}">Download Excel</a>'+share_button('/activity-reports/pdf?'+params)+table+SHARE_SCRIPT)

@router.get('/activity-reports/{format}')
def activity_export(format:str,request:Request,employee_id:int=0,period:str='daily',day:date|None=None,month:str='',start:date|None=None,end:date|None=None):
    denied=staff_access(request)
    if denied is not None:return denied
    if format not in {'pdf','export'}:return HTMLResponse('Not found',404)
    try:employee_id=scope(request,employee_id);first,last=report_range(period,day,month,start,end)
    except PermissionError:return HTMLResponse('Access Denied',403)
    except ValueError as e:return HTMLResponse(escape(str(e)),400)
    with SessionLocal() as db:headers,rows=report_data(db,employee_id,first,last)
    if format=='pdf':return pdf_response('Employee Activity',headers,rows,summary=f'{first} to {last} (India) | employee '+str(employee_id or 'All'))
    return xlsx(headers,rows,'employee_activity')
