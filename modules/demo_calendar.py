"""Calendar-only demo overview and calendar-first booking date picker."""
import calendar
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from html import escape
from urllib.parse import urlencode
from database.models import Activity, Client, DemoBooking, DemoBookingRequest, User, DemoEducator
from modules.operations import business_today

MARKERS={'BOOKED':'🟢 Booked','PENDING':'🟠 Approval Pending','REJECTED':'🔴 Rejected'}


def calendar_view(db, month='', educator_id=0, day=None, q='', status='', *, booking=False, client_id=0, viewer_id=None, can_review=False):
    today=business_today()
    try:
        first=date.fromisoformat(month+'-01') if month else (day or today).replace(day=1)
        if not 1900<=first.year<=2100 or (day and (day.year,day.month)!=(first.year,first.month)):raise ValueError()
    except ValueError:raise ValueError('Choose a valid month and a day within that month.')
    following=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
    previous=(first-timedelta(days=1)).replace(day=1)
    start=datetime.combine(first,time.min);end=datetime.combine(following,time.min)
    people=db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    if educator_id and not any(p.id==educator_id for p in people):raise ValueError('Choose an active educator.')
    query=db.query(DemoBooking,Activity,Client,User).join(Activity,Activity.id==DemoBooking.activity_id).join(Client,Client.id==Activity.client_id).outerjoin(User,User.id==DemoBooking.assigned_educator_id).filter(DemoBooking.demo_date>=start,DemoBooking.demo_date<end,Activity.status!='CANCELLED')
    if educator_id:query=query.filter(DemoBooking.assigned_educator_id==educator_id)
    names={n.demo_id:n.name for n in db.query(DemoEducator).all()}
    events=defaultdict(list)
    for demo,activity,client,user in query.order_by(DemoBooking.demo_date,DemoBooking.id):
        if status and activity.status!=status:continue
        if q and q.casefold() not in (client.business_name+' '+(client.phone or '')).casefold():continue
        events[demo.demo_date.date()].append(dict(kind='BOOKED',time=demo.demo_date.strftime('%I:%M %p'),salon=client.business_name,treatment=demo.product_or_treatment or '',educator=names.get(demo.id,user.full_name if user else 'Unassigned'),url=f'/demos/{demo.id}',label=f'#{demo.id}',reason=''))
    # Request counts and details use the same ownership scope. Approved requests
    # are omitted because their corresponding booking is already counted above.
    if viewer_id is not None:
        requests=db.query(DemoBookingRequest,Client).join(Client,Client.id==DemoBookingRequest.client_id).filter(DemoBookingRequest.demo_date>=start,DemoBookingRequest.demo_date<end,DemoBookingRequest.status.in_(['PENDING','REJECTED']))
        if not can_review:requests=requests.filter(DemoBookingRequest.requested_by==viewer_id)
        if educator_id:requests=requests.filter(DemoBookingRequest.educator_id==educator_id)
        for item,client in requests.order_by(DemoBookingRequest.demo_date,DemoBookingRequest.id):
            if status and item.status!=status:continue
            if q and q.casefold() not in (client.business_name+' '+(client.phone or '')).casefold():continue
            events[item.demo_date.date()].append(dict(kind=item.status,time=item.demo_date.strftime('%I:%M %p'),salon=client.business_name,treatment=item.treatment,educator=item.educator_name,url=None,label=f'Request #{item.id}',reason=item.review_reason or ''))
    def link(target_month,selected_day=None):
        params={'month':target_month.strftime('%Y-%m'),'educator_id':educator_id}
        if selected_day:params['demo_day' if booking else 'day']=selected_day.isoformat()
        if booking and client_id:params['client_id']=client_id
        if q:params['q']=q
        if status:params['status']=status
        return ('/demos/new?' if booking else '/demos?')+escape(urlencode(params),quote=True)
    legend='<div class="demo-legend" aria-label="Demo status legend">'+''.join(f'<span>{value}</span>' for value in MARKERS.values())+'</div>'
    cells=''.join(f'<div class="weekday">{name}</div>' for name in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(first.year,first.month):
        for number in week:
            if not number:cells+='<div class="calendar-day empty" aria-hidden="true"></div>';continue
            current=first.replace(day=number);items=events[current];counts=Counter(item['kind'] for item in items)
            badges=''.join(f'<small class="demo-badge {kind.lower()}" aria-label="{MARKERS[kind]}: {counts[kind]}" title="{MARKERS[kind]}: {counts[kind]}">{MARKERS[kind].split()[0]} {counts[kind]}</small>' for kind in MARKERS if counts[kind])
            classes='calendar-day'+(' booked' if counts['BOOKED'] else '')+(' today' if current==today else '')+(' selected' if current==day else '')
            label=escape(current.strftime('%d %B %Y')+': '+', '.join(f'{MARKERS[kind]} {counts[kind]}' for kind in MARKERS))
            attrs=f'aria-label="{label}" data-date="{current}" data-demo-count="{counts["BOOKED"]}" data-pending-count="{counts["PENDING"]}" data-rejected-count="{counts["REJECTED"]}"'
            heading=f'<strong>{number}</strong>{badges}'
            if booking:
                if current<today:cells+=f'<span class="{classes} past" aria-disabled="true" {attrs}>{heading}</span>'
                else:cells+=f'<a class="{classes}" href="{link(first,current)}" {attrs}>{heading}</a>'
            else:
                details=''
                for item in items:
                    identity=f'<a href="{item["url"]}">{item["label"]}</a>' if item['url'] else escape(item['label'])
                    reason=f'<p>Rejection reason: {escape(item["reason"])}</p>' if item['kind']=='REJECTED' and item['reason'] else ''
                    details+=f'<article class="demo-event"><strong>{MARKERS[item["kind"]]}</strong> · {identity}<div>{escape(item["time"])} · {escape(item["salon"])}</div><div>{escape(item["treatment"])} · {escape(item["educator"])}</div>{reason}</article>'
                cells+=f'<details class="{classes}" {attrs} {"open" if current==day else ""}><summary>{heading}</summary><div class="demo-day-events" role="region" aria-label="Demo details"><button type="button" onclick="this.parentElement.parentElement.open=false">Close</button><h3>{current:%d %B %Y}</h3>{details or "No demos"}</div></details>'
    prev_link=f'<a href="{link(previous)}">← Previous</a>' if previous.year>=1900 else '<span></span>'
    next_link=f'<a href="{link(following)}">Next →</a>' if following.year<=2100 else '<span></span>'
    # Month navigation uses links, so the overview has no booking or filter form.
    styles='''<style>.demo-legend{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}.demo-legend span{padding:6px 9px;background:#f7f8fa;border-radius:7px}.demo-badge{display:block!important;white-space:normal;line-height:1.35}.demo-badge.booked{color:#17633c!important}.demo-badge.pending{color:#8c4c00!important}.demo-badge.rejected{color:#a62e26!important}.calendar-grid>details.calendar-day{display:block;grid-column:auto!important;min-width:0;margin:0;width:auto}.calendar-day summary{cursor:pointer;display:flex;flex-direction:column;gap:6px;list-style:none}.calendar-day summary::-webkit-details-marker{display:none}.demo-day-events{position:fixed;z-index:120;inset:18% 15% auto;max-height:65vh;overflow:auto;min-width:0;background:white;border:1px solid #d6dde5;border-radius:12px;padding:20px;box-shadow:0 8px 40px #0003}.demo-event{border-top:1px solid #ddd;padding:10px 0;font-size:12px;overflow-wrap:anywhere}.demo-event p{margin:5px 0}.calendar-day:has(.demo-badge.pending){border-color:#d49742}.calendar-day:has(.demo-badge.rejected){border-color:#d58b87}@media(max-width:600px){.demo-legend{gap:6px;font-size:12px}.demo-badge{font-size:9px!important}.demo-day-events{inset:15% 4% auto;max-height:75vh}}</style>'''
    title='<h2>1. Select demo date</h2>' if booking else ''
    chooser=''
    if booking:
        chooser=f'<p>Choose a date to enter demo details.</p><form class="calendar-toolbar" action="/demos/new"><label>Month <input type="month" name="month" value="{first:%Y-%m}" min="1900-01" max="2100-12"></label><input type="hidden" name="client_id" value="{client_id}"><input type="hidden" name="educator_id" value="{educator_id}"><button>Show Month</button></form>'
    return styles+title+chooser+f'<section class="calendar-panel" aria-label="Demo calendar">{legend}<div class="calendar-header">{prev_link}<h2>{first:%B %Y}</h2>{next_link}</div><div class="calendar-grid">{cells}</div></section>'
