"""
alchemy.api.otp_routes
=======================
Email OTP verification + 2FA setup/login endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from typing import Optional
import structlog

from alchemy.auth.middleware import get_current_user, CurrentUser, check_rate_limit
from alchemy.auth.otp_store import generate_otp, verify_otp, invalidate_otp
from alchemy.notifications.email_service import send_otp_email, send_2fa_enabled_email

log    = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth/otp", tags=["auth-otp"])


# ── Schemas ────────────────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    email: str
    purpose: str = "verification"   # verification | login | password_reset

class VerifyOTPRequest(BaseModel):
    email: str
    otp:   str
    purpose: str = "verification"

class Setup2FARequest(BaseModel):
    totp_code: str   # verify user has their authenticator working

class Verify2FARequest(BaseModel):
    email:    str
    totp_code: Optional[str] = None   # TOTP from authenticator
    email_otp: Optional[str] = None   # email OTP fallback


# ── Email OTP endpoints ────────────────────────────────────────────────────

@router.post("/send")
async def send_otp(req: SendOTPRequest, request: Request):
    """Send OTP to email. Rate limited to 3 per 10 minutes."""
    check_rate_limit(request, "auth.otp_send")
    otp  = generate_otp(req.purpose, req.email)
    sent = send_otp_email(req.email, otp, req.purpose)

    if not sent:
        # In dev mode: return OTP in response (never in production)
        from alchemy.core.config import get_config
        cfg = get_config()
        if cfg.env in ("development","dev","local","test"):
            log.info("otp.dev_mode", email=req.email, otp=otp, purpose=req.purpose)
            return {
                "sent": False,
                "dev_otp": otp,
                "message": "SMTP not configured — OTP shown for dev only",
            }
        raise HTTPException(503, "Email service unavailable. Configure SMTP_USER + SMTP_PASSWORD.")

    log.info("otp.sent", email=req.email, purpose=req.purpose)
    return {"sent": True, "message": f"OTP sent to {req.email}"}


@router.post("/verify")
async def verify_email_otp(req: VerifyOTPRequest):
    """Verify OTP. Activates account if purpose=verification."""
    ok = verify_otp(req.purpose, req.email, req.otp)
    if not ok:
        raise HTTPException(400, "Invalid or expired OTP. Request a new one.")

    if req.purpose == "verification":
        # Activate the user account
        import sqlite3
        from alchemy.api.auth_routes import _get_db_path
        conn = sqlite3.connect(_get_db_path())
        conn.execute("UPDATE users SET status='active', email_verified=1 WHERE LOWER(email)=LOWER(?)",
                     (req.email,))
        conn.commit(); conn.close()
        log.info("otp.email_verified", email=req.email)
        return {"verified": True, "message": "Email verified. You can now sign in."}

    return {"verified": True, "message": "OTP verified."}


@router.post("/resend")
async def resend_otp(req: SendOTPRequest, request: Request):
    """Resend OTP (invalidates previous)."""
    check_rate_limit(request, "auth.otp_send")
    invalidate_otp(req.purpose, req.email)
    return await send_otp(req, request)


# ── 2FA setup endpoints ────────────────────────────────────────────────────

@router.post("/2fa/setup/init")
async def init_2fa_setup(user: CurrentUser = Depends(get_current_user)):
    """Generate TOTP secret and QR code for setup."""
    from alchemy.auth.security import TOTPManager
    secret  = TOTPManager.generate_secret()
    qr_b64  = TOTPManager.generate_qr_code(secret, user.email)

    # Store secret temporarily (not yet active)
    generate_otp("2fa_pending_secret", user.user_id, length=32)
    # Store actual secret in a side channel
    from alchemy.auth.otp_store import _store
    _store._store[f"2fa_secret:{user.user_id}"] = (secret, __import__("time").time() + 600)

    return {
        "secret":     secret,
        "qr_code":    qr_b64,
        "issuer":     "Alchemy Trading",
        "account":    user.email,
        "instructions": [
            "1. Open Google Authenticator or Authy",
            "2. Tap '+' → 'Scan QR code'",
            "3. Scan the QR code above",
            "4. Enter the 6-digit code below to confirm setup",
        ],
    }


@router.post("/2fa/setup/confirm")
async def confirm_2fa_setup(req: Setup2FARequest,
                              user: CurrentUser = Depends(get_current_user)):
    """Confirm TOTP setup by verifying the code from authenticator."""
    from alchemy.auth.security import TOTPManager
    from alchemy.auth.otp_store import _store
    import time

    # Retrieve pending secret
    entry = _store._store.get(f"2fa_secret:{user.user_id}")
    if not entry or time.time() > entry[1]:
        raise HTTPException(400, "Setup session expired. Start over.")

    secret = entry[0]  # plain secret stored directly
    if not TOTPManager.verify_code(secret, req.totp_code):
        raise HTTPException(400, "Invalid code. Check your authenticator app.")

    # Activate 2FA in database
    import sqlite3
    from alchemy.api.auth_routes import _get_db_path
    conn = sqlite3.connect(_get_db_path())
    conn.execute("UPDATE users SET totp_enabled=1, totp_secret=? WHERE id=?",
                 (secret, user.user_id))
    conn.commit(); conn.close()

    # Clean up pending
    _store._store.pop(f"2fa_secret:{user.user_id}", None)

    # Send confirmation email
    send_2fa_enabled_email(user.email)
    log.info("2fa.enabled", user_id=user.user_id, email=user.email)

    return {
        "enabled":  True,
        "message":  "2FA enabled successfully.",
        "backup_hint": "Save your TOTP secret as backup: " + secret[:8] + "…",
    }


@router.post("/2fa/disable")
async def disable_2fa(req: Setup2FARequest,
                       user: CurrentUser = Depends(get_current_user)):
    """Disable 2FA. Requires current TOTP code."""
    from alchemy.auth.security import TOTPManager
    import sqlite3
    from alchemy.api.auth_routes import _get_db_path

    conn = sqlite3.connect(_get_db_path())
    row  = conn.execute("SELECT totp_secret FROM users WHERE id=?", (user.user_id,)).fetchone()
    if not row or not row[0]:
        conn.close()
        raise HTTPException(400, "2FA is not enabled on this account.")

    if not TOTPManager.verify_code(row[0], req.totp_code):
        conn.close()
        raise HTTPException(400, "Invalid TOTP code.")

    conn.execute("UPDATE users SET totp_enabled=0, totp_secret=NULL WHERE id=?", (user.user_id,))
    conn.commit(); conn.close()
    log.info("2fa.disabled", user_id=user.user_id)
    return {"disabled": True, "message": "2FA disabled."}


@router.get("/2fa/status")
async def get_2fa_status(user: CurrentUser = Depends(get_current_user)):
    import sqlite3
    from alchemy.api.auth_routes import _get_db_path
    conn = sqlite3.connect(_get_db_path())
    row  = conn.execute("SELECT totp_enabled FROM users WHERE id=?", (user.user_id,)).fetchone()
    conn.close()
    return {"enabled": bool(row and row[0])}
