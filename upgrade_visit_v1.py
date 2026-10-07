from sqlalchemy import text
from database.db import engine, Base
import database.models  # noqa

Base.metadata.create_all(bind=engine)

columns = [
    ("visits", "location_status", "VARCHAR(30) DEFAULT 'PENDING'"),
    ("visits", "location_distance_m", "FLOAT"),
    ("visits", "end_otp_status", "VARCHAR(30) DEFAULT 'NOT_SENT'"),
    ("visits", "end_otp_verified_at", "DATETIME"),
    ("visits", "end_notes", "TEXT"),
]
with engine.begin() as conn:
    for table, col, ddl in columns:
        existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
        if col not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            print(f"Added {table}.{col}")
print("Visit v1 upgrade complete.")
