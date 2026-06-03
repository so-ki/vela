"""Seed demo business and legal users for local development."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, init_db
from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL
from app.core.security import get_password_hash
from app.models.user import User

DEMO_USERS = [
    {
        "email": "legal@demo.vela",
        "full_name": "演示法务",
        "organization": "Demo Corp · 法务部",
        "password": "Demo1234!",
        "role": ROLE_LEGAL,
    },
    {
        "email": "biz@demo.vela",
        "full_name": "演示业务",
        "organization": "Demo Corp · 投资部",
        "password": "Demo1234!",
        "role": ROLE_BUSINESS,
    },
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        for spec in DEMO_USERS:
            existing = db.query(User).filter(User.email == spec["email"]).first()
            if existing:
                if existing.role != spec["role"]:
                    existing.role = spec["role"]
                    existing.full_name = spec["full_name"]
                    existing.organization = spec["organization"]
                    db.commit()
                    print(f"Updated demo user role: {spec['email']} → {spec['role']}")
                else:
                    print(f"Demo user already exists: {spec['email']}")
                continue

            user = User(
                email=spec["email"],
                full_name=spec["full_name"],
                organization=spec["organization"],
                hashed_password=get_password_hash(spec["password"]),
                role=spec["role"],
                disclaimer_accepted=True,
            )
            db.add(user)
            db.commit()
            print(f"Created demo user: {spec['email']} / {spec['password']} ({spec['role']})")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
