"""
alchemy.api.auth_routes
=======================
Authentication endpoints — login, signup, refresh, logout, 2FA, password reset.

All database operations use SQLAlchemy async sessions via AuthService.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

import structlog
from alchemy.auth.middleware import check_rate_limit, get_current_user, CurrentUser, get_client_ip
from alchemy.auth.security import PasswordPolicy
from alchemy.core.messages import msg
from alchemy.auth.guards import check_credential_stuffing
from alchemy.auth.service import AuthService, AuthError

log = structlog.get_logger(__name__)

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
            "email_verified, failed_login_count, locked_until, totp_enabled, subscription "
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
            # Auto-activate (OTP email verification disabled)
            conn.execute("UPDATE users SET status='active', email_verified=1 WHERE email=?", (row["email"],))
            conn.commit()

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
            "subscription": row["subscription"] or "free",
        }
    finally:
        conn.close()


def _create_tokens_sync(user_id: str, email: str, role: str, subscription: str = "free") -> dict:
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
        "subscription": subscription,
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
async def login(req: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)):
    """Authenticate user with email + password (+ optional TOTP)."""
    check_rate_limit(request, "auth.login")
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    check_credential_stuffing(ip)
    try:
        svc = AuthService()
        result = await svc.login(
            db, email=req.email, password=req.password,
            ip_address=ip, user_agent=ua, totp_code=req.totp_code,
        )
        await db.commit()

        # If 2FA is required, return early without tokens
        if result.get("requires_2fa"):
            return result

        _set_cookie(response, result["refresh_token"])
        return {
            "access_token": result["access_token"],
            "token_type":   "bearer",
            "user":         result["user"],
        }
    except AuthError as e:
        # Persist failed-login counter / lockout changes so brute-force
        # protection actually works across requests.
        await db.commit()
        code = getattr(e, "code", "auth_error")

        # If account is pending verification, send/resend OTP instead of blocking
        if code == "account_pending_verification":
            from alchemy.notifications.email_service import EmailConfig
            smtp_cfg = EmailConfig()

            if not smtp_cfg.enabled:
                # SMTP not configured — auto-activate and login
                import sqlite3
                conn = sqlite3.connect(_get_db_path())
                conn.execute("UPDATE users SET status='active', email_verified=1 WHERE LOWER(email)=LOWER(?)",
                             (req.email,))
                conn.commit(); conn.close()
                log.warning("auth.login_auto_activated_no_smtp", email=req.email)

                # Retry login
                try:
                    result = await svc.login(
                        db, email=req.email, password=req.password,
                        ip_address=ip, user_agent=ua, totp_code=req.totp_code,
                    )
                    await db.commit()
                    if result.get("requires_2fa"):
                        return result
                    _set_cookie(response, result["refresh_token"])
                    return {
                        "access_token": result["access_token"],
                        "token_type": "bearer",
                        "user": result["user"],
                    }
                except Exception:
                    pass

            # SMTP configured — send OTP
            try:
                from alchemy.auth.otp_store import generate_otp
                from alchemy.notifications.email_service import send_otp_email
                otp = generate_otp("verification", req.email)
                sent = send_otp_email(req.email, otp, "verification")
                log.info("auth.login_pending_otp_sent", email=req.email, sent=sent)
            except Exception:
                pass
            return {
                "requires_otp": True,
                "email": req.email,
                "message": "Please verify your email. A new OTP has been sent.",
            }

        messages = {
            "invalid_credentials":          msg("auth_login_invalid"),
            "account_banned":               msg("auth_login_banned"),
            "account_locked":               msg("auth_login_locked"),
        }
        status_code = 429 if code == "account_locked" else 401
        raise HTTPException(status_code, {
            "code":    code,
            "message": messages.get(code, str(e)),
        })
    except Exception as e:
        log.error("auth.login_failed", error=str(e), exc_info=True)
        raise HTTPException(500, {"code": "server_error", "message": msg("server_error")})


@router.post("/signup", status_code=201)
async def signup(req: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.signup")
    try:
        from alchemy.core.config import get_config
        svc  = AuthService()
        user = await svc.signup(db, email=req.email, username=req.username,
                                full_name=req.full_name, password=req.password)
        # Auto-activate all users (OTP email verification disabled)
        user.status         = "active"
        user.email_verified = True
        log.info("auth.auto_activated", email=req.email)

        # Persist user to DB before attempting auto-login so the account
        # is saved even if login fails (e.g. pending status in production).
        await db.commit()

        # Auto-login after signup
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "")
        try:
            result = await svc.login(
                db, email=req.email, password=req.password,
                ip_address=ip, user_agent=ua,
            )
            await db.commit()
            _set_cookie(response, result["refresh_token"])
            return {
                "message":      msg("auth_signup_success", name=user.full_name.split()[0]),
                "access_token": result["access_token"],
                "user":         user.safe_dict(),
            }
        except AuthError:
            # User is pending email verification. Try to send OTP.
            from alchemy.notifications.email_service import EmailConfig
            smtp_cfg = EmailConfig()

            if not smtp_cfg.enabled:
                # SMTP not configured — auto-activate the user (graceful degradation)
                import sqlite3
                from alchemy.api.auth_routes import _get_db_path
                conn = sqlite3.connect(_get_db_path())
                conn.execute("UPDATE users SET status='active', email_verified=1 WHERE LOWER(email)=LOWER(?)",
                             (req.email,))
                conn.commit(); conn.close()
                log.warning("auth.signup_auto_activated_no_smtp", email=req.email)

                # Retry login now that user is active
                try:
                    result = await svc.login(
                        db, email=req.email, password=req.password,
                        ip_address=ip, user_agent=ua,
                    )
                    await db.commit()
                    _set_cookie(response, result["refresh_token"])
                    return {
                        "message": "Account created and activated! (Email verification skipped — SMTP not configured)",
                        "access_token": result["access_token"],
                        "user": user.safe_dict(),
                    }
                except Exception:
                    return {
                        "message": "Account created and activated. Please sign in.",
                        "user": user.safe_dict(),
                    }

            # SMTP IS configured — send OTP email
            try:
                from alchemy.auth.otp_store import generate_otp
                from alchemy.notifications.email_service import send_otp_email
                otp = generate_otp("verification", req.email)
                sent = send_otp_email(req.email, otp, "verification")
                if sent:
                    log.info("auth.signup_otp_sent", email=req.email)
                else:
                    log.warning("auth.signup_otp_send_failed", email=req.email)
            except Exception as otp_err:
                log.error("auth.signup_otp_error", error=str(otp_err))

            return {
                "message": "Account created! Please check your email for the verification code.",
                "requires_otp": True,
                "email": req.email,
                "user": user.safe_dict(),
            }
    except AuthError as e:
        code    = getattr(e, "code", "signup_error")
        msg_map = {
            "email_taken":    msg("auth_signup_email_taken"),
            "username_taken": msg("auth_signup_username_taken", username=req.username),
            "weak_password":  msg("auth_signup_password_weak"),
        }
        raise HTTPException(400, {
            "code":    code,
            "message": msg_map.get(code, str(e)),
        })
    except ValueError as e:
        raise HTTPException(422, {
            "code":    "validation_error",
            "message": msg("auth_signup_username_invalid") if "username" in str(e).lower()
                       else msg("auth_signup_password_weak") if "password" in str(e).lower()
                       else str(e),
        })
    except Exception as e:
        log.error("auth.signup_failed", error=str(e), exc_info=True)
        raise HTTPException(500, {
            "code":    "server_error",
            "message": msg("auth_signup_server_error"),
        })


@router.post("/refresh")
async def refresh_tokens(response: Response, db: AsyncSession = Depends(get_db),
                          refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    if not refresh_token:
        raise HTTPException(401, "No refresh token")
    try:
        svc = AuthService()
        result = await svc.refresh_tokens(db, refresh_token)
        await db.commit()
        _set_cookie(response, result["refresh_token"])
        return {"access_token": result["access_token"], "token_type": "bearer"}
    except AuthError:
        raise HTTPException(401, "Invalid or expired refresh token")
    except Exception as e:
        raise HTTPException(401, f"Refresh failed: {e}")


@router.post("/logout")
async def logout(response: Response, db: AsyncSession = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user),
                  refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    """Invalidate current session."""
    _clear_cookie(response)
    if refresh_token:
        try:
            svc = AuthService()
            await svc.logout(db, refresh_token, user.user_id)
            await db.commit()
        except Exception:
            pass  # Best-effort — cookie is already cleared
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(response: Response, db: AsyncSession = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    """Revoke ALL sessions for a user."""
    _clear_cookie(response)
    try:
        svc = AuthService()
        await svc.logout_all(db, user.user_id)
        await db.commit()
    except Exception:
        pass  # Best-effort — cookie is already cleared
    return {"message": "Logged out from all devices"}


@router.post("/2fa/setup")
async def setup_2fa(db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    svc = AuthService()
    data = await svc.setup_2fa(db, user.user_id); await db.commit(); return data


@router.post("/2fa/verify")
async def verify_2fa(req: TwoFAVerifyRequest, request: Request,
                      db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    check_rate_limit(request, "auth.2fa")
    try:
        svc = AuthService()
        await svc.verify_and_enable_2fa(db, user.user_id, req.code); await db.commit()
        return {"message": "2FA enabled", "enabled": True}
    except AuthError as e: raise HTTPException(400, str(e))


@router.post("/2fa/disable")
async def disable_2fa(req: TwoFADisableRequest, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    try:
        svc = AuthService()
        await svc.disable_2fa(db, user.user_id, req.password); await db.commit()
        return {"message": "2FA disabled"}
    except AuthError as e: raise HTTPException(400, str(e))


@router.post("/password/reset-request")
async def request_reset(req: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.reset")
    svc = AuthService()
    await svc.request_password_reset(db, req.email); await db.commit()
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password/reset")
async def reset_password(req: PasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    try:
        svc = AuthService()
        await svc.reset_password(db, req.token, req.new_password); await db.commit()
        return {"message": "Password reset. Please login."}
    except AuthError as e: raise HTTPException(400, str(e))


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email, "role": user.role,
            "subscription": getattr(user, "subscription", None) or "free"}


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
