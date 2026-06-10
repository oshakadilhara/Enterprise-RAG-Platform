"""Seed demo users for local / Docker testing.

Run inside the backend container:
    python scripts/seed_test_users.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import Role, hash_password
from app.models.organization import Organization
from app.models.user import User

# email, password, full_name, role, organization_name (None = no org)
TEST_USERS = [
    ("admin@acme.com", "AcmeAdmin123!", "Alice Admin", Role.ORG_ADMIN, "Acme Corp"),
    ("manager@acme.com", "AcmeMgr123!", "Bob Manager", Role.MANAGER, "Acme Corp"),
    ("employee@acme.com", "AcmeEmp123!", "Carol Employee", Role.EMPLOYEE, "Acme Corp"),
    ("admin@beta.com", "BetaAdmin123!", "Dan Beta Admin", Role.ORG_ADMIN, "Beta Inc"),
    ("super@platform.com", "SuperAdmin123!", "Eve Super Admin", Role.SUPER_ADMIN, None),
]


async def seed() -> None:
    org_cache: dict[str, Organization] = {}

    async with async_session_factory() as session:
        for email, password, full_name, role, org_name in TEST_USERS:
            existing = await session.execute(select(User).where(User.email == email))
            if existing.scalar_one_or_none():
                print(f"  skip  {email} (already exists)")
                continue

            org_id = None
            if org_name:
                if org_name not in org_cache:
                    result = await session.execute(
                        select(Organization).where(Organization.name == org_name)
                    )
                    org = result.scalar_one_or_none()
                    if not org:
                        org = Organization(
                            id=uuid4(),
                            name=org_name,
                            slug=org_name.lower().replace(" ", "-")[:100],
                        )
                        session.add(org)
                        await session.flush()
                        print(f"  org   {org_name} ({org.id})")
                    org_cache[org_name] = org
                org_id = org_cache[org_name].id

            user = User(
                id=uuid4(),
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=role.value,
                organization_id=org_id,
            )
            session.add(user)
            print(f"  user  {email} [{role.value}]")

        await session.commit()

    print("\n[OK] Seed complete. Credentials:\n")
    print(f"{'Email':<28} {'Password':<18} {'Role':<14} Organization")
    print("-" * 80)
    for email, password, full_name, role, org_name in TEST_USERS:
        print(f"{email:<28} {password:<18} {role.value:<14} {org_name or '-'}")


if __name__ == "__main__":
    asyncio.run(seed())
