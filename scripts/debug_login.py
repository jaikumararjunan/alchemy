"""
Debug login failure - runs synchronously, no async needed.
Run: python scripts\debug_login.py
"""
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB = PROJECT_ROOT / "data" / "alchemy.db"
EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@alchemy.in")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Alchemy#Admin!2024")

print(f"DB path : {DB}")
print(f"DB exists: {DB.exists()}")
print()

if not DB.exists():
    print("ERROR: DB not found. Run: python scripts\\reset_password.py")
    sys.exit(1)

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# 1. Check user exists
row = conn.execute("SELECT * FROM users WHERE email=?", (EMAIL,)).fetchone()
if not row:
    print(f"ERROR: No user with email '{EMAIL}' found in DB")
    print("Fix: python scripts\\reset_password.py")
    sys.exit(1)

print(f"User found  : {row['email']}")
print(f"Status      : {row['status']}")
print(f"Role        : {row['role']}")
print(f"Email verified: {row['email_verified']}")
print(f"Failed logins : {row['failed_login_count']}")
print(f"Locked until  : {row['locked_until']}")
print(f"Hash prefix   : {row['password_hash'][:30]}...")
print()

# 2. Check bcrypt directly
import bcrypt
stored = row['password_hash']
ok = bcrypt.checkpw(PASSWORD.encode('utf-8'), stored.encode('utf-8'))
print(f"Password '{PASSWORD}'")
print(f"bcrypt check  : {'PASS' if ok else 'FAIL'}")
print()

if not ok:
    print("Password hash mismatch — resetting now...")
    new_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(12)).decode()
    conn.execute("""
        UPDATE users SET
            password_hash=?, status='active', email_verified=1,
            failed_login_count=0, locked_until=NULL
        WHERE email=?
    """, (new_hash, EMAIL))
    conn.commit()
    ok2 = bcrypt.checkpw(PASSWORD.encode(), new_hash.encode())
    print(f"New hash set, verify: {'PASS' if ok2 else 'FAIL'}")
    print()

# 3. Check all users
print("All users in DB:")
for u in conn.execute("SELECT email, role, status, email_verified FROM users").fetchall():
    print(f"  {u['email']:30s}  role={u['role']:12s}  status={u['status']:10s}  verified={u['email_verified']}")

conn.close()
print()
print("Restart uvicorn and try logging in again.")
