"""ES1 CRM Phase 1 - safe SQLite upgrade.

Run once:
    C:\\ES1\\venv\\Scripts\\python.exe C:\\ES1\\upgrade_crm.py
"""
from sqlalchemy import inspect, text
from database.db import engine
from database.models import Base

Base.metadata.create_all(bind=engine)

wanted = {
    "business_name": "VARCHAR(200)",
    "contact_person": "VARCHAR(150)",
    "alternate_phone": "VARCHAR(20)",
    "area": "VARCHAR(120)",
    "city": "VARCHAR(120)",
    "address": "VARCHAR(500)",
    "pincode": "VARCHAR(12)",
    "client_category": "VARCHAR(10) DEFAULT 'B'",
    "client_type": "VARCHAR(30) DEFAULT 'SALON'",
    "status": "VARCHAR(30) DEFAULT 'LEAD'",
    "assigned_sales_id": "INTEGER",
    "latitude": "FLOAT",
    "longitude": "FLOAT",
    "updated_at": "DATETIME"
}

inspector = inspect(engine)
columns = {c["name"] for c in inspector.get_columns("clients")}

with engine.begin() as conn:
    for name, sql_type in wanted.items():
        if name not in columns:
            conn.execute(text(f"ALTER TABLE clients ADD COLUMN {name} {sql_type}"))
            print(f"Added clients.{name}")

    # Preserve any old client records by copying client_name into business_name.
    current = {c["name"] for c in inspect(engine).get_columns("clients")}
    if "client_name" in current and "business_name" in current:
        conn.execute(text(
            "UPDATE clients SET business_name = client_name "
            "WHERE (business_name IS NULL OR TRIM(business_name) = '') "
            "AND client_name IS NOT NULL"
        ))

print("ES1 CRM database upgrade complete.")
