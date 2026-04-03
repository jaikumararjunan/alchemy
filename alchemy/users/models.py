"""
alchemy.users.models
====================
User, Role, Permission, Session, and AuditLog models.
Uses SQLAlchemy ORM with TimescaleDB/PostgreSQL.

Security design:
  - Passwords stored as bcrypt hash (cost=12) ONLY — plaintext never stored
  - TOTP secret encrypted in DB using Fernet symmetric encryption
  - Sessions tracked server-side — logout invalidates token immediately
  - Account lockout after 5 consecutive failed login attempts
  - All security-relevant actions written to immutable audit log
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Text, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"   # Full platform control
    ADMIN       = "admin"         # User management + all features
    TRADER      = "trader"        # Full trading access
    ANALYST     = "analyst"       # Read + analytics, no execution
    VIEWER      = "viewer"        # Read-only dashboard


class UserStatus(str, Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    LOCKED   = "locked"      # Locked after too many failed attempts
    PENDING  = "pending"     # Email not yet verified
    BANNED   = "banned"      # Admin-banned


# Role → allowed permissions mapping
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.SUPER_ADMIN: {"*"},          # All permissions
    UserRole.ADMIN:       {
        "users:read", "users:write", "users:delete",
        "trading:read", "trading:write", "trading:execute",
        "admin:dashboard", "admin:audit",
        "tokens:read", "tokens:write",
        "workflows:read", "workflows:write",
        "signals:read", "signals:generate",
    },
    UserRole.TRADER: {
        "trading:read", "trading:write", "trading:execute",
        "tokens:read", "tokens:write",
        "workflows:read", "workflows:write",
        "signals:read", "signals:generate",
    },
    UserRole.ANALYST: {
        "trading:read", "signals:read",
        "tokens:read", "workflows:read",
    },
    UserRole.VIEWER: {
        "trading:read", "signals:read",
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


# ── SQLAlchemy Models ─────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email            = Column(String(255), unique=True, nullable=False, index=True)
    username         = Column(String(64),  unique=True, nullable=False, index=True)
    full_name        = Column(String(255), nullable=False)
    password_hash    = Column(String(255), nullable=False)   # bcrypt hash only

    role             = Column(String(32),  nullable=False, default=UserRole.TRADER.value)
    status           = Column(String(32),  nullable=False, default=UserStatus.PENDING.value)

    # 2FA
    totp_secret_enc  = Column(Text, nullable=True)           # Fernet-encrypted TOTP secret
    totp_enabled     = Column(Boolean, default=False)
    totp_backup_codes= Column(Text, nullable=True)           # Encrypted comma-separated backup codes
    totp_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Security tracking
    failed_login_count   = Column(Integer, default=0)
    locked_until         = Column(DateTime(timezone=True), nullable=True)
    last_login_at        = Column(DateTime(timezone=True), nullable=True)
    last_login_ip        = Column(String(45), nullable=True)   # IPv6 max length
    last_password_change = Column(DateTime(timezone=True), nullable=True)
    must_change_password = Column(Boolean, default=False)

    # Email verification
    email_verified       = Column(Boolean, default=False)
    email_verify_token   = Column(String(128), nullable=True, index=True)
    email_verify_expires = Column(DateTime(timezone=True), nullable=True)

    # Password reset
    reset_token          = Column(String(128), nullable=True, index=True)
    reset_token_expires  = Column(DateTime(timezone=True), nullable=True)

    # Profile
    avatar_url   = Column(String(512), nullable=True)
    timezone_str = Column(String(64),  default="Asia/Kolkata")
    preferred_exchange = Column(String(32), default="paper")

    # Timestamps
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions   = relationship("UserSession",   back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog",      back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_email_lower", "email"),
    )

    def is_locked(self) -> bool:
        if self.status == UserStatus.LOCKED.value:
            return True
        if self.locked_until and self.locked_until > datetime.now(timezone.utc):
            return True
        return False

    def increment_failed_logins(self, max_attempts: int = 5) -> bool:
        """Increment counter. Returns True if account should be locked."""
        self.failed_login_count = (self.failed_login_count or 0) + 1
        return self.failed_login_count >= max_attempts

    def reset_failed_logins(self) -> None:
        self.failed_login_count = 0
        self.locked_until = None

    def safe_dict(self) -> dict:
        """Return user dict safe for API responses — no secrets."""
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
    """Server-side session tracking — enables instant logout/revocation."""
    __tablename__ = "user_sessions"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    refresh_token_hash = Column(String(128), unique=True, nullable=False, index=True)
    access_jti    = Column(String(128), nullable=True, index=True)   # JWT ID for revocation
    ip_address    = Column(String(45), nullable=True)
    user_agent    = Column(String(512), nullable=True)
    device_type   = Column(String(64), nullable=True)   # mobile | desktop | api
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at    = Column(DateTime(timezone=True), nullable=False)
    last_used_at  = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="sessions")

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class AuditLog(Base):
    """Immutable audit trail for all security-sensitive actions."""
    __tablename__ = "audit_logs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action      = Column(String(128), nullable=False, index=True)   # e.g. "auth.login.success"
    resource    = Column(String(128), nullable=True)                # e.g. "order:WF-ABC123"
    ip_address  = Column(String(45),  nullable=True)
    user_agent  = Column(String(512), nullable=True)
    status      = Column(String(32),  nullable=False)               # success | failure | blocked
    detail      = Column(Text, nullable=True)                       # JSON extra data
    risk_score  = Column(Integer, default=0)                        # 0=low, 100=critical
    timestamp   = Column(DateTime(timezone=True),
                         default=lambda: datetime.now(timezone.utc), index=True)

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_action",         "action"),
    )
