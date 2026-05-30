"""Seed a demo legal user for local development."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, init_db
from app.core.security import get_password_hash
from app.models.user import User


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        email = "legal@demo.vela"
        if db.query(User).filter(User.email == email).first():
            print(f"Demo user already exists: {email}")
            return

        user = User(
            email=email,
            full_name="演示法务",
            organization="Demo Corp",
            hashed_password=get_password_hash("Demo1234!"),
            role="legal",
            disclaimer_accepted=True,
        )
        db.add(user)
        db.commit()
        print(f"Created demo user: {email} / Demo1234!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
