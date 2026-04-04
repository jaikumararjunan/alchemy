"""
alchemy.api.database
====================
SQLAlchemy async session factory.

In production: configure DATABASE_URL env var pointing to PostgreSQL/TimescaleDB.
For development: uses SQLite async as fallback.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

log = structlog.get_logger(__name__)

# Create data directory if it doesn't exist
import pathlib
_db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
if "sqlite" in _db_url:
    import re as _re
    # Handle both relative (sqlite:///./path) and absolute (sqlite:////abs/path)
    _db_path = _re.sub(r"^sqlite(\+aiosqlite)?:///", "", _db_url)
    # If it started with 4 slashes, path is absolute — add the slash back
    if _db_url.count("/") >= 4 and not _db_path.startswith("/"):
        _db_path = "/" + _db_path
    if _db_path and not _db_path.startswith(":"):
        _parent = pathlib.Path(_db_path).parent
        _parent.mkdir(parents=True, exist_ok=True)
        # Make directory writable
        try:
            _parent.chmod(0o777)
        except Exception:
            pass

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./alchemy_dev.db"  # Dev fallback
).replace("postgresql://", "postgresql+asyncpg://")

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        kwargs = {"echo": os.environ.get("DB_ECHO", "false") == "true"}
        if "sqlite" not in DATABASE_URL:
            kwargs["poolclass"] = NullPool
        _engine = create_async_engine(DATABASE_URL, **kwargs)
        log.info("db.engine_created", url=DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "sqlite")
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async SQLAlchemy session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables (development only — use Alembic migrations in production)."""
    from alchemy.users.models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("db.tables_created")


async def create_initial_admin(email: str, password: str) -> None:
    """Bootstrap the first super admin account."""
    from alchemy.auth.service import AuthService
    from alchemy.users.models import UserRole, UserStatus

    async with get_session_factory()() as db:
        svc = AuthService()
        try:
            user = await svc.signup(
                db, email=email, username="superadmin",
                full_name="Super Admin", password=password,
                role=UserRole.SUPER_ADMIN.value,
            )
            user.status         = UserStatus.ACTIVE.value
            user.email_verified = True
            await db.commit()
            log.info("db.admin_created", email=email)
        except Exception as e:
            log.warning("db.admin_create_failed", error=str(e))
