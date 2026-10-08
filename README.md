# ESONE

Earthshine Professional business operations app, built with FastAPI and SQLAlchemy.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

For Render, retain the existing service and use `uvicorn main:app --host 0.0.0.0 --port $PORT`. Liveness path: `/health`. Database readiness: `/health/ready` (read-only).

Configuration: `DATABASE_URL` (existing database), `SESSION_SECRET` (stable private random secret), and `RENDER=true` for secure cookies. Without SESSION_SECRET, sessions use a process-random key and expire on restart; multiple workers require a shared private key. Do not put credentials in Git.

Application startup does **not** create or migrate tables, seed data or create administrators. Existing `init_db.py`, `create_admin.py` and upgrade scripts must not be run against production without explicit approval. Render SQLite storage may be ephemeral; confirm the existing PostgreSQL connection before accepting real data.

Visit completion requires real customer OTP delivery, which is not integrated yet. Production fails explicitly instead of showing a fake customer verification code. `ESONE_ENV=test` enables test-only OTP display and must never be configured on production.

## Test

```bash
pip install httpx==0.28.1
python -m unittest discover -s tests -v
```

Tests use synthetic in-memory data, never the configured production database. Scope, findings and rollout blockers: [development audit](docs/DEVELOPMENT_AUDIT.md).
