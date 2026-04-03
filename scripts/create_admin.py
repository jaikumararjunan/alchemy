"""
Create or reset the Alchemy super admin account.

Run from the project root:
    python scripts/create_admin.py

Or from anywhere:
    python path/to/alchemy/scripts/create_admin.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure data directory exists
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Force local SQLite path — ignore any Docker path from .env.local
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DATA_DIR / 'alchemy.db'}"

# Load remaining env vars from .env.local (skip DATABASE_URL — already set)
env_file = PROJECT_ROOT / ".env.local"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            if k != "DATABASE_URL":   # Already forced above
                os.environ.setdefault(k, v.strip())

# Final defaults
os.environ.setdefault("JWT_SECRET_KEY",    "AlchemyLocalDev!JWT_Secret_Key_32chars_Min_2024")
os.environ.setdefault("ALCHEMY_VAULT_KEY", "AlchemyLocalDev!Vault_Key_32chars_Min2024")
os.environ.setdefault("ADMIN_EMAIL",       "admin@alchemy.in")
os.environ.setdefault("ADMIN_PASSWORD",    "Alchemy#Admin!2024")

ADMIN_EMAIL    = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
DB_URL         = os.environ["DATABASE_URL"]


async def main():
    print(f"\n  Creating admin : {ADMIN_EMAIL}")
    print(f"  Database       : {DB_URL}\n")

    from alchemy.api.database import create_tables, get_session_factory
    from alchemy.auth.service import AuthService
    from alchemy.auth.security import hash_password
    from alchemy.users.models import User, UserStatus
    from sqlalchemy import select

    await create_tables()
    print("  Tables ready")

    svc     = AuthService()
    factory = get_session_factory()

    async with factory() as db:
        result   = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            existing.password_hash  = hash_password(ADMIN_PASSWORD)
            existing.status         = UserStatus.ACTIVE.value
            existing.email_verified = True
            existing.role           = "super_admin"
            await db.commit()
            print("  Admin updated (password reset)")
        else:
            user = await svc.signup(db,
                email=ADMIN_EMAIL,
                username="superadmin",
                full_name="Super Admin",
                password=ADMIN_PASSWORD,
                role="super_admin",
            )
            user.status         = UserStatus.ACTIVE.value
            user.email_verified = True
            await db.commit()
            print("  Admin created")

    async with factory() as db:
        result = await svc.login(db,
            email=ADMIN_EMAIL, password=ADMIN_PASSWORD,
            ip_address="127.0.0.1", user_agent="create_admin_script")
        await db.commit()
        print(f"  Login verified (role: {result['user']['role']})")

    print()
    print("  " + "=" * 43)
    print("   Admin account ready!")
    print(f"   Email   : {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print("   Login   : http://localhost:3000/auth/login")
    print("  " + "=" * 43)
    print()


if __name__ == "__main__":
    asyncio.run(main())
