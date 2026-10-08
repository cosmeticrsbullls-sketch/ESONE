"""Operational reports derived from existing ESONE records."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from openpyxl import Workbook
from sqlalchemy import func

from database.db import SessionLocal
from database.models import Activity, Client, CollectionActivity, PromiseToPay, Visit, DemoBooking

router = APIRouter()
MANAGEMENT_ROLES = {"SUPER_ADMIN", "MANAGEMENT", "OFFICE"}


def access(request):
    if not request.session.get("user_id"):
        return RedirectResponse("/", 303)
    if request.session.get("role") not in MANAGEMENT_ROLES:
        return HTMLResponse("Access Denied", 403)


def business_today():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def filters(start, end):
    if start and end and start > end:
        raise ValueError("Start date must be on or before end date.")
    return (datetime.combine(start, time.min) if start else None,
            datetime.combine(end + timedelta(days=1), time.min) if end else None)


def queues(db, kind, q="", start=None, end=None):
    lower, upper = filters(start, end)
    if kind == "courtesy":
        # One task per salon, based on the latest completed employee visit.
        latest = db.query(Activity.client_id.label("client_id"),
                          func.max(Activity.completed_at).label("visited_at")).filter(
            Activity.activity_type == "FIELD_VISIT", Activity.status == "COMPLETED",
            Activity.completed_at.isnot(None)).group_by(Activity.client_id).subquery()
        records = db.query(Client, latest.c.visited_at).join(latest, Client.id == latest.c.client_id).all()
        headers = ["Client ID", "Salon", "Phone", "Area", "Last Visit", "Courtesy Due", "Days Overdue"]
        today = business_today()
        rows = []
        for c, visited in records:
            latest_visit = db.query(Activity).filter_by(client_id=c.id, activity_type="FIELD_VISIT", status="COMPLETED").filter(Activity.completed_at==visited).order_by(Activity.id.desc()).first()
            if db.query(Activity).filter_by(parent_activity_id=latest_visit.id, activity_type="COURTESY_CALL", status="COMPLETED").first():
                continue
            due = visited.date() + timedelta(days=7)
            if due > today or (start and due < start) or (end and due > end):
                continue
            if q and q.lower() not in " ".join(str(v or "") for v in [c.business_name,c.phone,c.area,c.city]).lower():
                continue
            rows.append([c.id,c.business_name,c.phone or "",c.area or c.city or "",visited,due,(today-due).days])
        return headers, sorted(rows, key=lambda r: (r[5],r[0]))
    if kind == "ptp":
        query = db.query(PromiseToPay,Client,Activity).join(Client,Client.id==PromiseToPay.client_id).join(
            CollectionActivity,CollectionActivity.id==PromiseToPay.collection_activity_id).join(
            Activity,Activity.id==CollectionActivity.activity_id).filter(PromiseToPay.status=="OPEN")
        if lower: query=query.filter(PromiseToPay.promise_date>=lower)
        if upper: query=query.filter(PromiseToPay.promise_date<upper)
        if not start and not end:
            query=query.filter(PromiseToPay.promise_date<datetime.combine(business_today()+timedelta(days=1),time.min))
        if q:
            like=f"%{q.strip()}%"
            query=query.filter((Client.business_name.ilike(like)) | (Client.phone.ilike(like)))
        headers=["PTP ID","Client ID","Salon","Phone","Promised Amount","Promise Date","Due Status","Call Date","Notes"]
        return headers, [[p.id,c.id,c.business_name,c.phone or "",p.promised_amount,p.promise_date,
            "OVERDUE" if p.promise_date.date()<business_today() else "TODAY" if p.promise_date.date()==business_today() else "UPCOMING",
            a.created_at,p.notes or ""] for p,c,a in query.order_by(PromiseToPay.promise_date,PromiseToPay.id).all()]
    if kind == "visits":
        query=db.query(Activity,Visit,Client).join(Visit,Visit.activity_id==Activity.id).join(Client,Client.id==Activity.client_id)
        if lower: query=query.filter(Activity.created_at>=lower)
        if upper: query=query.filter(Activity.created_at<upper)
        if q:
            like=f"%{q.strip()}%"
            query=query.filter((Client.business_name.ilike(like)) | (Client.phone.ilike(like)))
        headers=["Activity ID","Client ID","Salon","Visit Type","Status","Employee ID","Created","Check In","Check Out","Notes"]
        return headers,[[a.id,c.id,c.business_name,v.visit_type,a.status,a.assigned_user_id,a.created_at,v.check_in_at,v.check_out_at,a.notes or ""] for a,v,c in query.order_by(Activity.id.desc()).all()]
    if kind in {"calls", "demos"}:
        query = db.query(Activity, Client).join(Client, Client.id==Activity.client_id)
        query = query.filter(Activity.activity_type.in_(["COLLECTION", "COURTESY_CALL"]) if kind=="calls" else Activity.activity_type=="DEMO")
        if lower: query=query.filter(Activity.created_at>=lower)
        if upper: query=query.filter(Activity.created_at<upper)
        if q: query=query.filter((Client.business_name.ilike(f"%{q}%")) | (Client.phone.ilike(f"%{q}%")))
        if kind=="calls":
            headers=["Activity ID","Client ID","Salon","Call Type","Outcome","Status","Call Date (UTC)","Notes"]
            rows=[[a.id,c.id,c.business_name,a.activity_type,a.title,a.status,a.created_at,a.notes or ""] for a,c in query.order_by(Activity.id.desc()).all()]
        else:
            headers=["Demo ID","Client ID","Salon","Treatment","Demo Date (India)","Educator ID","Status","Result","Follow-up","Notes"]
            rows=[]
            for a,c in query.order_by(Activity.id.desc()).all():
                d=db.query(DemoBooking).filter_by(activity_id=a.id).first()
                if d: rows.append([d.id,c.id,c.business_name,d.product_or_treatment,d.demo_date,d.assigned_educator_id,a.status,d.conversion_status,d.followup_at,a.notes or ""])
        return headers,rows
    raise ValueError("Unknown report.")


def xlsx(headers, rows, kind):
    book=Workbook(); sheet=book.active; sheet.title="ESONE Report"; sheet.append(headers)
    for row in rows:
        safe=[]
        for value in row:
            if isinstance(value,Decimal): value=float(value)
            safe.append(value)
        sheet.append(safe)
        # User text beginning with '=' must stay text, never executable Excel formulas.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value,str): cell.data_type="s"
    sheet.freeze_panes="A2"; sheet.auto_filter.ref=sheet.dimensions
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width=min(45,max(14,max(len(str(c.value or "")) for c in column)+2))
    output=BytesIO(); book.save(output)
    return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":f'attachment; filename="ESONE_{kind}.xlsx"'})


@router.get("/operations", response_class=HTMLResponse)
def operations(request: Request, kind: str="courtesy", q: str="", start: date|None=None, end: date|None=None):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        try: headers,rows=queues(db,kind,q,start,end)
        except ValueError as error:return HTMLResponse(escape(str(error)),400)
    from urllib.parse import urlencode
    params=urlencode({k:v for k,v in {"kind":kind,"q":q,"start":start,"end":end}.items() if v is not None})
    actions = ""
    if kind in {"courtesy", "ptp", "demos"}:
        for row in rows:
            url = f"/calls/new?client_id={row[0]}&kind=COURTESY_CALL" if kind=="courtesy" else f"/ptps/{row[0]}" if kind=="ptp" else f"/demos/{row[0]}"
            actions += f'<p><a href="{escape(url,quote=True)}">{escape(str(row[2] if kind!="courtesy" else row[1]))} — {"Record Courtesy Call" if kind=="courtesy" else "Follow Up" if kind=="ptp" else "Demo Details"}</a></p>'
    headings="".join(f"<th>{escape(h)}</th>" for h in headers)
    body="".join("<tr>"+"".join(f"<td>{escape(str(v if v is not None else ''))}</td>" for v in row)+"</tr>" for row in rows)
    if not body:body=f'<tr><td colspan="{len(headers)}">No matching records.</td></tr>'
    opts="".join(f'<option value="{key}" {"selected" if key==kind else ""}>{label}</option>' for key,label in [("courtesy","7-Day Courtesy Calls"),("ptp","PTP Due Today / Overdue"),("visits","Visit History"),("calls","Call History"),("demos","Demo History")])
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>ESONE Operations</title><style>body{{font-family:Arial;margin:24px;background:#f5f5f5;color:#222}}main{{background:white;padding:24px;border-radius:12px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}.table{{overflow:auto}}input,select,button{{padding:10px;margin:5px}}a{{color:#222}}</style></head><body><main><a href="/command-center">← Command Center</a><h1>ESONE Operations</h1><p><a href="/calls/new">Record Call</a> · <a href="/demos">Demo Bookings</a></p><p>Business date: {business_today()} (India). {len(rows)} matching records.</p><form><select name="kind">{opts}</select><input name="q" aria-label="Search salon or phone" value="{escape(q,quote=True)}" placeholder="Salon / phone"><label>From <input type="date" name="start" value="{start or ''}"></label><label>To <input type="date" name="end" value="{end or ''}"></label><button>Apply</button></form><a href="/reports/export?{escape(params,quote=True)}">Download filtered Excel</a><p>Courtesy calls become due 7 days after the latest completed visit. CONTACTED courtesy outcomes clear the reminder for that visit.</p>{actions}<div class="table"><table><tr>{headings}</tr>{body}</table></div></main><script>document.querySelector('form').addEventListener('submit',()=>{{document.querySelectorAll('input[type=date]').forEach(x=>{{if(!x.value)x.disabled=true}})}})</script></body></html>'''


@router.get("/reports/export")
def export_report(request: Request, kind: str="courtesy", q: str="", start: date|None=None, end: date|None=None):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        try:headers,rows=queues(db,kind,q,start,end)
        except ValueError as error:return HTMLResponse(escape(str(error)),400)
    return xlsx(headers,rows,kind)


@router.get("/clients/{client_id}/timeline", response_class=HTMLResponse)
def timeline(client_id:int,request:Request):
    denied=access(request)
    if denied is not None:return denied
    with SessionLocal() as db:
        client=db.get(Client,client_id)
        if not client:return HTMLResponse("Client not found",404)
        records=db.query(Activity).filter(Activity.client_id==client_id).order_by(Activity.created_at.desc(),Activity.id.desc()).all()
        items="".join(f'<li><strong>{escape(a.activity_type)} — {escape(a.status or "")}</strong> · {a.created_at}<p>{escape(a.title or "")} {escape(a.notes or "")}</p></li>' for a in records)
        return f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>ESONE Timeline</title></head><body style="font-family:Arial;padding:24px"><a href="/clients">← Clients</a><h1>{escape(client.business_name)} — Activity Timeline</h1><ol>{items or "<li>No recorded activities.</li>"}</ol></body></html>'
