"""alchemy.api.admin_routes v0.5.1"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from alchemy.auth.middleware import CurrentUser, require_role, get_current_user
from alchemy.users.models import UserRole, UserStatus

router = APIRouter(prefix="/admin", tags=["admin"])

async def get_db():
    from alchemy.api.database import get_session_factory
    async with get_session_factory()() as s: yield s

def _require_admin(): return require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)

class CreateUserRequest(BaseModel):
    email: EmailStr; username: str = Field(..., min_length=3, max_length=32)
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=12); role: str = UserRole.TRADER.value

class UpdateUserRequest(BaseModel):
    role: Optional[str]=None; status: Optional[str]=None; full_name: Optional[str]=None
    must_change_password: Optional[bool]=None; preferred_exchange: Optional[str]=None

@router.get("/users")
async def list_users(page:int=Query(1,ge=1), limit:int=Query(50,ge=1,le=200),
                      role:Optional[str]=None, status_filter:Optional[str]=Query(None,alias="status"),
                      search:Optional[str]=None, db: AsyncSession=Depends(get_db),
                      admin: CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select, func, or_
    from alchemy.users.models import User
    q = select(User)
    if role:          q = q.where(User.role == role)
    if status_filter: q = q.where(User.status == status_filter)
    if search:        q = q.where(or_(User.email.ilike(f"%{search}%"), User.username.ilike(f"%{search}%")))
    q = q.offset((page-1)*limit).limit(limit)
    result = await db.execute(q)
    users  = result.scalars().all()
    total  = (await db.execute(select(func.count(User.id)))).scalar()
    return {"users": [u.safe_dict() for u in users], "total": total, "page": page, "pages": (total+limit-1)//limit}

@router.get("/users/{user_id}")
async def get_user(user_id:str, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select; from alchemy.users.models import User; from uuid import UUID
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format")
    result = await db.execute(select(User).where(User.id==uid))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(404,"User not found")
    return user.safe_dict()

@router.post("/users", status_code=201)
async def create_user(req:CreateUserRequest, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from alchemy.auth.service import AuthService, AuthError
    try:
        svc=AuthService(); user=await svc.signup(db,email=req.email,username=req.username,full_name=req.full_name,password=req.password,role=req.role)
        user.status="active"; user.email_verified=True; await db.commit()
        return {"user":user.safe_dict(),"message":"User created"}
    except AuthError as e: raise HTTPException(400,str(e))

@router.patch("/users/{user_id}")
async def update_user(user_id:str, req:UpdateUserRequest, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select; from alchemy.users.models import User; from uuid import UUID
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format")
    result = await db.execute(select(User).where(User.id==uid))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(404,"Not found")
    if req.role:
        valid_roles = {r.value for r in UserRole}
        if req.role not in valid_roles:
            raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")
        user.role=req.role
    if req.status:
        valid_statuses = {s.value for s in UserStatus}
        if req.status not in valid_statuses:
            raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}")
        user.status=req.status
    if req.full_name: user.full_name=req.full_name
    if req.must_change_password is not None: user.must_change_password=req.must_change_password
    await db.commit(); return {"user":user.safe_dict()}

@router.post("/users/{user_id}/ban")
async def ban_user(user_id:str, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select,update; from alchemy.users.models import User,UserSession; from uuid import UUID
    if user_id==admin.user_id: raise HTTPException(400,"Cannot ban yourself")
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format")
    result = await db.execute(select(User).where(User.id==uid))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(404,"Not found")
    user.status="banned"
    await db.execute(update(UserSession).where(UserSession.user_id==uid).values(is_active=False))
    await db.commit(); return {"message":f"{user.email} banned"}

@router.post("/users/{user_id}/unlock")
async def unlock_user(user_id:str, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select; from alchemy.users.models import User; from uuid import UUID
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format")
    result = await db.execute(select(User).where(User.id==uid))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(404,"Not found")
    user.status="active"; user.failed_login_count=0; user.locked_until=None
    await db.commit(); return {"message":f"{user.email} unlocked"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db),
                      admin: CurrentUser = Depends(_require_admin())):
    """Permanently delete a user and all their data."""
    from sqlalchemy import select, delete as sql_delete
    from alchemy.users.models import User, UserSession, AuditLog
    from uuid import UUID
    import sqlite3, os, json

    if user_id == admin.user_id:
        raise HTTPException(400, "Cannot delete your own account")

    uid = UUID(user_id)
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    email = user.email
    # Prevent deleting super_admin
    if user.role == "super_admin":
        raise HTTPException(403, "Cannot delete super_admin accounts")

    # Delete sessions and audit logs first (FK constraints)
    await db.execute(sql_delete(UserSession).where(UserSession.user_id == uid))
    await db.execute(sql_delete(AuditLog).where(AuditLog.user_id == uid))
    await db.delete(user)
    await db.commit()

    # Also delete exchange tokens from SQLite (stored separately)
    try:
        from alchemy.api.token_routes import _get_db_path
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM exchange_tokens WHERE user_id=?", (user_id,))
        conn.commit(); conn.close()
    except Exception:
        pass

    import structlog
    structlog.get_logger().info("admin.user_deleted", email=email, by=admin.email)
    return {"message": f"User {email} permanently deleted", "deleted": True}


@router.patch("/users/{user_id}/subscription")
async def update_subscription(user_id: str, plan: str,
                               db: AsyncSession = Depends(get_db),
                               admin: CurrentUser = Depends(_require_admin())):
    """Change a user's subscription plan."""
    from sqlalchemy import select
    from alchemy.users.models import User
    from uuid import UUID
    valid = {"free", "pro", "team", "enterprise"}
    if plan not in valid:
        raise HTTPException(400, f"Plan must be one of: {', '.join(valid)}")
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user: raise HTTPException(404, "User not found")
    user.subscription = plan
    await db.commit()
    return {"message": f"Subscription updated to {plan}", "user": user.safe_dict()}


@router.delete("/users/{user_id}/sessions")
async def revoke_sessions(user_id:str, db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from alchemy.auth.service import AuthService
    count=await AuthService().logout_all(db,user_id); await db.commit()
    return {"count":count}

@router.get("/audit-logs")
async def get_audit_logs(page:int=Query(1,ge=1), limit:int=Query(100,ge=1,le=500),
                          user_id:Optional[str]=None, action:Optional[str]=None,
                          min_risk:int=Query(0,ge=0,le=100),
                          db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select, desc; from alchemy.users.models import AuditLog; from uuid import UUID
    q=select(AuditLog).order_by(desc(AuditLog.timestamp))
    if user_id:
        try:
            q=q.where(AuditLog.user_id==UUID(user_id))
        except ValueError:
            raise HTTPException(400, "Invalid user_id format")
    if action:  q=q.where(AuditLog.action.ilike(f"%{action}%"))
    if min_risk:q=q.where(AuditLog.risk_score>=min_risk)
    q=q.offset((page-1)*limit).limit(limit)
    result=await db.execute(q); logs=result.scalars().all()
    return {"logs":[{"id":str(l.id),"user_id":str(l.user_id) if l.user_id else None,"action":l.action,
                     "status":l.status,"ip_address":l.ip_address,"risk_score":l.risk_score,
                     "timestamp":l.timestamp.isoformat(),"detail":l.detail} for l in logs],"page":page}

@router.get("/stats")
async def system_stats(db:AsyncSession=Depends(get_db), admin:CurrentUser=Depends(_require_admin())):
    from sqlalchemy import select, func
    from alchemy.users.models import User, UserSession, AuditLog
    from datetime import datetime,timezone,timedelta
    now=datetime.now(timezone.utc); day_ago=now-timedelta(hours=24)
    total=(await db.execute(select(func.count(User.id)))).scalar()
    active=(await db.execute(select(func.count(User.id)).where(User.status=="active"))).scalar()
    sessions=(await db.execute(select(func.count(UserSession.id)).where(UserSession.is_active==True).where(UserSession.expires_at>now))).scalar()
    failed=(await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action=="auth.login").where(AuditLog.status=="failure").where(AuditLog.timestamp>day_ago))).scalar()
    risk_evts=(await db.execute(select(func.count(AuditLog.id)).where(AuditLog.risk_score>=60).where(AuditLog.timestamp>day_ago))).scalar()
    try:
        from alchemy.tokens.manager import get_token_manager; broker_status=get_token_manager().status()
    except Exception: broker_status={}
    return {"users":{"total":total,"active":active},"sessions":{"active":sessions},
            "security_24h":{"failed_logins":failed,"high_risk_events":risk_evts},"broker_connections":broker_status}
