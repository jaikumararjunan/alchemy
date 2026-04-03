import asyncio, os, subprocess, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(DATA_DIR / "alchemy.db").replace("\\", "/")

env_file = PROJECT_ROOT / ".env.local"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() != "DATABASE_URL":
                os.environ.setdefault(k.strip(), v.strip())

os.environ.setdefault("JWT_SECRET_KEY",    "AlchemyLocalDev!JWT_Secret_Key_32chars_Min_2024")
os.environ.setdefault("ALCHEMY_VAULT_KEY", "AlchemyLocalDev!Vault_Key_32chars_Min2024")
os.environ.setdefault("ADMIN_EMAIL",       "admin@alchemy.in")
os.environ.setdefault("ADMIN_PASSWORD",    "Alchemy#Admin!2024")

ADMIN_EMAIL    = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

# Install every package the app needs — all have Python 3.12 wheels on Windows
PACKAGES = [
    "fastapi==0.115.0",
    "uvicorn[standard]==0.29.0",
    "python-multipart==0.0.9",
    "httpx==0.27.0",
    "sqlalchemy[asyncio]==2.0.30",
    "aiosqlite==0.20.0",
    "bcrypt==4.1.3",
    "PyJWT==2.8.0",
    "pyotp==2.9.0",
    "qrcode[pil]==7.4.0",
    "cryptography==42.0.5",
    "pydantic[email]==2.7.1",
    "pydantic-settings==2.2.1",
    "structlog==24.1.0",
    "langchain-core==0.2.7",
    "pillow>=10.0.0",
]

def install_packages():
    print("  Installing required packages...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-warn-script-location"] + PACKAGES,
        capture_output=False
    )
    if result.returncode != 0:
        print("  Some packages failed — continuing anyway")

install_packages()

async def main():
    print(f"\n  Admin  : {ADMIN_EMAIL}")
    print(f"  DB     : {os.environ['DATABASE_URL']}\n")

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
            print("  Admin updated")
        else:
            user = await svc.signup(db, email=ADMIN_EMAIL, username="superadmin",
                full_name="Super Admin", password=ADMIN_PASSWORD, role="super_admin")
            user.status = UserStatus.ACTIVE.value
            user.email_verified = True
            await db.commit()
            print("  Admin created")

    async with factory() as db:
        r = await svc.login(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD,
            ip_address="127.0.0.1", user_agent="setup")
        await db.commit()
        print(f"  Login OK  (role: {r['user']['role']})")

    print()
    print("  =========================================")
    print("   READY!")
    print(f"   Email   : {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print()
    print("   Start API:")
    print("   uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload")
    print()
    print("   Start UI (new terminal):")
    print("   cd frontend && npm install && npm run dev")
    print()
    print("   Open: http://localhost:3000")
    print("  =========================================")
    print()

asyncio.run(main())
