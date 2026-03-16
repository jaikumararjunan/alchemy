#!/usr/bin/env python3
"""
Alchemy Auth Setup
==================
Interactive one-time helper to generate secure authentication credentials.

Run once before first launch:
    pip3 install pyotp passlib[bcrypt]
    python3 scripts/setup_auth.py

Outputs the lines to paste into your .env file, and prints the TOTP
provisioning URI to scan with Google Authenticator / Authy.
"""

import getpass
import os
import re
import secrets
import sys

# ── Dependency check ──────────────────────────────────────────────────────────
MISSING = []
try:
    import pyotp
except ImportError:
    MISSING.append("pyotp")
try:
    from passlib.context import CryptContext
except ImportError:
    MISSING.append("passlib[bcrypt]")

if MISSING:
    print(f"\nMissing dependencies: {', '.join(MISSING)}")
    print(f"Install them with:  pip3 install {' '.join(MISSING)}\n")
    sys.exit(1)

# ── Helpers (inline — no project imports needed) ──────────────────────────────
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def generate_jwt_secret() -> str:
    return secrets.token_hex(32)


def get_totp_uri(username: str, totp_secret: str) -> str:
    totp = pyotp.TOTP(totp_secret)
    return totp.provisioning_uri(name=username, issuer_name="Alchemy Trading Bot")


def _update_env(path: str, key: str, value: str) -> None:
    """Set KEY=VALUE in .env file, replacing existing line if present."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(f"{key}={value}\n")
        return

    with open(path, "r") as f:
        content = f.read()

    pattern = rf"^{re.escape(key)}=.*$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        with open(path, "w") as f:
            f.write(content)
    else:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  ALCHEMY — Authentication Setup")
    print("=" * 60 + "\n")

    # Username
    username = input("Admin username [admin]: ").strip() or "admin"

    # Password
    while True:
        pw = getpass.getpass("Admin password (min 8 chars): ")
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            print("  ✗ Passwords do not match. Try again.\n")
        elif len(pw) < 8:
            print("  ✗ Password must be at least 8 characters.\n")
        else:
            break

    # Generate secrets
    print("\nGenerating credentials...", end=" ", flush=True)
    password_hash = hash_password(pw)
    totp_secret = generate_totp_secret()
    jwt_secret = generate_jwt_secret()
    uri = get_totp_uri(username, totp_secret)
    print("done.\n")

    # Display
    print("=" * 60)
    print("  Add these lines to your .env file:")
    print("=" * 60)
    print()
    print("AUTH_ENABLED=true")
    print(f"AUTH_USERNAME={username}")
    print(f"AUTH_PASSWORD_HASH={password_hash}")
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"TOTP_SECRET={totp_secret}")
    print()
    print("=" * 60)
    print("  Scan this URI with Google Authenticator / Authy:")
    print("=" * 60)
    print(f"\n{uri}\n")
    print("Or call GET /api/auth/setup after the server starts to see the QR image.")
    print()

    # Optionally write to .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    write = input(f"Update {env_path} automatically? [Y/n]: ").strip().lower()
    if write in ("", "y", "yes"):
        _update_env(env_path, "AUTH_ENABLED", "true")
        _update_env(env_path, "AUTH_USERNAME", username)
        _update_env(env_path, "AUTH_PASSWORD_HASH", password_hash)
        _update_env(env_path, "JWT_SECRET_KEY", jwt_secret)
        _update_env(env_path, "TOTP_SECRET", totp_secret)
        print(f"  ✓ Credentials written to {env_path}")
    print("\nSetup complete. Restart the server to apply changes.\n")


if __name__ == "__main__":
    main()
