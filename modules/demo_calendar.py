"""Read-only demo calendar; booking dates are stored in India local time."""
import calendar
from collections import Counter
from datetime import date, datetime, time, timedelta
from html import escape
from urllib.parse import urlencode

from database.models import Activity, Client, DemoBooking, User
from modules.operations import business_today


def calendar_view(db, month='', educator_id=0, day=None, q='', status=''):
    today=business_today()
    try:
        first=date.fromisoformat(month+'-01') if month else (day or today).replace(day=1)
        if not 1900<=first.year<=2100:raise ValueError()
        if day and (day.year,day.month)!=(first.year,first.month):raise ValueError()
    except ValueError:
        raise ValueError('Choose a valid month and a day within that month.')
    following=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
    previous=(first-timedelta(days=1)).replace(day=1)
    start=datetime.combine(first,time.min);end=datetime.combine(following,time.min)
    people=db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    if educator_id and not any(p.id==educator_id for p in people):raise ValueError('Choose an active educator.')
    query=db.query(DemoBooking,Activity,Client,User).join(Activity,Activity.id==DemoBooking.activity_id).join(Client,Client.id==Activity.client_id).outerjoin(User,User.id==DemoBooking.assigned_educator_id).filter(DemoBooking.demo_date>=start,DemoBooking.demo_date<end)
    if educator_id:query=query.filter(DemoBooking.assigned_educator_id==educator_id)
    all_records=query.order_by(DemoBooking.demo_date,DemoBooking.id).all()
    counts=Counter(d.demo_date.date() for d,a,c,u in all_records if a.status!='CANCELLED')
    def link(target_month, selected_day=None):
        params={'month':target_month.strftime('%Y-%m'),'educator_id':educator_id}
        if selected_day:params['day']=selected_day.isoformat()
        if q:params['q']=q
        if status:params['status']=status
        return '/demos?'+escape(urlencode(params),quote=True)
    cells=''.join(f'<div class="weekday">{name}</div>' for name in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(first.year,first.month):
        for number in week:
            if not number:
                cells+='<div class="calendar-day empty" aria-hidden="true"></div>';continue
            current=first.replace(day=number);count=counts[current]
            classes='calendar-day'+(' booked' if count else '')+(' today' if current==today else '')+(' selected' if current==day else '')
            label=f'{current.strftime("%d %B %Y")}: {count} demos booked'
            cells+=f'<a class="{classes}" href="{link(first,current)}" aria-label="{label}" data-date="{current}" data-demo-count="{count}"><strong>{number}</strong><small>{str(count)+" demo"+("s" if count!=1 else "") if count else "No demos"}</small></a>'
    options='<option value="0">All educators</option>'+''.join(f'<option value="{u.id}" {"selected" if u.id==educator_id else ""}>{escape(u.full_name)}</option>' for u in people)
    statuses='<option value="">All statuses</option>'+''.join(f'<option {"selected" if value==status else ""}>{value}</option>' for value in ['BOOKED','IN_PROGRESS','COMPLETED','CANCELLED'])
    rows=''
    shown=0
    for d,a,c,u in all_records:
        if day and d.demo_date.date()!=day:continue
        if status and a.status!=status:continue
        if q and q.lower() not in (c.business_name+' '+(c.phone or '')).lower():continue
        shown+=1
        rows+=f'<tr><td><a href="/demos/{d.id}">#{d.id}</a></td><td>{escape(c.business_name)}</td><td>{escape(d.product_or_treatment or "")}</td><td>{d.demo_date.strftime("%d %b %Y · %I:%M %p")}</td><td>{escape(u.full_name if u else "Unassigned")}</td><td>{escape(a.status)}</td><td>{escape(d.conversion_status or "")}</td></tr>'
    selected_day=day or (today if (today.year,today.month)==(first.year,first.month) else first)
    book_params={'demo_day':selected_day.isoformat(),'educator_id':educator_id}
    book_url='/demos/new?'+escape(urlencode(book_params),quote=True)
    heading=day.strftime('%d %B %Y') if day else first.strftime('%B %Y')
    prev_link=f'<a href="{link(previous)}">← Previous</a>' if previous.year>=1900 else '<span></span>'
    next_link=f'<a href="{link(following)}">Next →</a>' if following.year<=2100 else '<span></span>'
    book_action=f'<a class="primary" href="{book_url}">+ Book Demo {"on "+day.strftime("%d %b") if day else ""}</a>' if selected_day>=today else '<span>Past dates are shown for history.</span>'
    return f'''<div class="actions">{book_action}<a class="secondary" href="/clients?return_to=/demos/new#new-salon">+ New Salon</a><a class="secondary" href="/operations?kind=demos">History / Excel</a></div><form class="calendar-toolbar"><label>Month <input type="month" name="month" value="{first.strftime('%Y-%m')}" min="1900-01" max="2100-12"></label><label>Educator <select name="educator_id">{options}</select></label><label>Search <input name="q" value="{escape(q,quote=True)}" placeholder="Salon / phone"></label><label>Status <select name="status">{statuses}</select></label><button>Show Calendar</button></form><section class="calendar-panel" aria-label="Demo booking calendar"><div class="calendar-header">{prev_link}<h2>{first.strftime('%B %Y')}</h2>{next_link}</div><div class="calendar-grid">{cells}</div><p class="calendar-legend">Gold days have demos booked · Top blue line marks today · Click a day for its bookings.</p><p class="calendar-legend">Highlights include all non-cancelled demos for the chosen educator. No demos means no bookings recorded; check times before confirming availability. All demo times are India time.</p></section><div class="section-heading"><h2>{heading} · {shown} booking{'s' if shown!=1 else ''}</h2><a href="{link(first)}">Show whole month</a></div><div class="table"><table><tr><th>ID</th><th>Salon</th><th>Treatment</th><th>Date / time (India)</th><th>Educator</th><th>Status</th><th>Result</th></tr>{rows or '<tr><td colspan="7">No matching bookings. Choose a day and Book Demo to add one.</td></tr>'}</table></div>'''
