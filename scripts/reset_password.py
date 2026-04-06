"""
Direct password reset using raw sqlite3 — no async, no SQLAlchemy.
Run: python scripts\reset_password.py
"""
import sqlite3
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Find the DB file
candidates = [
    PROJECT_ROOT / "data" / "alchemy.db",
    PROJECT_ROOT / "alchemy_dev.db",
]

db_path = None
for c in candidates:
    if c.exists():
        db_path = c
        break

if not db_path:
    print(f"No database found. Run: python scripts\\create_admin.py first")
    sys.exit(1)

print(f"Database: {db_path}")

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@alchemy.in")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Alchemy#Admin!2024")

# Install bcrypt if needed
try:
    import bcrypt
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bcrypt", "-q"])
    import bcrypt

# Hash the password
pwd_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()

# Update directly via sqlite3
conn = sqlite3.connect(str(db_path))
cur  = conn.cursor()

# Check if user exists
cur.execute("SELECT id, email, status, role FROM users WHERE email = ?", (ADMIN_EMAIL,))
row = cur.fetchone()

if row:
    user_id, email, status, role = row
    cur.execute("""
        UPDATE users
        SET password_hash   = ?,
            status          = 'active',
            email_verified  = 1,
            role            = 'super_admin',
            failed_login_count = 0,
            locked_until    = NULL
        WHERE email = ?
    """, (pwd_hash, ADMIN_EMAIL))
    conn.commit()
    print(f"Password reset for: {email}")
    print(f"Status: {status} -> active")
    print(f"Role:   {role} -> super_admin")
else:
    # Insert new admin
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO users (
            id, email, username, full_name, password_hash,
            role, status, email_verified,
            failed_login_count, totp_enabled,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, ADMIN_EMAIL, "superadmin", "Super Admin", pwd_hash,
        "super_admin", "active", 1, 0, 0, now, now
    ))
    conn.commit()
    print(f"Admin created: {ADMIN_EMAIL}")

conn.close()

# Verify the password works
cur2 = sqlite3.connect(str(db_path)).cursor()
cur2.execute("SELECT password_hash, status, role FROM users WHERE email = ?", (ADMIN_EMAIL,))
row2 = cur2.fetchone()
if row2:
    stored_hash, status, role = row2
    ok = bcrypt.checkpw(ADMIN_PASSWORD.encode(), stored_hash.encode())
    print(f"\nVerification: password matches = {ok}")
    print(f"Status: {status}, Role: {role}")

print()
print("=" * 45)
print(" Done! You can now login with:")
print(f"  Email   : {ADMIN_EMAIL}")
print(f"  Password: {ADMIN_PASSWORD}")
print(f"  URL     : http://localhost:8000")
print("=" * 45)
print()
print("Restart uvicorn, then login.")
