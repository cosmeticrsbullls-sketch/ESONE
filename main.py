import os
from html import escape
from secrets import token_urlsafe
from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from database.db import SessionLocal
from database.models import User, Client
from modules.security import verify_password
from modules.users import create_user, get_all_users


app = FastAPI(title="ESONE")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or token_urlsafe(48),
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=os.getenv("RENDER", "").lower() == "true"
)


def login_page(error=""):
    error_html = ""

    if error:
        error_html = f'<div class="error">{escape(str(error))}</div>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>ESONE | Login</title>

        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                background: #101010;
                color: white;
                font-family: Arial, sans-serif;
            }}

            .login-box {{
                width: min(390px, 94vw);
                padding: 45px;
                background: #171717;
                border: 1px solid #333;
                border-radius: 18px;
            }}

            h1 {{
                margin: 0;
                text-align: center;
                font-size: 34px;
            }}

            .gold {{
                color: #d4af37;
            }}

            .subtitle {{
                text-align: center;
                color: #999;
                margin: 10px 0 35px;
            }}

            label {{
                display: block;
                margin: 18px 0 7px;
                color: #bbb;
            }}

            input {{
                width: 100%;
                padding: 13px;
                border-radius: 8px;
                border: 1px solid #444;
                background: #101010;
                color: white;
                font-size: 16px;
            }}

            button {{
                width: 100%;
                margin-top: 28px;
                padding: 14px;
                border: 0;
                border-radius: 8px;
                background: #d4af37;
                color: #111;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
            }}

            .error {{
                margin-bottom: 20px;
                padding: 10px;
                border-radius: 7px;
                background: #3a1717;
                color: #ffb4b4;
                text-align: center;
            }}
        </style>
    </head>

    <body>

        <div class="login-box">

            <h1>ES<span class="gold">ONE</span></h1>

            <div class="subtitle">
                ESONE Business Management System
            </div>

            {error_html}

            <form method="post" action="/login">

                <label>Email</label>
                <input
                    type="email"
                    name="email"
                    required
                    autocomplete="username"
                >

                <label>Password</label>
                <input
                    type="password"
                    name="password"
                    required
                    autocomplete="current-password"
                >

                <button type="submit">
                    LOGIN TO ESONE
                </button>

            </form>

        </div>

    </body>
    </html>
    """


@app.get("/login", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if request.session.get("user_id"):
        if request.session.get("role") == "SALES":
            return RedirectResponse("/mobile", status_code=303)

        return RedirectResponse("/command-center", status_code=303)

    return login_page()


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == email.strip().lower())
            .first()
        )

        if not user:
            return HTMLResponse(
                login_page("Invalid email or password."),
                status_code=401
            )

        if not user.is_active:
            return HTMLResponse(
                login_page("This ESONE account is inactive."),
                status_code=403
            )

        if not verify_password(password, user.password_hash):
            return HTMLResponse(
                login_page("Invalid email or password."),
                status_code=401
            )

        request.session.clear()

        request.session["user_id"] = user.id
        request.session["full_name"] = user.full_name
        request.session["role"] = user.role

        if user.role == "SALES":
            return RedirectResponse(
                "/mobile",
                status_code=303
            )

        return RedirectResponse(
            "/command-center",
            status_code=303
        )

    finally:
        db.close()


@app.get("/command-center", response_class=HTMLResponse)
def command_center(request: Request):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    name = escape(str(request.session.get("full_name") or ""))
    role = request.session.get("role")
    summary = ""
    if role in {"SUPER_ADMIN", "MANAGEMENT", "OFFICE"}:
        from modules.operations import queues
        from database.models import DemoBooking, Activity
        with SessionLocal() as db:
            courtesy_count = len(queues(db, "courtesy")[1])
            ptp_rows = queues(db, "ptp")[1]
            today_count = sum(row[6] == "TODAY" for row in ptp_rows)
            overdue_count = sum(row[6] == "OVERDUE" for row in ptp_rows)
            demo_count = db.query(DemoBooking).join(Activity, Activity.id == DemoBooking.activity_id).filter(Activity.status.in_(["BOOKED", "IN_PROGRESS"])).count()
        from modules.ui import icon
        metrics = [
            ("Courtesy calls due", courtesy_count, "/operations?kind=courtesy", "Salons ready for a follow-up"),
            ("PTP today", today_count, "/operations?kind=ptp", "Promises due today"),
            ("PTP overdue", overdue_count, "/operations?kind=ptp", "Promises needing attention"),
            ("Active demos", demo_count, "/demos", "Booked or in progress"),
        ]
        summary = '<section class="metrics" aria-label="Today’s work">' + ''.join(
            f'<a class="metric" href="{url}"><div class="metric-label">{label}: <strong>{count}</strong></div><div class="number" aria-hidden="true">{count}</div><div class="hint">{hint} →</div></a>' for label,count,url,hint in metrics) + '</section>'
    from modules.ui import icon
    from modules.operations import business_today
    cards = [("clients", "Clients & CRM", "Salon contacts, assignments and activity history.", "/clients"),
             ("visits", "Field Visits", "Manage field visits and verified check-ins.", "/visits"),
             ("calls", "Calls & Collections", "Record calls, promises and follow-up outcomes.", "/calls/new"),
             ("demos", "Demo Bookings", "Schedule treatments and track conversion outcomes.", "/demos"),
             ("reports", "Reports & Follow-ups", "Courtesy queues, PTPs and filtered Excel exports.", "/operations")]
    if role == "SUPER_ADMIN": cards.append(("clients", "Team & Access", "Manage employee accounts and roles.", "/users"))
    modules = ''.join(f'<a class="module-card" href="{url}"><div class="module-icon">{icon(key)}</div><h3>{title}</h3><p>{description}</p><span class="open">Open workspace →</span></a>' for key,title,description,url in cards)
    return f'''<!doctype html><html><head><title>ESONE Command Center</title></head><body><main class="dashboard"><section class="hero"><div><div class="eyebrow">Command Center · {business_today().strftime('%d %b %Y')}</div><h1>Welcome, {name}</h1><p>Your clients, follow-ups and team activity in one place.</p></div><div class="actions"><a class="primary" href="/calls/new">+ Record Call</a><a class="secondary" href="/demos/new">+ Book Demo</a></div></section>{summary}<div class="section-heading"><h2>Your workspaces</h2><span style="font-size:12px;color:#87929c">ESONE · Earthshine Professional</span></div><section class="module-grid">{modules}</section></main></body></html>'''


@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse("/", status_code=303)
@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") != "SUPER_ADMIN":
        return HTMLResponse("Access Denied", status_code=403)

    users = get_all_users()

    rows = ""

    for user in users:
        status = "Active" if user.is_active else "Inactive"

        rows += f"""
        <tr>
            <td>{escape(str(user.full_name))}</td>
            <td>{escape(str(user.email))}</td>
            <td>{escape(str(user.role))}</td>
            <td>{status}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>

        <title>ESONE | User Management</title>

        <style>

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                background: #101010;
                color: white;
                font-family: Arial, sans-serif;
            }}

            header {{
                padding: 22px 35px;
                border-bottom: 1px solid #333;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            .brand {{
                font-size: 24px;
                font-weight: bold;
            }}

            .gold {{
                color: #d4af37;
            }}

            .container {{
                padding: 40px;
                max-width: 1200px;
                margin: auto;
            }}

            .panel {{
                background: #181818;
                border: 1px solid #333;
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 30px;
            }}

            input, select {{
                width: 100%;
                padding: 12px;
                margin-top: 6px;
                margin-bottom: 15px;
                border-radius: 7px;
                border: 1px solid #444;
                background: #101010;
                color: white;
                font-size: 15px;
            }}

            button {{
                padding: 13px 22px;
                background: #d4af37;
                color: #111;
                border: none;
                border-radius: 7px;
                font-weight: bold;
                cursor: pointer;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}

            th, td {{
                padding: 14px;
                border-bottom: 1px solid #333;
                text-align: left;
            }}

            th {{
                color: #d4af37;
            }}

            a {{
                color: #d4af37;
                text-decoration: none;
            }}

        </style>

    </head>

    <body>

        <header>

            <div class="brand">
                ES<span class="gold">ONE</span>
            </div>

            <a href="/command-center">
                ← Command Center
            </a>

        </header>

        <div class="container">

            <h1>User Management</h1>

            <div class="panel">

                <h2>Create ESONE User</h2>

                <form method="post" action="/users/create">

                    <label>Employee Name</label>
                    <input
                        type="text"
                        name="full_name"
                        required
                    >

                    <label>Email</label>
                    <input
                        type="email"
                        name="email"
                        required
                    >

                    <label>Temporary Password</label>
                    <input
                        type="password"
                        name="password"
                        minlength="8"
                        required
                    >

                    <label>ESONE Role</label>

                    <select name="role" required>
                        <option value="SALES">Sales Employee</option>
                        <option value="OFFICE">Office / Telecaller</option>
                        <option value="MANAGEMENT">Management</option>
                    </select>

                    <button type="submit">
                        CREATE USER
                    </button>

                </form>

            </div>

            <div class="panel">

                <h2>ESONE Users</h2>

                <table>

                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Role</th>
                            <th>Status</th>
                        </tr>
                    </thead>

                    <tbody>
                        {rows}
                    </tbody>

                </table>

            </div>

        </div>

    </body>
    </html>
    """


@app.post("/users/create")
def create_es1_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...)
):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") != "SUPER_ADMIN":
        return HTMLResponse("Access Denied", status_code=403)

    success, message = create_user(
        full_name,
        email,
        password,
        role
    )

    if not success:
        return HTMLResponse(
            f"""
            <h2>{escape(str(message))}</h2>
            <a href="/users">Return to User Management</a>
            """,
            status_code=400
        )

    return RedirectResponse(
        "/users",
        status_code=303
    )

@app.get("/mobile", response_class=HTMLResponse)
def mobile_home(request: Request):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") != "SALES":
        return RedirectResponse("/command-center", status_code=303)

    name = escape(str(request.session.get("full_name") or ""))

    with SessionLocal() as db:
        visits_today = db.query(Visit).join(Activity,Activity.id==Visit.activity_id).filter(
            Activity.assigned_user_id==request.session.get("user_id"),
            Visit.check_in_at >= datetime.combine(datetime.now().date(), datetime.min.time())
        ).count()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>ESONE | Mobile</title>

        <style>

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                background: #101010;
                color: white;
                font-family: Arial, sans-serif;
            }}

            .mobile {{
                max-width: 500px;
                margin: auto;
                padding: 25px 20px;
            }}

            .brand {{
                text-align: center;
                font-size: 25px;
                font-weight: bold;
                margin-top: 10px;
            }}

            .gold {{
                color: #d4af37;
            }}

            .welcome {{
                margin-top: 35px;
                color: #999;
            }}

            .name {{
                margin-top: 5px;
                font-size: 26px;
                font-weight: bold;
            }}

            .checkin {{
                width: 100%;
                height: 130px;
                margin-top: 40px;
                border: none;
                border-radius: 18px;
                background: #d4af37;
                color: #111;
                font-size: 27px;
                font-weight: bold;
                cursor: pointer;
            }}

            .today {{
                margin-top: 35px;
                padding: 22px;
                background: #181818;
                border: 1px solid #333;
                border-radius: 15px;
            }}

            .stats {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin-top: 20px;
                text-align: center;
            }}

            .stat {{
                background: #111;
                border-radius: 10px;
                padding: 15px 5px;
            }}

            .number {{
                font-size: 22px;
                color: #d4af37;
                font-weight: bold;
            }}

            .label {{
                margin-top: 5px;
                font-size: 11px;
                color: #999;
            }}

            .logout {{
                display: block;
                margin-top: 40px;
                text-align: center;
                color: #888;
                text-decoration: none;
            }}

        </style>

    </head>

    <body>

        <div class="mobile">

            <div class="brand">
                ES<span class="gold">ONE</span>
            </div>

            <div class="welcome">
                Welcome
            </div>

            <div class="name">
                {name}
            </div>

            <button class="checkin" type="button" onclick="location.href='/visits'">📍 FIELD VISITS</button>

            <div class="today">

                <strong>Today's Activity</strong>

                <div class="stats">

                    <div class="stat">
                        <div class="number">{visits_today}</div>
                        <div class="label">VISITS</div>
                    </div>

                    <div class="stat">
                        <div class="number">—</div>
                        <div class="label">ORDERS (COMING SOON)</div>
                    </div>

                    <div class="stat">
                        <div class="number">—</div>
                        <div class="label">COLLECTION (COMING SOON)</div>
                    </div>

                </div>

            </div>

            <a class="logout" href="/logout">
                Logout
            </a>

        </div>

    </body>
    </html>
    """

@app.get("/clients", response_class=HTMLResponse)
def clients_page(request: Request, q: str = "", return_to: str = ""):
    from modules.workflows import hidden
    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") not in {"SUPER_ADMIN", "MANAGEMENT", "OFFICE"}:
        return HTMLResponse("Access Denied", status_code=403)

    db = SessionLocal()
    try:
        query = db.query(Client)
        search = q.strip()
        if search:
            like = f"%{search}%"
            query = query.filter(
                (Client.business_name.like(like)) |
                (Client.contact_person.like(like)) |
                (Client.phone.like(like)) |
                (Client.area.like(like)) |
                (Client.city.like(like))
            )
        clients = query.order_by(Client.id.desc()).all()
        sales_users = (
            db.query(User)
            .filter(User.role == "SALES", User.is_active == True)
            .order_by(User.full_name)
            .all()
        )

        sales_map = {u.id: u.full_name for u in sales_users}
        rows = ""
        for c in clients:
            assigned = sales_map.get(c.assigned_sales_id, "-")
            rows += f"""
            <tr>
                <td>{c.id}</td>
                <td><strong><a href="/clients/{c.id}/timeline">{escape(c.business_name)}</a></strong><br><small>{escape(str(c.contact_person or ""))}</small></td>
                <td>{escape(str(c.phone or ""))}<br><small>{escape(str(c.alternate_phone or ""))}</small></td>
                <td>{escape(str(c.area or ""))}<br><small>{escape(str(c.city or ""))}</small></td>
                <td>{escape(str(c.client_category or ""))}</td>
                <td>{escape(str(c.client_type or ""))}</td>
                <td>{escape(str(assigned))}</td>
                <td>{escape(str(c.status or ""))}</td>
            </tr>
            """

        sales_options = '<option value="">Unassigned</option>'
        for u in sales_users:
            sales_options += f'<option value="{u.id}">{escape(str(u.full_name))}</option>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>ESONE | CRM Client Master</title>
            <style>
                * {{ box-sizing:border-box; }}
                body {{ margin:0;background:#101010;color:white;font-family:Arial,sans-serif; }}
                header {{ padding:20px 32px;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center; }}
                .brand {{ font-size:24px;font-weight:bold; }}
                .gold, a {{ color:#d4af37; }}
                a {{ text-decoration:none; }}
                .container {{ max-width:1450px;margin:auto;padding:32px; }}
                .grid {{ display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 20px; }}
                .panel {{ background:#181818;border:1px solid #333;border-radius:15px;padding:25px;margin-bottom:25px; }}
                label {{ display:block;color:#bbb;margin-bottom:6px; }}
                input, select, textarea {{ width:100%;padding:11px;border:1px solid #444;border-radius:7px;background:#101010;color:white; }}
                textarea {{ min-height:80px;resize:vertical; }}
                button {{ padding:12px 20px;background:#d4af37;color:#111;border:0;border-radius:7px;font-weight:bold;cursor:pointer; }}
                .full {{ grid-column:1 / -1; }}
                .toolbar {{ display:flex;gap:10px;align-items:center; }}
                .toolbar input {{ max-width:420px; }}
                .table-wrap {{ overflow-x:auto; }}
                table {{ width:100%;border-collapse:collapse;min-width:1050px; }}
                th, td {{ padding:12px;border-bottom:1px solid #333;text-align:left;vertical-align:top; }}
                th {{ color:#d4af37; }}
                small {{ color:#999; }}
                @media (max-width:760px) {{
                    .grid {{ grid-template-columns:1fr; }}
                    .full {{ grid-column:auto; }}
                    .container {{ padding:18px; }}
                }}
            </style>
        </head>
        <body>
            <header>
                <div class="brand">ES<span class="gold">ONE</span> / CRM</div>
                <div><a href="/command-center">Command Center</a> &nbsp; | &nbsp; <a href="/logout">Logout</a></div>
            </header>

            <div class="container">
                <div class="panel" id="new-salon">
                    <h2>Register New Salon / Client</h2>
                    <form method="post" action="/clients/create">{hidden(request)}<input type="hidden" name="return_to" value="{escape(return_to if return_to in {'/demos/new','/calls/new'} else '',quote=True)}">
                        <div class="grid">
                            <div><label>Business / Salon Name *</label><input name="business_name" required></div>
                            <div><label>Owner / Contact Person</label><input name="contact_person"></div>
                            <div><label>Mobile</label><input name="phone"></div>
                            <div><label>Alternate Mobile</label><input name="alternate_phone"></div>
                            <div><label>Area</label><input name="area"></div>
                            <div><label>City</label><input name="city"></div>
                            <div><label>Pincode</label><input name="pincode"></div>
                            <div>
                                <label>Category</label>
                                <select name="client_category">
                                    <option value="A">A</option>
                                    <option value="B" selected>B</option>
                                    <option value="C">C</option>
                                </select>
                            </div>
                            <div>
                                <label>Client Type</label>
                                <select name="client_type">
                                    <option value="SALON" selected>Salon</option>
                                    <option value="DISTRIBUTOR">Distributor</option>
                                    <option value="ACADEMY">Academy</option>
                                    <option value="OTHER">Other</option>
                                </select>
                            </div>
                            <div>
                                <label>Status</label>
                                <select name="status">
                                    <option value="LEAD" selected>Lead</option>
                                    <option value="ACTIVE">Active</option>
                                    <option value="INACTIVE">Inactive</option>
                                </select>
                            </div>
                            <div>
                                <label>Assigned Sales Employee</label>
                                <select name="assigned_sales_id">{sales_options}</select>
                            </div>
                            <div class="full"><label>Address</label><textarea name="address"></textarea></div>
                            <div class="full"><button type="submit">SAVE CLIENT</button></div>
                        </div>
                    </form>
                </div>

                <div class="panel">
                    <div class="toolbar">
                        <form method="get" action="/clients" style="display:flex;gap:10px;width:100%;">
                            <input name="q" value="{escape(search, quote=True)}" placeholder="Search name, mobile, area or city">
                            <button type="submit">SEARCH</button>
                        </form>
                    </div>

                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th><th>Client / Contact</th><th>Mobile</th><th>Area / City</th>
                                    <th>Category</th><th>Type</th><th>Assigned Sales</th><th>Status</th>
                                </tr>
                            </thead>
                            <tbody>{rows}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    finally:
        db.close()


@app.post("/clients/create")
def create_client(
    request: Request,
    business_name: str = Form(...),
    contact_person: str = Form(""),
    phone: str = Form(""),
    alternate_phone: str = Form(""),
    area: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
    pincode: str = Form(""),
    client_category: str = Form("B"),
    client_type: str = Form("SALON"),
    status: str = Form("LEAD"),
    assigned_sales_id: str = Form(""),
    return_to: str = Form(""),
    csrf: str = Form("")
):
    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") not in {"SUPER_ADMIN", "MANAGEMENT", "OFFICE"}:
        return HTMLResponse("Access Denied", status_code=403)

    from modules.workflows import guard
    denied = guard(request, csrf)
    if denied is not None: return denied
    db = SessionLocal()
    try:
        if not business_name.strip(): return HTMLResponse("Salon name is required.",400)
        assigned_id = int(assigned_sales_id) if assigned_sales_id.strip().isdigit() else None
        client = Client(
            client_name=business_name.strip(),
            business_name=business_name.strip(),
            contact_person=contact_person.strip() or None,
            phone=phone.strip() or None,
            alternate_phone=alternate_phone.strip() or None,
            area=area.strip() or None,
            city=city.strip() or None,
            address=address.strip() or None,
            pincode=pincode.strip() or None,
            client_category=client_category.strip().upper() or "B",
            client_type=client_type.strip().upper() or "SALON",
            status=status.strip().upper() or "LEAD",
            assigned_sales_id=assigned_id,
            created_by=request.session.get("user_id")
        )
        db.add(client)
        db.commit()
        destination = f"{return_to}?client_id={client.id}" if return_to in {"/demos/new", "/calls/new"} else "/clients"
        return RedirectResponse(destination, status_code=303)
    finally:
        db.close()


# ==================== PHASE 1: FIELD VISITS ====================
from datetime import datetime, timedelta
import hashlib, math, secrets
from database.models import Activity, Visit, VerificationOTP, AuditLog, CommunicationLog

VISIT_RADIUS_METERS = 200

def _distance_m(lat1, lon1, lat2, lon2):
    r=6371000
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return r*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def _otp_hash(code):
    return hashlib.sha256(code.encode()).hexdigest()

def _visit_access(request):
    return request.session.get("role") in {"SUPER_ADMIN","MANAGEMENT","OFFICE","SALES"}

def _owns_visit(request, activity):
    return _visit_access(request) and (request.session.get("role") != "SALES" or activity.assigned_user_id == request.session.get("user_id"))


@app.get("/visits", response_class=HTMLResponse)
def visits_page(request: Request):
    if not request.session.get("user_id"): return RedirectResponse("/",303)
    if not _visit_access(request): return HTMLResponse("Access Denied",403)
    db=SessionLocal()
    try:
        q=db.query(Activity,Visit,Client).join(Visit,Visit.activity_id==Activity.id).join(Client,Client.id==Activity.client_id)
        if request.session.get("role")=="SALES": q=q.filter(Activity.assigned_user_id==request.session.get("user_id"))
        items=q.order_by(Activity.id.desc()).limit(100).all()
        rows="".join([f'<tr><td>{a.id}</td><td>{escape(str(c.business_name))}</td><td>{escape(str(v.visit_type))}</td><td>{escape(str(a.status))}</td><td>{"VERIFIED" if v.check_in_at else "PENDING"}</td><td><a href="/visits/{a.id}">OPEN</a></td></tr>' for a,v,c in items])
        clients=db.query(Client).order_by(Client.business_name).all()
        opts="".join([f'<option value="{c.id}">{escape(str(c.business_name))} — {escape(str(c.area or c.city or ""))}</option>' for c in clients])
        return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>ESONE Visits</title>
<style>body{{font-family:Arial;background:#f4f4f4;color:#222;margin:0}}header{{background:#fff;border-bottom:1px solid #ddd;padding:18px 24px;display:flex;justify-content:space-between}}main{{max-width:1100px;margin:auto;padding:24px}}.card{{background:white;border:1px solid #ddd;border-radius:14px;padding:20px;margin-bottom:20px}}select,button{{padding:12px;border:1px solid #bbb;border-radius:8px}}button{{background:#222;color:#fff;font-weight:bold}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;border-bottom:1px solid #eee;text-align:left}}a{{color:#222}}</style></head><body>
<header><strong>ESONE / FIELD VISITS</strong><a href="/mobile">Home</a></header><main>
<div class="card"><h2>New Field Visit</h2><form method="post" action="/visits/create"><select name="client_id" required><option value="">Select Salon</option>{opts}</select> <select name="visit_type"><option>SALES</option><option>COURTESY</option><option>COLLECTION</option></select> <button>CREATE VISIT</button></form><p>Visit start માટે GPS/location ફરજિયાત છે. Customer OTP માત્ર visit complete કરતી વખતે જરૂરી છે.</p></div>
<div class="card"><h2>Visits</h2><table><tr><th>ID</th><th>Salon</th><th>Type</th><th>Status</th><th>Location</th><th></th></tr>{rows}</table></div></main></body></html>'''
    finally: db.close()

@app.post("/visits/create")
def create_visit(request:Request, client_id:int=Form(...), visit_type:str=Form(...)):
    if not request.session.get("user_id"): return RedirectResponse("/",303)
    db=SessionLocal()
    try:
        if not _visit_access(request):return HTMLResponse("Access Denied",403)
        if visit_type.upper() not in {"SALES","COURTESY","COLLECTION"}:return HTMLResponse("Invalid visit type",400)
        if not db.get(Client,client_id):return HTMLResponse("Client not found",404)
        a=Activity(client_id=client_id,activity_type="FIELD_VISIT",source="FIELD",status="CREATED",title=f"{visit_type.upper()} Visit",assigned_user_id=request.session.get("user_id"),created_by=request.session.get("user_id"))
        db.add(a); db.flush(); v=Visit(activity_id=a.id,visit_type=visit_type.upper()); db.add(v); db.commit()
        return RedirectResponse(f"/visits/{a.id}",303)
    finally: db.close()

@app.get("/visits/{activity_id}", response_class=HTMLResponse)
def visit_detail(activity_id:int, request:Request):
    if not request.session.get("user_id"): return RedirectResponse("/",303)
    db=SessionLocal()
    try:
        row=db.query(Activity,Visit,Client).join(Visit,Visit.activity_id==Activity.id).join(Client,Client.id==Activity.client_id).filter(Activity.id==activity_id).first()
        if not row:return HTMLResponse("Visit not found",404)
        a,v,c=row
        if not _owns_visit(request,a):return HTMLResponse("Access Denied",403)
        gps_registered=c.latitude is not None and c.longitude is not None
        start_block='''<button onclick="startVisit()">VERIFY LOCATION & START VISIT</button><div id="geo"></div>''' if a.status=="CREATED" else ""
        end_block='''<form method="post" action="/visits/%s/request-end-otp"><label>Outcome / Notes</label><input name="notes" style="width:100%%;padding:12px;margin:8px 0" required><button>SEND END OTP</button></form>'''%activity_id if a.status=="IN_PROGRESS" else ""
        otp=db.query(VerificationOTP).filter(VerificationOTP.activity_id==activity_id,VerificationOTP.purpose=="VISIT_END",VerificationOTP.status=="PENDING").order_by(VerificationOTP.id.desc()).first()
        otp_block=''
        if otp:
            otp_block=f'''<form method="post" action="/visits/{activity_id}/verify-end-otp"><h3>Customer End OTP</h3><input name="otp" inputmode="numeric" maxlength="6" required><button>VERIFY & COMPLETE</button></form>'''
        register_note="Salon GPS not registered. Current verified location will be registered when visit starts." if not gps_registered else f"Registered GPS: {c.latitude:.5f}, {c.longitude:.5f} (allowed radius {VISIT_RADIUS_METERS}m)"
        return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Visit</title><style>body{{font-family:Arial;background:#f4f4f4;margin:0}}main{{max-width:650px;margin:auto;padding:22px}}.card{{background:#fff;padding:22px;border:1px solid #ddd;border-radius:14px}}button,input{{padding:13px;border-radius:8px;border:1px solid #bbb;margin:6px 0}}button{{background:#222;color:white;font-weight:bold}}.ok{{color:green}}</style></head><body><main><a href="/visits">← Visits</a><div class="card"><h2>{escape(str(v.visit_type))} VISIT</h2><h3>{escape(str(c.business_name))}</h3><p>Status: <b>{escape(str(a.status))}</b></p><p>Location: {register_note}</p>{start_block}{end_block}{otp_block}</div></main>
<script>function startVisit(){{if(!navigator.geolocation){{alert('GPS not supported');return}};document.getElementById('geo').innerText='Getting location...';navigator.geolocation.getCurrentPosition(async p=>{{let f=new FormData();f.append('latitude',p.coords.latitude);f.append('longitude',p.coords.longitude);let r=await fetch('/visits/{activity_id}/start',{{method:'POST',body:f}});let t=await r.text();if(r.ok)location.reload();else document.getElementById('geo').innerHTML=t;}},e=>{{document.getElementById('geo').innerText='Location permission/GPS required: '+e.message}},{{enableHighAccuracy:true,timeout:15000}})}};</script></body></html>'''
    finally: db.close()

@app.post("/visits/{activity_id}/start")
def start_visit(activity_id:int,request:Request,latitude:float=Form(...),longitude:float=Form(...)):
    if not request.session.get("user_id"): return HTMLResponse("Login required",401)
    db=SessionLocal()
    try:
        a=db.query(Activity).filter(Activity.id==activity_id).first(); v=db.query(Visit).filter(Visit.activity_id==activity_id).first()
        if not a or not v:return HTMLResponse("Visit not found",404)
        if not _owns_visit(request,a):return HTMLResponse("Access Denied",403)
        if a.status != "CREATED":return HTMLResponse("Visit has already started or completed",409)
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -90<=latitude<=90 and -180<=longitude<=180):return HTMLResponse("Invalid GPS coordinates",400)
        c=db.query(Client).filter(Client.id==a.client_id).first()
        if not c:return HTMLResponse("Client not found",404)
        if c.latitude is None or c.longitude is None:
            c.latitude,c.longitude=latitude,longitude; dist=0
        else:
            dist=_distance_m(latitude,longitude,c.latitude,c.longitude)
            if dist>VISIT_RADIUS_METERS:return HTMLResponse(f"Location mismatch: approx {dist:.0f}m from registered salon location. Visit cannot start.",409)
        v.check_in_latitude=latitude;v.check_in_longitude=longitude;v.check_in_at=datetime.now();a.status="IN_PROGRESS"
        db.add(AuditLog(user_id=request.session.get("user_id"),entity_type="VISIT",entity_id=v.id,action="START",new_value=f"distance_m={dist:.1f}"));db.commit();return HTMLResponse("OK")
    finally:db.close()

@app.post("/visits/{activity_id}/request-end-otp")
def request_visit_end_otp(activity_id:int,request:Request,notes:str=Form("")):
    if not request.session.get("user_id"):return RedirectResponse("/",303)
    db=SessionLocal()
    try:
        a=db.query(Activity).filter(Activity.id==activity_id).first();v=db.query(Visit).filter(Visit.activity_id==activity_id).first()
        if not a or not v:return HTMLResponse("Visit not found",404)
        if not _owns_visit(request,a):return HTMLResponse("Access Denied",403)
        c=db.get(Client,a.client_id)
        if not c:return HTMLResponse("Client not found",404)
        if os.getenv("ESONE_ENV") != "test":return HTMLResponse("Customer OTP delivery is not configured. Contact management; no OTP was sent.",503)
        if a.status!="IN_PROGRESS":return HTMLResponse("Visit is not in progress",409)
        code=f"{secrets.randbelow(900000)+100000}"
        otp=VerificationOTP(client_id=c.id,activity_id=a.id,purpose="VISIT_END",otp_hash=_otp_hash(code),recipient=c.whatsapp_phone or c.phone,status="PENDING",expires_at=datetime.now()+timedelta(minutes=10))
        db.query(VerificationOTP).filter(VerificationOTP.activity_id==a.id,VerificationOTP.purpose=="VISIT_END",VerificationOTP.status=="PENDING").update({"status":"SUPERSEDED"})
        a.notes=notes;db.add(otp)
        db.add(CommunicationLog(client_id=c.id,activity_id=a.id,channel="WHATSAPP",purpose="VISIT_END_OTP",recipient=c.whatsapp_phone or c.phone,message_text="Visit completion verification OTP",send_mode="AUTO",status="QUEUED",created_by=request.session.get("user_id")))
        db.commit()
        # Until Meta WhatsApp API credentials are connected, expose a local test OTP so the workflow can be tested end-to-end.
        return HTMLResponse(f'''<html><body style="font-family:Arial;padding:30px"><h2>OTP queued</h2><p>WhatsApp API is not connected yet.</p><p><b>TEST OTP: {code}</b> (valid 10 minutes)</p><a href="/visits/{activity_id}">Return to visit</a></body></html>''')
    finally:db.close()

@app.post("/visits/{activity_id}/verify-end-otp")
def verify_visit_end_otp(activity_id:int,request:Request,otp:str=Form(...)):
    if not request.session.get("user_id"):return RedirectResponse("/",303)
    db=SessionLocal()
    try:
        a=db.query(Activity).filter(Activity.id==activity_id).first();v=db.query(Visit).filter(Visit.activity_id==activity_id).first()
        if not a or not v:return HTMLResponse("Visit not found",404)
        if not _owns_visit(request,a):return HTMLResponse("Access Denied",403)
        if a.status!="IN_PROGRESS":return HTMLResponse("Visit is not in progress",409)
        rec=db.query(VerificationOTP).filter(VerificationOTP.activity_id==activity_id,VerificationOTP.purpose=="VISIT_END",VerificationOTP.status=="PENDING").order_by(VerificationOTP.id.desc()).first()
        if not rec or rec.expires_at<datetime.now():return HTMLResponse("OTP expired. Request a new OTP.",409)
        if rec.otp_hash!=_otp_hash(otp.strip()):return HTMLResponse("Invalid OTP",400)
        rec.status="VERIFIED";rec.verified_at=datetime.now();v.check_out_at=datetime.now();a.status="COMPLETED";a.completed_at=datetime.now()
        db.add(AuditLog(user_id=request.session.get("user_id"),entity_type="VISIT",entity_id=v.id,action="COMPLETE_OTP_VERIFIED",new_value="customer OTP verified"));db.commit();return RedirectResponse(f"/visits/{activity_id}",303)
    finally:db.close()


@app.get("/**", include_in_schema=False)
def copied_wildcard_url():
    """Recover the literal wildcard accidentally copied into the browser URL."""
    return RedirectResponse("/", status_code=303)


@app.get("/health", include_in_schema=False)
def health():
    # Liveness must never initialize, seed, or mutate the database.
    return {"status": "ok", "service": "ESONE"}


from modules.operations import router as operations_router
app.include_router(operations_router)

@app.middleware("http")
async def database_error_page(request: Request, call_next):
    try:
        return await call_next(request)
    except SQLAlchemyError:
        # Do not expose database URLs, SQL, parameters, or credentials.
        return HTMLResponse("<h1>ESONE temporarily unavailable</h1><p>The database needs an administrator check. No automatic database changes were made.</p><a href='/'>Return to login</a>",status_code=503)


@app.get("/health/ready", include_in_schema=False)
def database_readiness():
    from sqlalchemy import inspect
    from database.db import engine, Base
    try:
        inspector = inspect(engine)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                return HTMLResponse("Database setup needs administrator review",503)
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            if not {column.name for column in table.columns}.issubset(actual):
                return HTMLResponse("Database schema needs administrator review",503)
        return {"status":"ready","service":"ESONE"}
    except SQLAlchemyError:
        return HTMLResponse("Database connection needs administrator review",503)

from modules.workflows import router as workflow_router
app.include_router(workflow_router)


@app.get("/assets/esone.css", include_in_schema=False)
def esone_stylesheet():
    from fastapi.responses import Response
    from modules.ui import CSS
    return Response(CSS, media_type="text/css", headers={"Cache-Control": "public, max-age=3600"})


@app.middleware("http")
async def esone_presentation(request: Request, call_next):
    response = await call_next(request)
    if "text/html" not in response.headers.get("content-type", ""):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    from modules.ui import enhance
    session = request.scope.get("session", {})
    document = enhance(body.decode("utf-8"), request.url.path,
                       str(session.get("full_name") or ""), str(session.get("role") or ""),
                       bool(session.get("user_id")))
    from fastapi.responses import Response
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(document, status_code=response.status_code, headers=headers,
                    background=response.background)


@app.get("/assets/earthshine-logo.png", include_in_schema=False)
def earthshine_logo():
    from modules.ui import LOGO_PATH
    from fastapi.responses import FileResponse, Response
    if not LOGO_PATH.exists():
        return Response(status_code=404)
    return FileResponse(LOGO_PATH, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def app_manifest():
    from fastapi.responses import FileResponse
    from modules.ui import LOGO_PATH
    return FileResponse(LOGO_PATH.parent / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "public, max-age=300"})


@app.get("/assets/{icon_name}", include_in_schema=False)
def mobile_icon(icon_name: str):
    from fastapi.responses import FileResponse, Response
    from modules.ui import LOGO_PATH
    if icon_name not in {"icon-192.png", "icon-512.png", "apple-touch-icon.png"}:
        return Response(status_code=404)
    return FileResponse(LOGO_PATH.parent / icon_name, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
