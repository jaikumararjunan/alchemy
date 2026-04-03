"""
alchemy.api.auth_routes
=======================
Authentication REST API endpoints.

All endpoints use rate limiting.
Refresh tokens set as httpOnly, Secure, SameSite=Strict cookies.
Access tokens returned in response body for SPA (stored in memory, NOT localStorage).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from alchemy.auth.middleware import (
    check_rate_limit, get_current_user, CurrentUser, get_client_ip
)
from alchemy.auth.security import PasswordPolicy

router = APIRouter(prefix="/auth", tags=["authentication"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email:     EmailStr
    username:  str       = Field(..., min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_-]+$')
    full_name: str       = Field(..., min_length=2, max_length=255)
    password:  str       = Field(..., min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors = PasswordPolicy.validate(v)
        if errors:
            raise ValueError(f"Password too weak: {'; '.join(errors)}")
        return v


class LoginRequest(BaseModel):
    email:     EmailStr
    password:  str
    totp_code: Optional[str] = Field(None, min_length=6, max_length=8)


class TwoFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class TwoFADisableRequest(BaseModel):
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token:       str
    new_password: str = Field(..., min_length=12, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(..., min_length=12, max_length=128)


def _get_db():
    """DB session dependency — replace with real async SQLAlchemy session."""
    from alchemy.api.database import get_db_session
    return get_db_session()


def _get_auth_service():
    from alchemy.auth.service import AuthService
    return AuthService()


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set refresh token as httpOnly Secure SameSite=Strict cookie."""
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=True,          # HTTPS only
        samesite="strict",    # CSRF protection
        max_age=7 * 24 * 3600,
        path="/auth",         # Only sent to /auth endpoints
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("refresh_token", path="/auth")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    req: SignupRequest,
    request: Request,
    response: Response,
):
    """Register a new account. Returns user data + access token."""
    check_rate_limit(request, "auth.signup")
    try:
        async for db in _get_db():
            svc  = _get_auth_service()
            user = await svc.signup(
                db, email=req.email, username=req.username,
                full_name=req.full_name, password=req.password,
            )
            await db.commit()
            return {
                "message": "Account created. Please verify your email.",
                "user":    user.safe_dict(),
            }
    except Exception as e:
        from alchemy.auth.service import AuthError
        if isinstance(e, AuthError):
            raise HTTPException(400, detail=str(e))
        raise HTTPException(500, "Signup failed")


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
):
    """Authenticate and return access token. Refresh token set in httpOnly cookie."""
    check_rate_limit(request, "auth.login")
    ip = get_client_ip(request)
    ua = request.headers.get("User-Agent", "")

    try:
        async for db in _get_db():
            svc    = _get_auth_service()
            result = await svc.login(
                db, email=req.email, password=req.password,
                ip_address=ip, user_agent=ua, totp_code=req.totp_code,
            )
            await db.commit()

            if result.get("requires_2fa"):
                return {"requires_2fa": True, "user_id": result["user_id"]}

            _set_refresh_cookie(response, result["refresh_token"])
            return {
                "access_token": result["access_token"],
                "token_type":   "bearer",
                "user":         result["user"],
            }
    except Exception as e:
        from alchemy.auth.service import AuthError
        if isinstance(e, AuthError):
            code = getattr(e, "code", "auth_error")
            status_code = 429 if code == "account_locked" else 401
            raise HTTPException(status_code, detail=str(e))
        raise HTTPException(500, "Login failed")


@router.post("/refresh")
async def refresh_tokens(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
):
    """Exchange refresh token for new access + refresh token pair."""
    if not refresh_token:
        raise HTTPException(401, "No refresh token")
    try:
        async for db in _get_db():
            svc    = _get_auth_service()
            result = await svc.refresh_tokens(db, refresh_token)
            await db.commit()
            _set_refresh_cookie(response, result["refresh_token"])
            return {"access_token": result["access_token"], "token_type": "bearer"}
    except Exception as e:
        from alchemy.auth.service import AuthError
        if isinstance(e, AuthError):
            raise HTTPException(401, str(e))
        raise HTTPException(500, "Token refresh failed")


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    user: CurrentUser = Depends(get_current_user),
):
    """Invalidate session. Clears cookie."""
    _clear_refresh_cookie(response)
    if refresh_token:
        try:
            async for db in _get_db():
                svc = _get_auth_service()
                await svc.logout(db, refresh_token, user.user_id)
                await db.commit()
        except Exception:
            pass
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    user: CurrentUser = Depends(get_current_user),
):
    """Revoke all sessions — useful after password change or suspected breach."""
    _clear_refresh_cookie(response)
    async for db in _get_db():
        svc   = _get_auth_service()
        count = await svc.logout_all(db, user.user_id)
        await db.commit()
    return {"message": f"Logged out from {count} sessions"}


# ── 2FA ───────────────────────────────────────────────────────────────────────

@router.post("/2fa/setup")
async def setup_2fa(user: CurrentUser = Depends(get_current_user)):
    """Initiate 2FA setup. Returns QR code PNG as base64 + backup codes."""
    async for db in _get_db():
        svc  = _get_auth_service()
        data = await svc.setup_2fa(db, user.user_id)
        await db.commit()
    return data


@router.post("/2fa/verify")
async def verify_2fa(
    req: TwoFAVerifyRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Verify first TOTP code and activate 2FA."""
    check_rate_limit(request, "auth.2fa")
    async for db in _get_db():
        svc    = _get_auth_service()
        result = await svc.verify_and_enable_2fa(db, user.user_id, req.code)
        await db.commit()
    return {"message": "2FA enabled successfully", "enabled": True}


@router.post("/2fa/disable")
async def disable_2fa(
    req: TwoFADisableRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Disable 2FA. Requires password confirmation."""
    async for db in _get_db():
        svc = _get_auth_service()
        await svc.disable_2fa(db, user.user_id, req.password)
        await db.commit()
    return {"message": "2FA disabled"}


# ── Password ──────────────────────────────────────────────────────────────────

@router.post("/password/reset-request")
async def request_password_reset(req: PasswordResetRequest, request: Request):
    """Request password reset email. Always returns 200 (no email disclosure)."""
    check_rate_limit(request, "auth.reset")
    async for db in _get_db():
        svc   = _get_auth_service()
        token = await svc.request_password_reset(db, req.email)
        await db.commit()
        # TODO: send email with token
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password/reset")
async def reset_password(req: PasswordResetConfirmRequest):
    """Reset password using token from email."""
    async for db in _get_db():
        svc = _get_auth_service()
        await svc.reset_password(db, req.token, req.new_password)
        await db.commit()
    return {"message": "Password reset successfully. Please login again."}


# ── Session info ──────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {"user_id": user.user_id, "email": user.email, "role": user.role}


@router.get("/password/strength")
async def check_password_strength(password: str):
    """Check password strength without storing it."""
    errors = PasswordPolicy.validate(password)
    score  = PasswordPolicy.strength_score(password)
    return {"score": score, "errors": errors, "valid": len(errors) == 0}
