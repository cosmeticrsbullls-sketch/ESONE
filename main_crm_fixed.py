from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from database.db import SessionLocal
from database.models import User, Client
from modules.security import verify_password
from modules.users import create_user, get_all_users


app = FastAPI(title="Earthshine One")

app.add_middleware(
    SessionMiddleware,
    secret_key="ES1-DEVELOPMENT-SECRET-CHANGE-LATER",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=False
)


def login_page(error=""):
    error_html = ""

    if error:
        error_html = f'<div class="error">{error}</div>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Earthshine One | Login</title>

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
                width: 390px;
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

            <h1>EARTHSHINE <span class="gold">ONE</span></h1>

            <div class="subtitle">
                ES1 Business Management System
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
                    LOGIN TO ES1
                </button>

            </form>

        </div>

    </body>
    </html>
    """


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
                login_page("This ES1 account is inactive."),
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

    name = request.session.get("full_name")
    role = request.session.get("role")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ES1 Command Center</title>

        <style>
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

            .content {{
                padding: 50px;
            }}

            .card {{
                max-width: 700px;
                padding: 30px;
                background: #181818;
                border: 1px solid #333;
                border-radius: 15px;
            }}

            .role {{
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
                EARTHSHINE <span class="gold">ONE</span>
            </div>

            <a href="/logout">Logout</a>

        </header>

        <div class="content">

            <div class="card">

                <h2>Welcome, {name}</h2>

                <p>
                    Role:
                    <span class="role">{role}</span>
                </p>

                <h3>ES1 COMMAND CENTER</h3>

                <p>
                    Authentication successful.
                </p>

                <p style="margin-top:25px;">
                    <a href="/clients" style="display:inline-block;padding:12px 18px;border:1px solid #d4af37;border-radius:8px;">
                        CRM / CLIENT MASTER
                    </a>
                </p>

            </div>

        </div>

    </body>
    </html>
    """


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
            <td>{user.full_name}</td>
            <td>{user.email}</td>
            <td>{user.role}</td>
            <td>{status}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>

        <title>ES1 | User Management</title>

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
                EARTHSHINE <span class="gold">ONE</span>
            </div>

            <a href="/command-center">
                ← Command Center
            </a>

        </header>

        <div class="container">

            <h1>User Management</h1>

            <div class="panel">

                <h2>Create ES1 User</h2>

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

                    <label>ES1 Role</label>

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

                <h2>ES1 Users</h2>

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
            <h2>{message}</h2>
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

    name = request.session.get("full_name")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Earthshine One | Mobile</title>

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
                EARTHSHINE <span class="gold">ONE</span>
            </div>

            <div class="welcome">
                Welcome
            </div>

            <div class="name">
                {name}
            </div>

            <button class="checkin" type="button">
                📍 CHECK-IN
            </button>

            <div class="today">

                <strong>Today's Activity</strong>

                <div class="stats">

                    <div class="stat">
                        <div class="number">0</div>
                        <div class="label">VISITS</div>
                    </div>

                    <div class="stat">
                        <div class="number">0</div>
                        <div class="label">ORDERS</div>
                    </div>

                    <div class="stat">
                        <div class="number">₹0</div>
                        <div class="label">COLLECTION</div>
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
def clients_page(request: Request, q: str = ""):
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
                <td><strong>{c.business_name}</strong><br><small>{c.contact_person or ""}</small></td>
                <td>{c.phone or ""}<br><small>{c.alternate_phone or ""}</small></td>
                <td>{c.area or ""}<br><small>{c.city or ""}</small></td>
                <td>{c.client_category or ""}</td>
                <td>{c.client_type or ""}</td>
                <td>{assigned}</td>
                <td>{c.status or ""}</td>
            </tr>
            """

        sales_options = '<option value="">Unassigned</option>'
        for u in sales_users:
            sales_options += f'<option value="{u.id}">{u.full_name}</option>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>ES1 | CRM Client Master</title>
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
                <div class="brand">EARTHSHINE <span class="gold">ONE</span> / CRM</div>
                <div><a href="/command-center">Command Center</a> &nbsp; | &nbsp; <a href="/logout">Logout</a></div>
            </header>

            <div class="container">
                <div class="panel">
                    <h2>Add Client / Venue</h2>
                    <form method="post" action="/clients/create">
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
                            <input name="q" value="{search}" placeholder="Search name, mobile, area or city">
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
    assigned_sales_id: str = Form("")
):
    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    if request.session.get("role") not in {"SUPER_ADMIN", "MANAGEMENT", "OFFICE"}:
        return HTMLResponse("Access Denied", status_code=403)

    db = SessionLocal()
    try:
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
        return RedirectResponse("/clients", status_code=303)
    finally:
        db.close()

