"""
alchemy.users.models
User, UserSession, AuditLog — SQLAlchemy ORM + RBAC.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator, CHAR
import uuid as _uuid_mod

Base = declarative_base()


# ── UUID that works with both SQLite and PostgreSQL ───────────────────────────
class GUID(TypeDecorator):
    """Platform-independent GUID. Stores as CHAR(36) in SQLite, UUID in PG."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None: return None
        if dialect.name == 'postgresql': return str(value)
        if isinstance(value, _uuid_mod.UUID): return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None: return None
        if isinstance(value, _uuid_mod.UUID): return value
        return _uuid_mod.UUID(str(value))


# ── UTC-aware datetime helper ─────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _make_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN       = "admin"
    TRADER      = "trader"
    ANALYST     = "analyst"
    VIEWER      = "viewer"


class UserStatus(str, Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    LOCKED   = "locked"
    PENDING  = "pending"
    BANNED   = "banned"


ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.SUPER_ADMIN: {"*"},
    UserRole.ADMIN: {
        "users:read","users:write","users:delete",
        "trading:read","trading:write","trading:execute",
        "admin:dashboard","admin:audit",
        "tokens:read","tokens:write",
        "workflows:read","workflows:write",
        "signals:read","signals:generate",
    },
    UserRole.TRADER: {
        "trading:read","trading:write","trading:execute",
        "tokens:read","tokens:write",
        "workflows:read","workflows:write",
        "signals:read","signals:generate",
    },
    UserRole.ANALYST: {
        "trading:read","signals:read",
        "tokens:read","workflows:read",
    },
    UserRole.VIEWER: {
        "trading:read","signals:read",
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


class User(Base):
    __tablename__ = "users"

    id               = Column(GUID(), primary_key=True, default=_uuid_mod.uuid4)
    email            = Column(String(255), unique=True, nullable=False, index=True)
    username         = Column(String(64),  unique=True, nullable=False, index=True)
    full_name        = Column(String(255), nullable=False)
    password_hash    = Column(String(255), nullable=False)

    role             = Column(String(32),  nullable=False, default=UserRole.TRADER.value)
    status           = Column(String(32),  nullable=False, default=UserStatus.PENDING.value)

    totp_secret_enc  = Column(Text,    nullable=True)
    totp_enabled     = Column(Boolean, default=False)
    totp_backup_codes= Column(Text,    nullable=True)
    totp_verified_at = Column(DateTime(timezone=True), nullable=True)

    failed_login_count   = Column(Integer, default=0)
    locked_until         = Column(DateTime(timezone=True), nullable=True)
    last_login_at        = Column(DateTime(timezone=True), nullable=True)
    last_login_ip        = Column(String(45), nullable=True)
    last_password_change = Column(DateTime(timezone=True), nullable=True)
    must_change_password = Column(Boolean, default=False)

    email_verified       = Column(Boolean, default=False)
    email_verify_token   = Column(String(128), nullable=True, index=True)
    email_verify_expires = Column(DateTime(timezone=True), nullable=True)

    reset_token          = Column(String(128), nullable=True, index=True)
    reset_token_expires  = Column(DateTime(timezone=True), nullable=True)

    avatar_url        = Column(String(512), nullable=True)
    timezone_str      = Column(String(64),  default="Asia/Kolkata")
    preferred_exchange = Column(String(32), default="paper")

    created_at = Column(DateTime(timezone=True), default=_now_utc)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc)

    sessions   = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog",    back_populates="user", cascade="all, delete-orphan")

    def is_locked(self) -> bool:
        if self.status == UserStatus.LOCKED.value:
            return True
        if self.locked_until:
            lu = _make_utc(self.locked_until)
            return lu > _now_utc()
        return False

    def increment_failed_logins(self, max_attempts: int = 5) -> bool:
        self.failed_login_count = (self.failed_login_count or 0) + 1
        return self.failed_login_count >= max_attempts

    def reset_failed_logins(self) -> None:
        self.failed_login_count = 0
        self.locked_until = None

    def safe_dict(self) -> dict:
        return {
            "id":            str(self.id),
            "email":         self.email,
            "username":      self.username,
            "full_name":     self.full_name,
            "role":          self.role,
            "status":        self.status,
            "totp_enabled":  self.totp_enabled,
            "email_verified":self.email_verified,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "preferred_exchange": self.preferred_exchange,
            "timezone_str":  self.timezone_str,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }


class UserSession(Base):
    __tablename__ = "user_sessions"

    id                 = Column(GUID(), primary_key=True, default=_uuid_mod.uuid4)
    user_id            = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"))
    refresh_token_hash = Column(String(128), unique=True, nullable=False, index=True)
    access_jti         = Column(String(128), nullable=True, index=True)
    ip_address         = Column(String(45),  nullable=True)
    user_agent         = Column(String(512), nullable=True)
    device_type        = Column(String(64),  nullable=True)
    is_active          = Column(Boolean, default=True)
    created_at         = Column(DateTime(timezone=True), default=_now_utc)
    expires_at         = Column(DateTime(timezone=True), nullable=False)
    last_used_at       = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="sessions")

    @property
    def is_expired(self) -> bool:
        # Always compare timezone-aware datetimes
        exp = _make_utc(self.expires_at)
        return _now_utc() >= exp


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id         = Column(GUID(), primary_key=True, default=_uuid_mod.uuid4)
    user_id    = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action     = Column(String(128), nullable=False, index=True)
    resource   = Column(String(128), nullable=True)
    ip_address = Column(String(45),  nullable=True)
    user_agent = Column(String(512), nullable=True)
    status     = Column(String(32),  nullable=False)
    detail     = Column(Text, nullable=True)
    risk_score = Column(Integer, default=0)
    timestamp  = Column(DateTime(timezone=True), default=_now_utc, index=True)

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_action",         "action"),
    )
