"""
alchemy.api.auth_routes - simplified login using raw sqlite3 to bypass ORM issues
"""
from __future__ import annotations
import asyncio
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from alchemy.auth.middleware import check_rate_limit, get_current_user, CurrentUser, get_client_ip
from alchemy.auth.security import PasswordPolicy

router = APIRouter(prefix="/auth", tags=["authentication"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:     str
    password:  str
    totp_code: Optional[str] = None

class SignupRequest(BaseModel):
    email:     str
    username:  str  = Field(..., min_length=3, max_length=32)
    full_name: str  = Field(..., min_length=2, max_length=255)
    password:  str  = Field(..., min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, v):
        import re as _re
        v = v.strip()
        if not _re.match(r'^[a-zA-Z0-9_]{3,32}$', v):
            raise ValueError("Username must be 3-32 chars: letters, numbers, underscore only. No spaces.")
        return v.lower()

class TwoFAVerifyRequest(BaseModel):  code: str
class TwoFADisableRequest(BaseModel): password: str
class PasswordResetRequest(BaseModel): email: str
class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12)


def _get_db_path() -> str:
    """Find the SQLite database file."""
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
    path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    if path.startswith("./") or path.startswith(".\\"):
        path = path[2:]
    # Make absolute relative to CWD
    abs_path = Path(path)
    if not abs_path.is_absolute():
        abs_path = Path.cwd() / abs_path
    return str(abs_path)


def _login_sync(email: str, password: str) -> dict:
    """
    Login using raw sqlite3 + bcrypt — bypasses SQLAlchemy entirely.
    Runs in a thread executor to avoid blocking the event loop.
    """
    import bcrypt

    db_path = _get_db_path()

    if not Path(db_path).exists():
        raise ValueError(f"Database not found: {db_path}. Run: python scripts\\reset_password.py")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, email, username, full_name, password_hash, role, status, "
            "email_verified, failed_login_count, locked_until, totp_enabled "
            "FROM users WHERE LOWER(email)=LOWER(?)",
            (email.strip(),)
        ).fetchone()

        if not row:
            raise ValueError("invalid_credentials")

        if row["status"] == "banned":
            raise ValueError("account_banned")

        if row["status"] == "locked":
            raise ValueError("account_locked")

        if row["status"] == "pending":
            # Auto-activate in dev mode; in prod would require email verification
            from alchemy.core.config import get_config
            if get_config().env in ("development","dev","local","test"):
                conn.execute("UPDATE users SET status='active', email_verified=1 WHERE email=?", (row["email"],))
                conn.commit()
            else:
                raise ValueError("account_pending_verification")

        # Check password
        stored_hash = row["password_hash"]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        ok = bcrypt.checkpw(password.encode("utf-8"), stored_hash)
        if not ok:
            # Increment failed count
            conn.execute(
                "UPDATE users SET failed_login_count=failed_login_count+1 WHERE email=?",
                (row["email"],)
            )
            conn.commit()
            raise ValueError("invalid_credentials")

        # Reset failed count + update last login
        conn.execute(
            "UPDATE users SET failed_login_count=0, last_login_at=? WHERE email=?",
            (datetime.now(timezone.utc).isoformat(), row["email"])
        )
        conn.commit()

        return {
            "id":       row["id"],
            "email":    row["email"],
            "username": row["username"],
            "full_name":row["full_name"],
            "role":     row["role"],
            "status":   row["status"],
            "totp_enabled": bool(row["totp_enabled"]),
        }
    finally:
        conn.close()


def _create_tokens_sync(user_id: str, email: str, role: str) -> dict:
    """Create JWT access token + refresh token."""
    import secrets, hashlib, jwt

    from alchemy.core.config import get_config
    secret = get_config().jwt_secret_key
    now    = datetime.now(timezone.utc)
    jti    = secrets.token_hex(8)

    access_token = jwt.encode({
        "sub":   user_id,
        "email": email,
        "role":  role,
        "jti":   jti,
        "iat":   now,
        "exp":   now + timedelta(minutes=15),
        "type":  "access",
    }, secret, algorithm="HS256")

    raw_refresh = secrets.token_urlsafe(48)
    hashed_refresh = hashlib.sha256(raw_refresh.encode()).hexdigest()

    # Store session in DB
    db_path = _get_db_path()
    session_id = str(__import__("uuid").uuid4())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_sessions
            (id, user_id, refresh_token_hash, access_jti, is_active, created_at, expires_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (
            session_id, user_id, hashed_refresh, jti,
            now.isoformat(),
            (now + timedelta(days=7)).isoformat()
        ))
        conn.commit()
    except Exception:
        pass  # Session storage is best-effort
    finally:
        conn.close()

    return {"access_token": access_token, "refresh_token": raw_refresh}


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token", value=token,
        httponly=True, secure=False, samesite="lax",
        max_age=7*24*3600, path="/auth"
    )

def _clear_cookie(response: Response) -> None:
    response.delete_cookie("refresh_token", path="/auth")


async def get_db():
    from alchemy.api.database import get_session_factory
    async with get_session_factory()() as s: yield s


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Login using raw sqlite3 — bypasses SQLAlchemy ORM."""
    check_rate_limit(request, "auth.login")
    try:
        loop = asyncio.get_running_loop()
        user = await loop.run_in_executor(None, _login_sync, req.email, req.password)
        tokens = await loop.run_in_executor(None, _create_tokens_sync,
                                             user["id"], user["email"], user["role"])
        _set_cookie(response, tokens["refresh_token"])
        return {
            "access_token": tokens["access_token"],
            "token_type":   "bearer",
            "user":         user,
        }
    except ValueError as e:
        code = str(e)
        raise HTTPException(429 if code == "account_locked" else 401,
                            "Invalid email or password")
    except Exception as e:
        raise HTTPException(500, f"Login error: {e}")


@router.post("/signup", status_code=201)
async def signup(req: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.signup")
    from alchemy.auth.service import AuthError
    try:
        from alchemy.auth.service import AuthService
        from alchemy.core.config import get_config
        svc  = AuthService()
        user = await svc.signup(db, email=req.email, username=req.username,
                                full_name=req.full_name, password=req.password)
        # Auto-activate in dev mode (no email verification required)
        cfg = get_config()
        if cfg.env in ("development", "dev", "local", "test"):
            user.status         = "active"
            user.email_verified = True
            log.info("auth.auto_activated", email=req.email, env=cfg.env)
        await db.commit()
        # Auto-login after signup
        tokens = await asyncio.get_running_loop().run_in_executor(
            None, _create_tokens_sync, str(user.id), user.email, user.role
        )
        _set_refresh_cookie(response, tokens["refresh_token"])
        return {
            "message":      "Account created and signed in.",
            "access_token": tokens["access_token"],
            "user":         user.safe_dict(),
        }
    except AuthError as e:
        raise HTTPException(400, {"message": str(e), "code": getattr(e, "code", "signup_error")})
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), "code": "validation_error"})
    except Exception as e:
        log.error("auth.signup_failed", error=str(e), exc_info=True)
        raise HTTPException(500, {"message": "Signup failed. Please try again.", "code": "server_error"})


@router.post("/refresh")
async def refresh_tokens(response: Response,
                          refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    if not refresh_token:
        raise HTTPException(401, "No refresh token")
    try:
        import hashlib, sqlite3
        hashed = hashlib.sha256(refresh_token.encode()).hexdigest()
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT s.user_id, u.email, u.role, s.expires_at
            FROM user_sessions s JOIN users u ON s.user_id=u.id
            WHERE s.refresh_token_hash=? AND s.is_active=1
        """, (hashed,)).fetchone()
        conn.close()

        if not row:
            raise HTTPException(401, "Invalid refresh token")

        # Check expiry
        exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp:
            raise HTTPException(401, "Refresh token expired")

        loop   = asyncio.get_running_loop()
        tokens = await loop.run_in_executor(None, _create_tokens_sync,
                                             row["user_id"], row["email"], row["role"])
        _set_cookie(response, tokens["refresh_token"])
        return {"access_token": tokens["access_token"], "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"Refresh failed: {e}")


@router.post("/logout")
async def logout(response: Response, user: CurrentUser = Depends(get_current_user),
                  refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    _clear_cookie(response)
    if refresh_token:
        import hashlib, sqlite3
        hashed = hashlib.sha256(refresh_token.encode()).hexdigest()
        try:
            conn = sqlite3.connect(_get_db_path())
            conn.execute("UPDATE user_sessions SET is_active=0 WHERE refresh_token_hash=?", (hashed,))
            conn.commit(); conn.close()
        except Exception: pass
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(response: Response, user: CurrentUser = Depends(get_current_user)):
    _clear_cookie(response)
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("UPDATE user_sessions SET is_active=0 WHERE user_id=?", (user.user_id,))
        conn.commit(); conn.close()
    except Exception: pass
    return {"message": "Logged out from all devices"}


@router.post("/2fa/setup")
async def setup_2fa(db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    from alchemy.auth.service import AuthService
    data = await AuthService().setup_2fa(db, user.user_id); await db.commit(); return data


@router.post("/2fa/verify")
async def verify_2fa(req: TwoFAVerifyRequest, request: Request,
                      db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    check_rate_limit(request, "auth.2fa")
    from alchemy.auth.service import AuthService, AuthError
    try:
        await AuthService().verify_and_enable_2fa(db, user.user_id, req.code); await db.commit()
        return {"message": "2FA enabled", "enabled": True}
    except AuthError as e: raise HTTPException(400, str(e))


@router.post("/2fa/disable")
async def disable_2fa(req: TwoFADisableRequest, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    from alchemy.auth.service import AuthService, AuthError
    try:
        await AuthService().disable_2fa(db, user.user_id, req.password); await db.commit()
        return {"message": "2FA disabled"}
    except AuthError as e: raise HTTPException(400, str(e))


@router.post("/password/reset-request")
async def request_reset(req: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.reset")
    from alchemy.auth.service import AuthService
    await AuthService().request_password_reset(db, req.email); await db.commit()
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password/reset")
async def reset_password(req: PasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    from alchemy.auth.service import AuthService, AuthError
    try:
        await AuthService().reset_password(db, req.token, req.new_password); await db.commit()
        return {"message": "Password reset. Please login."}
    except AuthError as e: raise HTTPException(400, str(e))


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email, "role": user.role}


@router.get("/password/strength")
async def password_strength(password: str):
    errors = PasswordPolicy.validate(password)
    return {"score": PasswordPolicy.strength_score(password), "errors": errors, "valid": not errors}


@router.post("/rate-limit/reset")
async def reset_rate_limit(request: Request):
    """Reset rate limits — dev only."""
    from alchemy.core.config import get_config
    if get_config().env not in ("development","dev","local","test"):
        raise HTTPException(403, "Only available in development mode")
    from alchemy.auth.middleware import clear_rate_limit
    ip = request.client.host if request.client else None
    clear_rate_limit(ip)
    return {"ok": True, "message": f"Rate limit cleared for {ip}"}
