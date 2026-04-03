"""
alchemy.api.admin_routes
=========================
Admin-only REST endpoints.
All routes require ADMIN or SUPER_ADMIN role.

Features:
  - User CRUD (list, create, update role, ban, unlock)
  - Audit log viewer with filters
  - System health stats
  - Session management (force-logout any user)
  - Broker gateway status overview
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from alchemy.auth.middleware import CurrentUser, require_role, get_current_user
from alchemy.users.models import UserRole, UserStatus

router = APIRouter(prefix="/admin", tags=["admin"])

require_admin_role = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email:     EmailStr
    username:  str   = Field(..., min_length=3, max_length=32)
    full_name: str   = Field(..., min_length=2, max_length=255)
    password:  str   = Field(..., min_length=12, max_length=128)
    role:      str   = UserRole.TRADER.value

class UpdateUserRequest(BaseModel):
    role:            Optional[str]  = None
    status:          Optional[str]  = None
    full_name:       Optional[str]  = None
    must_change_password: Optional[bool] = None
    preferred_exchange:   Optional[str]  = None


def _get_db():
    from alchemy.api.database import get_db_session
    return get_db_session()


# ── User Management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page:    int   = Query(1, ge=1),
    limit:   int   = Query(50, ge=1, le=200),
    role:    Optional[str] = None,
    status:  Optional[str] = None,
    search:  Optional[str] = None,
    admin:   CurrentUser   = Depends(require_admin_role),
):
    """List all users with pagination and filters."""
    from sqlalchemy import select, or_
    from alchemy.users.models import User

    async for db in _get_db():
        q = select(User)
        if role:   q = q.where(User.role == role)
        if status: q = q.where(User.status == status)
        if search:
            q = q.where(or_(
                User.email.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        q = q.offset((page-1)*limit).limit(limit)
        result = await db.execute(q)
        users  = result.scalars().all()

        # Count total
        from sqlalchemy import func
        count_result = await db.execute(select(func.count(User.id)))
        total = count_result.scalar()

        return {
            "users":      [u.safe_dict() for u in users],
            "total":      total,
            "page":       page,
            "pages":      (total + limit - 1) // limit,
        }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    admin:   CurrentUser = Depends(require_admin_role),
):
    from sqlalchemy import select
    from alchemy.users.models import User
    from uuid import UUID
    async for db in _get_db():
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user   = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")
        return user.safe_dict()


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    req:   CreateUserRequest,
    admin: CurrentUser = Depends(require_admin_role),
):
    """Admin-created user (bypasses email verification)."""
    from alchemy.auth.service import AuthService, AuthError
    async for db in _get_db():
        try:
            svc  = AuthService()
            user = await svc.signup(
                db, email=req.email, username=req.username,
                full_name=req.full_name, password=req.password, role=req.role,
            )
            # Admin-created users are immediately active
            user.status         = UserStatus.ACTIVE.value
            user.email_verified = True
            await db.commit()
            return {"user": user.safe_dict(), "message": "User created by admin"}
        except AuthError as e:
            raise HTTPException(400, str(e))


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    req:     UpdateUserRequest,
    admin:   CurrentUser = Depends(require_admin_role),
):
    from sqlalchemy import select
    from alchemy.users.models import User
    from uuid import UUID

    async for db in _get_db():
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user   = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")

        # Prevent demoting super_admin (unless caller is super_admin)
        if user.role == UserRole.SUPER_ADMIN.value and admin.role != UserRole.SUPER_ADMIN.value:
            raise HTTPException(403, "Only super admins can modify super admin accounts")

        if req.role:     user.role     = req.role
        if req.status:   user.status   = req.status
        if req.full_name: user.full_name = req.full_name
        if req.must_change_password is not None:
            user.must_change_password = req.must_change_password
        if req.preferred_exchange:
            user.preferred_exchange = req.preferred_exchange

        await db.commit()
        return {"user": user.safe_dict(), "message": "User updated"}


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    admin:   CurrentUser = Depends(require_admin_role),
):
    """Immediately ban a user and revoke all their sessions."""
    from sqlalchemy import select, update
    from alchemy.users.models import User, UserSession
    from uuid import UUID
    from alchemy.auth.service import AuthService

    if user_id == admin.user_id:
        raise HTTPException(400, "Cannot ban yourself")

    async for db in _get_db():
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user   = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")

        user.status = UserStatus.BANNED.value
        # Revoke all sessions
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == UUID(user_id))
            .values(is_active=False)
        )
        await db.commit()
        return {"message": f"User {user.email} banned and sessions revoked"}


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: str,
    admin:   CurrentUser = Depends(require_admin_role),
):
    """Unlock a locked account and reset failed login counter."""
    from sqlalchemy import select
    from alchemy.users.models import User
    from uuid import UUID

    async for db in _get_db():
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user   = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")

        user.status           = UserStatus.ACTIVE.value
        user.failed_login_count = 0
        user.locked_until     = None
        await db.commit()
        return {"message": f"User {user.email} unlocked"}


@router.delete("/users/{user_id}/sessions")
async def revoke_user_sessions(
    user_id: str,
    admin:   CurrentUser = Depends(require_admin_role),
):
    """Force-logout a specific user from all devices."""
    from alchemy.auth.service import AuthService
    async for db in _get_db():
        svc   = AuthService()
        count = await svc.logout_all(db, user_id)
        await db.commit()
    return {"message": f"Revoked {count} sessions", "count": count}


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    page:       int            = Query(1, ge=1),
    limit:      int            = Query(100, ge=1, le=500),
    user_id:    Optional[str]  = None,
    action:     Optional[str]  = None,
    status:     Optional[str]  = None,
    min_risk:   int            = Query(0, ge=0, le=100),
    admin:      CurrentUser    = Depends(require_admin_role),
):
    """Query the immutable audit log with filters."""
    from sqlalchemy import select, desc
    from alchemy.users.models import AuditLog
    from uuid import UUID

    async for db in _get_db():
        q = select(AuditLog).order_by(desc(AuditLog.timestamp))
        if user_id:  q = q.where(AuditLog.user_id  == UUID(user_id))
        if action:   q = q.where(AuditLog.action.ilike(f"%{action}%"))
        if status:   q = q.where(AuditLog.status    == status)
        if min_risk: q = q.where(AuditLog.risk_score >= min_risk)
        q = q.offset((page-1)*limit).limit(limit)

        result = await db.execute(q)
        logs   = result.scalars().all()
        return {
            "logs": [
                {
                    "id":         str(l.id),
                    "user_id":    str(l.user_id) if l.user_id else None,
                    "action":     l.action,
                    "status":     l.status,
                    "ip_address": l.ip_address,
                    "risk_score": l.risk_score,
                    "timestamp":  l.timestamp.isoformat(),
                    "detail":     l.detail,
                }
                for l in logs
            ],
            "page": page,
        }


# ── System Stats ──────────────────────────────────────────────────────────────

@router.get("/stats")
async def system_stats(admin: CurrentUser = Depends(require_admin_role)):
    """System-wide statistics for the admin dashboard."""
    from sqlalchemy import select, func
    from alchemy.users.models import User, UserSession, AuditLog
    from datetime import timedelta, timezone

    async for db in _get_db():
        now = __import__('datetime').datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)

        total_users   = (await db.execute(select(func.count(User.id)))).scalar()
        active_users  = (await db.execute(
            select(func.count(User.id)).where(User.status == 'active')
        )).scalar()
        active_sessions = (await db.execute(
            select(func.count(UserSession.id))
            .where(UserSession.is_active == True)
            .where(UserSession.expires_at > now)
        )).scalar()
        failed_logins_24h = (await db.execute(
            select(func.count(AuditLog.id))
            .where(AuditLog.action == 'auth.login')
            .where(AuditLog.status == 'failure')
            .where(AuditLog.timestamp > day_ago)
        )).scalar()
        high_risk_events = (await db.execute(
            select(func.count(AuditLog.id))
            .where(AuditLog.risk_score >= 60)
            .where(AuditLog.timestamp > day_ago)
        )).scalar()

        return {
            "users":              {"total": total_users, "active": active_users},
            "sessions":           {"active": active_sessions},
            "security_24h":       {
                "failed_logins":  failed_logins_24h,
                "high_risk_events": high_risk_events,
            },
            "broker_connections": _get_broker_status(),
        }


def _get_broker_status() -> dict:
    """Quick check of exchange connectivity."""
    try:
        from alchemy.tokens.manager import get_token_manager
        return get_token_manager().status()
    except Exception:
        return {}
