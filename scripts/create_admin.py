"""
Run this once to create the super admin account.
Usage: python scripts/create_admin.py
"""
import asyncio, os, sys
from pathlib import Path

# Load .env.local if it exists
env_file = Path(".env.local")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Fallback defaults
os.environ.setdefault("JWT_SECRET_KEY",    "AlchemyLocalDev!JWT_Secret_Key_32chars_Min_2024")
os.environ.setdefault("ALCHEMY_VAULT_KEY", "AlchemyLocalDev!Vault_Key_32chars_Min2024")
os.environ.setdefault("DATABASE_URL",      "sqlite+aiosqlite:///./data/alchemy.db")

# Make sure data/ exists
Path("data").mkdir(exist_ok=True)

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL",    "admin@alchemy.in")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Alchemy#Admin!2024")

async def main():
    print(f"Creating admin: {ADMIN_EMAIL}")

    from alchemy.api.database import create_tables, get_session_factory
    await create_tables()
    print("  ✓ Tables ready")

    from alchemy.auth.service import AuthService
    from alchemy.users.models import UserStatus
    from sqlalchemy import select
    from alchemy.users.models import User

    svc     = AuthService()
    factory = get_session_factory()

    async with factory() as db:
        # Check if already exists
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            # Update password and ensure active
            from alchemy.auth.security import hash_password
            existing.password_hash = hash_password(ADMIN_PASSWORD)
            existing.status        = UserStatus.ACTIVE.value
            existing.email_verified = True
            existing.role          = "super_admin"
            await db.commit()
            print(f"  ✓ Admin updated (password reset)")
        else:
            user = await svc.signup(db,
                email=ADMIN_EMAIL, username="superadmin",
                full_name="Super Admin", password=ADMIN_PASSWORD,
                role="super_admin")
            user.status         = UserStatus.ACTIVE.value
            user.email_verified = True
            await db.commit()
            print(f"  ✓ Admin created")

    # Verify login works
    async with factory() as db:
        result = await svc.login(db,
            email=ADMIN_EMAIL, password=ADMIN_PASSWORD,
            ip_address="127.0.0.1", user_agent="seed-script")
        await db.commit()
        print(f"  ✓ Login verified — role: {result['user']['role']}")

    print()
    print("=" * 45)
    print("  Admin account ready!")
    print(f"  Email   : {ADMIN_EMAIL}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print("  URL     : http://localhost:3000/auth/login")
    print("=" * 45)

asyncio.run(main())
