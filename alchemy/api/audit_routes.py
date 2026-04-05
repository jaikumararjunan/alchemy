"""
alchemy.api.audit_routes
=========================
Audit log and security event API endpoints.
Accessible by admin and super_admin roles only.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from alchemy.auth.middleware import CurrentUser, require_role, get_current_user
from alchemy.users.models import UserRole
import structlog

log    = structlog.get_logger(__name__)
router = APIRouter(prefix="/audit", tags=["audit"])


async def get_db():
    from alchemy.api.database import get_session_factory
    async with get_session_factory()() as s:
        yield s


def _admin():
    return require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("/logs")
async def get_audit_logs(
    page:     int          = Query(1, ge=1),
    limit:    int          = Query(50, ge=1, le=200),
    user_id:  Optional[str] = None,
    action:   Optional[str] = None,
    status:   Optional[str] = None,
    min_risk: int          = Query(0, ge=0, le=100),
    db: AsyncSession       = Depends(get_db),
    admin: CurrentUser     = Depends(_admin()),
):
    """Get paginated audit logs with filters."""
    from sqlalchemy import select, desc
    from alchemy.users.models import AuditLog, User
    from uuid import UUID

    q = select(AuditLog, User.email, User.username).outerjoin(
        User, AuditLog.user_id == User.id
    ).order_by(desc(AuditLog.timestamp))

    if user_id:   q = q.where(AuditLog.user_id == UUID(user_id))
    if action:    q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if status:    q = q.where(AuditLog.status == status)
    if min_risk:  q = q.where(AuditLog.risk_score >= min_risk)

    total_q = select(__import__("sqlalchemy").func.count(AuditLog.id))
    if user_id:  total_q = total_q.where(AuditLog.user_id == UUID(user_id))
    if action:   total_q = total_q.where(AuditLog.action.ilike(f"%{action}%"))
    total = (await db.execute(total_q)).scalar()

    q = q.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(q)).all()

    return {
        "logs": [{
            "id":         str(r.AuditLog.id),
            "user_id":    str(r.AuditLog.user_id) if r.AuditLog.user_id else None,
            "user_email": r.email,
            "username":   r.username,
            "action":     r.AuditLog.action,
            "resource":   r.AuditLog.resource,
            "status":     r.AuditLog.status,
            "ip_address": r.AuditLog.ip_address,
            "risk_score": r.AuditLog.risk_score,
            "detail":     r.AuditLog.detail,
            "timestamp":  r.AuditLog.timestamp.isoformat() if r.AuditLog.timestamp else None,
        } for r in rows],
        "total": total,
        "page":  page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/security-events")
async def get_security_events(
    hours:  int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    admin: CurrentUser = Depends(_admin()),
):
    """Get security-relevant events from last N hours."""
    from sqlalchemy import select, func
    from alchemy.users.models import AuditLog
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    security_actions = [
        "auth.login", "auth.signup", "auth.logout",
        "auth.password_change", "auth.2fa_enable", "auth.2fa_disable",
        "token.register", "token.delete", "admin.user_delete",
        "admin.user_ban", "risk.emergency_stop",
    ]

    q = select(AuditLog).where(
        AuditLog.timestamp >= since,
        AuditLog.action.in_(security_actions)
    ).order_by(AuditLog.timestamp.desc()).limit(500)

    rows = (await db.execute(q)).scalars().all()

    # Aggregate stats
    failed_logins = sum(1 for r in rows if r.action == "auth.login" and r.status == "failure")
    high_risk     = sum(1 for r in rows if (r.risk_score or 0) >= 60)
    unique_ips    = len(set(r.ip_address for r in rows if r.ip_address))

    return {
        "period_hours":  hours,
        "summary": {
            "total_events":   len(rows),
            "failed_logins":  failed_logins,
            "high_risk":      high_risk,
            "unique_ips":     unique_ips,
        },
        "events": [{
            "id":         str(r.id),
            "action":     r.action,
            "status":     r.status,
            "ip_address": r.ip_address,
            "risk_score": r.risk_score,
            "timestamp":  r.timestamp.isoformat() if r.timestamp else None,
        } for r in rows[:100]],  # Return top 100 only
    }


@router.get("/user-activity/{user_id}")
async def get_user_activity(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: CurrentUser = Depends(_admin()),
):
    """Get complete activity history for a specific user."""
    from sqlalchemy import select, desc
    from alchemy.users.models import AuditLog, User
    from uuid import UUID

    uid = UUID(user_id)
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")

    logs = (await db.execute(
        select(AuditLog).where(AuditLog.user_id == uid)
        .order_by(desc(AuditLog.timestamp)).limit(200)
    )).scalars().all()

    return {
        "user":    user.safe_dict(),
        "activity": [{
            "action":     r.action,
            "status":     r.status,
            "ip_address": r.ip_address,
            "risk_score": r.risk_score,
            "detail":     r.detail,
            "timestamp":  r.timestamp.isoformat() if r.timestamp else None,
        } for r in logs],
    }
