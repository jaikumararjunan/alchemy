"""alchemy.api.auth_routes v0.5.1 — fixed async DB injection"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from alchemy.auth.middleware import check_rate_limit, get_current_user, CurrentUser, get_client_ip
from alchemy.auth.security import PasswordPolicy

router = APIRouter(prefix="/auth", tags=["authentication"])

class SignupRequest(BaseModel):
    email: EmailStr; username: str = Field(..., min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_-]+$')
    full_name: str = Field(..., min_length=2, max_length=255); password: str = Field(..., min_length=12, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr; password: str; totp_code: Optional[str] = None

class TwoFAVerifyRequest(BaseModel): code: str = Field(..., min_length=6, max_length=8)
class TwoFADisableRequest(BaseModel): password: str
class PasswordResetRequest(BaseModel): email: EmailStr
class PasswordResetConfirmRequest(BaseModel): token: str; new_password: str = Field(..., min_length=12)

async def get_db():
    from alchemy.api.database import get_session_factory
    async with get_session_factory()() as s: yield s

def _svc():
    from alchemy.auth.service import AuthService; return AuthService()

def _set_cookie(response, token):
    response.set_cookie(key="refresh_token", value=token, httponly=True, secure=False,
                        samesite="lax", max_age=7*24*3600, path="/auth")

def _clear_cookie(response): response.delete_cookie("refresh_token", path="/auth")

@router.post("/signup", status_code=201)
async def signup(req: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.signup")
    from alchemy.auth.service import AuthError
    try:
        user = await _svc().signup(db, email=req.email, username=req.username, full_name=req.full_name, password=req.password)
        await db.commit()
        return {"message": "Account created.", "user": user.safe_dict()}
    except AuthError as e: raise HTTPException(400, str(e))
    except Exception as e: raise HTTPException(500, f"Signup failed: {e}")

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.login")
    from alchemy.auth.service import AuthError
    try:
        result = await _svc().login(db, email=req.email, password=req.password,
                                     ip_address=get_client_ip(request), user_agent=request.headers.get("User-Agent",""),
                                     totp_code=req.totp_code)
        await db.commit()
        if result.get("requires_2fa"): return {"requires_2fa": True, "user_id": result["user_id"]}
        _set_cookie(response, result["refresh_token"])
        return {"access_token": result["access_token"], "token_type": "bearer", "user": result["user"]}
    except AuthError as e: raise HTTPException(429 if getattr(e,"code","")=="account_locked" else 401, str(e))
    except Exception as e: raise HTTPException(500, f"Login error: {e}")

@router.post("/refresh")
async def refresh_tokens(response: Response, db: AsyncSession = Depends(get_db),
                          refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    if not refresh_token: raise HTTPException(401, "No refresh token")
    from alchemy.auth.service import AuthError
    try:
        result = await _svc().refresh_tokens(db, refresh_token); await db.commit()
        _set_cookie(response, result["refresh_token"])
        return {"access_token": result["access_token"], "token_type": "bearer"}
    except AuthError as e: raise HTTPException(401, str(e))

@router.post("/logout")
async def logout(response: Response, db: AsyncSession = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user),
                  refresh_token: Optional[str] = Cookie(None, alias="refresh_token")):
    _clear_cookie(response)
    if refresh_token:
        try: await _svc().logout(db, refresh_token, user.user_id); await db.commit()
        except: pass
    return {"message": "Logged out"}

@router.post("/logout-all")
async def logout_all(response: Response, db: AsyncSession = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    _clear_cookie(response)
    count = await _svc().logout_all(db, user.user_id); await db.commit()
    return {"message": f"Revoked {count} sessions"}

@router.post("/2fa/setup")
async def setup_2fa(db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    data = await _svc().setup_2fa(db, user.user_id); await db.commit(); return data

@router.post("/2fa/verify")
async def verify_2fa(req: TwoFAVerifyRequest, request: Request, db: AsyncSession = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    check_rate_limit(request, "auth.2fa")
    from alchemy.auth.service import AuthError
    try:
        await _svc().verify_and_enable_2fa(db, user.user_id, req.code); await db.commit()
        return {"message": "2FA enabled", "enabled": True}
    except AuthError as e: raise HTTPException(400, str(e))

@router.post("/2fa/disable")
async def disable_2fa(req: TwoFADisableRequest, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    from alchemy.auth.service import AuthError
    try:
        await _svc().disable_2fa(db, user.user_id, req.password); await db.commit()
        return {"message": "2FA disabled"}
    except AuthError as e: raise HTTPException(400, str(e))

@router.post("/password/reset-request")
async def request_reset(req: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, "auth.reset")
    await _svc().request_password_reset(db, req.email); await db.commit()
    return {"message": "If that email exists, a reset link has been sent."}

@router.post("/password/reset")
async def reset_password(req: PasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    from alchemy.auth.service import AuthError
    try:
        await _svc().reset_password(db, req.token, req.new_password); await db.commit()
        return {"message": "Password reset. Please login."}
    except AuthError as e: raise HTTPException(400, str(e))

@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email, "role": user.role}

@router.get("/password/strength")
async def password_strength(password: str):
    return {"score": PasswordPolicy.strength_score(password), "errors": PasswordPolicy.validate(password), "valid": not PasswordPolicy.validate(password)}
