"""Attendance gate for field work; administrative work keeps its existing access rules."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import or_
from fastapi.responses import HTMLResponse
from database.models import User, Attendance, Activity, Visit, DemoBooking

OFFICE_ROLES = {'SUPER_ADMIN', 'MANAGEMENT', 'OFFICE'}
MESSAGE = 'Punch In before starting or recording work. An older open attendance must be punched out first.'

def notice():
    return '<div class="card duty-notice" role="status"><p>'+MESSAGE+'</p><a class="secondary" href="/attendance">Go to Punch In / Out</a></div>'

def on_duty(db, uid):
    local_day = datetime.now(ZoneInfo('Asia/Kolkata')).date()
    lower = datetime.combine(local_day, time.min, ZoneInfo('Asia/Kolkata')).astimezone(timezone.utc).replace(tzinfo=None)
    upper = lower + timedelta(days=1)
    return db.query(Attendance.id).filter(Attendance.user_id==uid, Attendance.punch_out_at.is_(None), Attendance.punch_in_at>=lower, Attendance.punch_in_at<upper).first() is not None

def open_shift(db, uid):
    return db.query(Attendance.id).filter_by(user_id=uid,punch_out_at=None).first() is not None

def require_duty(db, request, *, office_work=False, finishing=False):
    if office_work and request.session.get('role') in OFFICE_ROLES:
        return None
    # Same first lock as punch-out, held until this work transaction commits.
    uid=request.session['user_id']
    db.query(User).filter_by(id=uid).with_for_update().one()
    if not on_duty(db, uid) and not (finishing and open_shift(db,uid)):
        return HTMLResponse(notice(), 409)

def active_field_work(db, uid):
    # Educator/assignee is responsible; unassigned work belongs to its creator.
    owned=or_(Activity.assigned_user_id==uid, (Activity.assigned_user_id.is_(None)) & (Activity.created_by==uid))
    visit=db.query(Activity.id).join(Visit, Visit.activity_id==Activity.id).filter(Activity.status=='IN_PROGRESS', owned).first()
    demo=db.query(Activity.id).join(DemoBooking, DemoBooking.activity_id==Activity.id).filter(Activity.status=='IN_PROGRESS', or_(DemoBooking.assigned_educator_id==uid, owned)).first()
    return bool(visit or demo)
