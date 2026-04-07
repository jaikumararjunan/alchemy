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
from urllib.parse import urlsplit

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

log = structlog.get_logger(__name__)


def _extract_sqlite_path(db_url: str) -> str:
    """Extract SQLite file path from SQLAlchemy URL without mangling relative paths."""
    parsed = urlsplit(db_url)
    # sqlite:///./data/alchemy.db   -> path='/./data/alchemy.db' (relative)
    # sqlite:////data/alchemy.db    -> path='//data/alchemy.db' (absolute)
    raw_path = parsed.path or ""
    if raw_path.startswith("//"):
        return raw_path[1:]
    if raw_path.startswith("/"):
        return raw_path[1:]
    return raw_path


def _resolve_sqlite_file_path(db_url: str) -> pathlib.Path:
    db_path_str = _extract_sqlite_path(db_url)
    db_path = pathlib.Path(db_path_str)
    if not db_path.is_absolute():
        db_path = pathlib.Path.cwd() / db_path
    return db_path

# Create data directory if it doesn't exist
import pathlib
_db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
if "sqlite" in _db_url:
    _resolved_db_path = _resolve_sqlite_file_path(_db_url)
    if str(_resolved_db_path) and not str(_resolved_db_path).startswith(":"):
        _parent = _resolved_db_path.parent
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
    """Create all tables and apply safe migrations for missing columns."""
    from alchemy.users.models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("db.tables_created")

    # Safe migrations: add missing columns without breaking existing data
    if "sqlite" in DATABASE_URL:
        import sqlite3
        db_path = str(_resolve_sqlite_file_path(DATABASE_URL))

        try:
            conn2 = sqlite3.connect(db_path)
            # audit_logs: add 'timestamp' if missing (was named 'created_at' in old schema)
            cols = [r[1] for r in conn2.execute("PRAGMA table_info(audit_logs)").fetchall()]
            if "timestamp" not in cols:
                if "created_at" in cols:
                    # rename approach: add timestamp, copy data, keep both
                    conn2.execute("ALTER TABLE audit_logs ADD COLUMN timestamp DATETIME")
                    conn2.execute("UPDATE audit_logs SET timestamp=created_at WHERE timestamp IS NULL")
                else:
                    conn2.execute("ALTER TABLE audit_logs ADD COLUMN timestamp DATETIME DEFAULT (datetime('now'))")
                conn2.commit()
                log.info("db.migration.audit_logs_timestamp_added")

            # users: add subscription if missing
            ucols = [r[1] for r in conn2.execute("PRAGMA table_info(users)").fetchall()]
            if "subscription" not in ucols:
                conn2.execute("ALTER TABLE users ADD COLUMN subscription TEXT DEFAULT 'free'")
                conn2.execute("UPDATE users SET subscription='enterprise' WHERE role IN ('super_admin','admin')")
                conn2.commit()
                log.info("db.migration.users_subscription_added")

            # exchange_tokens: add last_test_msg if missing
            etcols = [r[1] for r in conn2.execute("PRAGMA table_info(exchange_tokens)").fetchall()]
            for col, typ in [("last_test_msg","TEXT"), ("last_tested","TEXT")]:
                if col not in etcols:
                    conn2.execute(f"ALTER TABLE exchange_tokens ADD COLUMN {col} {typ}")
            conn2.commit()
            conn2.close()
            log.info("db.migrations_complete")
        except Exception as e:
            log.warning("db.migration_failed", error=str(e))


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
