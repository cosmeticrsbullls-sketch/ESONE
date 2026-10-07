from getpass import getpass

from database.db import SessionLocal
from database.models import User
from modules.security import hash_password


db = SessionLocal()

try:
    existing_admin = (
        db.query(User)
        .filter(User.role == "SUPER_ADMIN")
        .first()
    )

    if existing_admin:
        print("A SUPER ADMIN ALREADY EXISTS.")
    else:
        print("\n=== ES1 SUPER ADMIN SETUP ===\n")

        full_name = input("Full Name: ").strip()
        email = input("Email: ").strip().lower()

        password = getpass("Password: ")
        confirm_password = getpass("Confirm Password: ")

        if not full_name or not email or not password:
            print("ERROR: All fields are required.")

        elif password != confirm_password:
            print("ERROR: Passwords do not match.")

        elif len(password) < 8:
            print("ERROR: Password must contain at least 8 characters.")

        else:
            existing_email = (
                db.query(User)
                .filter(User.email == email)
                .first()
            )

            if existing_email:
                print("ERROR: This email is already registered.")

            else:
                admin = User(
                    full_name=full_name,
                    email=email,
                    password_hash=hash_password(password),
                    role="SUPER_ADMIN",
                    is_active=True
                )

                db.add(admin)
                db.commit()

                print("\nES1 SUPER ADMIN CREATED SUCCESSFULLY.")

finally:
    db.close()