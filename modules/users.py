from database.db import SessionLocal
from database.models import User
from modules.security import hash_password


VALID_ROLES = {
    "SUPER_ADMIN",
    "MANAGEMENT",
    "OFFICE",
    "SALES"
}


def create_user(full_name, email, password, role):

    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip().upper()

    if not full_name:
        return False, "Full name is required."

    if not email:
        return False, "Email is required."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    if len(password.encode("utf-8")) > 72:
        return False, "Password must be at most 72 UTF-8 bytes."

    if role not in VALID_ROLES:
        return False, "Invalid ESONE role."

    db = SessionLocal()

    try:

        existing = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing:
            return False, "Email already registered."

        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True
        )

        db.add(user)
        db.commit()

        return True, "ESONE user created successfully."

    finally:
        db.close()


def get_all_users():

    db = SessionLocal()

    try:
        return (
            db.query(User)
            .order_by(User.full_name)
            .all()
        )

    finally:
        db.close()