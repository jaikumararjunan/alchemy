"""
alchemy.auth.service
====================
Authentication business logic: signup, login, 2FA, refresh, logout.

All operations write to the AuditLog for compliance.
Failed logins trigger account lockout after 5 attempts.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog

from alchemy.auth.security import (
    PasswordPolicy, TOTPManager, SecretEncryptor,
    create_access_token, create_refresh_token, hash_password,
    verify_password, hash_refresh_token, get_encryptor,
    generate_email_verify_token, generate_password_reset_token,
)
from alchemy.users.models import (
    User, UserRole, UserSession, AuditLog, UserStatus,
)

log = structlog.get_logger(__name__)

MAX_FAILED_LOGINS  = 5
LOCKOUT_DURATION_M = 30   # minutes


class AuthError(Exception):
    def __init__(self, message: str, code: str = "auth_error"):
        super().__init__(message)
        self.code = code


class AuthService:
    """
    Stateless auth service — receives a DB session per call.
    All methods accept `db` (SQLAlchemy AsyncSession).
    """

    # ── Signup ────────────────────────────────────────────────────────────────

    async def signup(
        self,
        db,
        email: str,
        username: str,
        full_name: str,
        password: str,
        role: str = UserRole.TRADER.value,
    ) -> User:
        """
        Register a new user.

        - Validates password policy
        - Checks email + username uniqueness
        - Hashes password with bcrypt (cost=12)
        - Generates email verification token
        - Writes AUDIT: auth.signup
        """
        # Password policy
        errors = PasswordPolicy.validate(password)
        if errors:
            raise AuthError("; ".join(errors), "weak_password")

        # Uniqueness check
        existing_email = await self._get_user_by_email(db, email.lower())
        if existing_email:
            raise AuthError("Email already registered", "email_taken")

        existing_username = await self._get_user_by_username(db, username.lower())
        if existing_username:
            raise AuthError("Username already taken", "username_taken")

        user = User(
            id=uuid4(),
            email=email.lower().strip(),
            username=username.lower().strip(),
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
            status=UserStatus.PENDING.value,
            email_verify_token=generate_email_verify_token(),
            email_verify_expires=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(user)
        await self._log(db, user_id=str(user.id),
                        action="auth.signup", status="success",
                        detail={"email": email, "role": role})
        await db.flush()

        log.info("auth.signup", user_id=str(user.id), email=email)
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(
        self,
        db,
        email: str,
        password: str,
        ip_address: str,
        user_agent: str,
        totp_code: Optional[str] = None,
    ) -> dict:
        """
        Authenticate user with email + password (+ optional TOTP).

        Returns:
            {
                access_token: str,
                refresh_token: str,   # Store in httpOnly cookie
                requires_2fa: bool,   # True if 2FA setup but code not provided
                user: dict,
            }
        """
        user = await self._get_user_by_email(db, email.lower())

        # Always run through the password hash check to prevent timing attacks
        # (even if user not found — compare against dummy hash)
        dummy_hash = "$2b$12$dummy.hash.to.prevent.timing.attacks.XXXXXXXXXXXXXX"
        candidate_hash = user.password_hash if user else dummy_hash

        password_ok = verify_password(password, candidate_hash)

        if not user:
            raise AuthError("Invalid email or password", "invalid_credentials")

        # Account status checks
        if user.status == UserStatus.BANNED.value:
            await self._log(db, user_id=str(user.id), action="auth.login",
                            status="blocked", ip_address=ip_address,
                            detail={"reason": "account_banned"})
            raise AuthError("Account has been suspended", "account_banned")

        if user.is_locked():
            await self._log(db, user_id=str(user.id), action="auth.login",
                            status="blocked", ip_address=ip_address,
                            detail={"reason": "account_locked"})
            raise AuthError(
                f"Account locked. Too many failed attempts. "
                f"Try again after {LOCKOUT_DURATION_M} minutes.",
                "account_locked"
            )

        # Pending users: auto-activate (OTP email verification disabled)
        if user.status == UserStatus.PENDING.value:
            user.status = UserStatus.ACTIVE.value
            user.email_verified = True
            await self._log(db, user_id=str(user.id), action="auth.login",
                            status="success", ip_address=ip_address,
                            detail={"reason": "pending_auto_activated"})
            log.info("auth.pending_auto_activated", user_id=str(user.id))

        if not password_ok:
            should_lock = user.increment_failed_logins(MAX_FAILED_LOGINS)
            if should_lock:
                user.status = UserStatus.LOCKED.value
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_M)
                await self._log(db, user_id=str(user.id), action="auth.login",
                                status="failure", ip_address=ip_address,
                                detail={"reason": "account_locked_now", "attempts": user.failed_login_count},
                                risk_score=80)
            else:
                await self._log(db, user_id=str(user.id), action="auth.login",
                                status="failure", ip_address=ip_address,
                                detail={"reason": "wrong_password", "attempts": user.failed_login_count},
                                risk_score=40)
            raise AuthError("Invalid email or password", "invalid_credentials")

        # 2FA check
        if user.totp_enabled:
            if not totp_code:
                # Signal frontend to show 2FA input
                return {"requires_2fa": True, "user_id": str(user.id)}

            enc = get_encryptor()
            secret = enc.decrypt(user.totp_secret_enc)

            # Check backup codes
            backup_codes = []
            if user.totp_backup_codes:
                backup_codes = json.loads(enc.decrypt(user.totp_backup_codes))

            if not TOTPManager.verify(secret, totp_code, backup_codes):
                await self._log(db, user_id=str(user.id), action="auth.2fa",
                                status="failure", ip_address=ip_address,
                                detail={"reason": "invalid_totp"}, risk_score=60)
                raise AuthError("Invalid 2FA code", "invalid_totp")

            # Remove used backup code (timing-safe lookup)
            import secrets as _secrets
            matched = next(
                (c for c in backup_codes if _secrets.compare_digest(c.upper(), totp_code.upper())),
                None,
            )
            if matched:
                backup_codes.remove(matched)
                user.totp_backup_codes = enc.encrypt(json.dumps(backup_codes))

        # Success — reset failed attempts, create session
        user.reset_failed_logins()
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip_address

        raw_refresh, hashed_refresh = create_refresh_token()
        access_jti = f"jti_{uuid4().hex[:16]}"
        access_token = create_access_token(
            str(user.id), user.email, user.role, jti=access_jti
        )

        session = UserSession(
            id=uuid4(),
            user_id=user.id,
            refresh_token_hash=hashed_refresh,
            access_jti=access_jti,
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(session)

        await self._log(db, user_id=str(user.id), action="auth.login",
                        status="success", ip_address=ip_address,
                        detail={"session_id": str(session.id)})
        await db.flush()

        log.info("auth.login_success", user_id=str(user.id), ip=ip_address)
        return {
            "access_token":  access_token,
            "refresh_token": raw_refresh,
            "requires_2fa":  False,
            "user":          user.safe_dict(),
        }

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refresh_tokens(self, db, raw_refresh_token: str) -> dict:
        """Exchange a valid refresh token for a new access + refresh token pair."""
        hashed = hash_refresh_token(raw_refresh_token)
        session = await self._get_session_by_refresh(db, hashed)

        if not session or not session.is_active or session.is_expired:
            raise AuthError("Invalid or expired refresh token", "invalid_refresh")

        user = session.user
        if user.status != UserStatus.ACTIVE.value:
            raise AuthError("Account is not active", "account_inactive")

        # Rotate refresh token (prevent replay attacks)
        raw_new, hashed_new = create_refresh_token()
        new_jti = f"jti_{uuid4().hex[:16]}"
        new_access = create_access_token(str(user.id), user.email, user.role, jti=new_jti)

        session.refresh_token_hash = hashed_new
        session.access_jti = new_jti
        session.last_used_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        await db.flush()
        return {"access_token": new_access, "refresh_token": raw_new}

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, db, raw_refresh_token: str, user_id: str) -> None:
        """Invalidate session server-side — token is immediately revoked."""
        hashed = hash_refresh_token(raw_refresh_token)
        session = await self._get_session_by_refresh(db, hashed)
        if session:
            session.is_active = False
        await self._log(db, user_id=user_id, action="auth.logout", status="success")
        await db.flush()

    async def logout_all(self, db, user_id: str) -> int:
        """Revoke ALL sessions for a user (force re-login on all devices)."""
        from sqlalchemy import update
        result = await db.execute(
            update(UserSession)
            .where(UserSession.user_id == UUID(user_id))
            .values(is_active=False)
        )
        await self._log(db, user_id=user_id, action="auth.logout_all", status="success",
                        detail={"sessions_revoked": result.rowcount})
        return result.rowcount

    # ── 2FA Setup ─────────────────────────────────────────────────────────────

    async def setup_2fa(self, db, user_id: str) -> dict:
        """
        Initiate 2FA setup. Returns QR code + backup codes.
        2FA is NOT activated until verify_2fa() is called.
        """
        user = await self._get_user_by_id(db, user_id)
        enc    = get_encryptor()
        secret = TOTPManager.generate_secret()
        backup_codes = TOTPManager.generate_backup_codes()

        user.totp_secret_enc  = enc.encrypt(secret)
        user.totp_backup_codes = enc.encrypt(json.dumps(backup_codes))
        # Don't enable yet — require verification first

        qr_data_url = TOTPManager.generate_qr_code(secret, user.email)
        await db.flush()

        return {
            "qr_code":     qr_data_url,
            "secret":      secret,       # Show once for manual entry
            "backup_codes":backup_codes,
        }

    async def verify_and_enable_2fa(self, db, user_id: str, totp_code: str) -> bool:
        """Verify first TOTP code and activate 2FA."""
        user = await self._get_user_by_id(db, user_id)
        if not user.totp_secret_enc:
            raise AuthError("2FA not initialized. Call setup_2fa first.", "2fa_not_setup")

        enc    = get_encryptor()
        secret = enc.decrypt(user.totp_secret_enc)

        if not TOTPManager.verify(secret, totp_code):
            await self._log(db, user_id=user_id, action="auth.2fa_enable",
                            status="failure", risk_score=30)
            raise AuthError("Invalid TOTP code — check your authenticator app", "invalid_totp")

        user.totp_enabled    = True
        user.totp_verified_at = datetime.now(timezone.utc)
        await self._log(db, user_id=user_id, action="auth.2fa_enable", status="success")
        await db.flush()
        return True

    async def disable_2fa(self, db, user_id: str, password: str) -> bool:
        """Disable 2FA — requires password re-confirmation."""
        user = await self._get_user_by_id(db, user_id)
        if not verify_password(password, user.password_hash):
            await self._log(db, user_id=user_id, action="auth.2fa_disable",
                            status="failure", risk_score=70)
            raise AuthError("Password incorrect", "invalid_password")

        user.totp_enabled     = False
        user.totp_secret_enc  = None
        user.totp_backup_codes = None
        await self._log(db, user_id=user_id, action="auth.2fa_disable", status="success",
                        risk_score=50)
        await db.flush()
        return True

    # ── Password Reset ────────────────────────────────────────────────────────

    async def request_password_reset(self, db, email: str) -> Optional[str]:
        """Returns reset token (send via email). Returns None if user not found (no disclosure)."""
        user = await self._get_user_by_email(db, email.lower())
        if not user:
            return None   # Silent — don't reveal if email exists

        token = generate_password_reset_token()
        user.reset_token         = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await self._log(db, user_id=str(user.id), action="auth.password_reset_request", status="success")
        await db.flush()
        return token

    async def reset_password(self, db, token: str, new_password: str) -> bool:
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.reset_token == token)
        )
        user = result.scalar_one_or_none()

        if not user or not user.reset_token_expires:
            raise AuthError("Invalid or expired reset token", "invalid_token")
        if user.reset_token_expires < datetime.now(timezone.utc):
            raise AuthError("Reset token has expired", "token_expired")

        errors = PasswordPolicy.validate(new_password)
        if errors:
            raise AuthError("; ".join(errors), "weak_password")

        user.password_hash        = hash_password(new_password)
        user.reset_token          = None
        user.reset_token_expires  = None
        user.last_password_change = datetime.now(timezone.utc)
        # Revoke all sessions on password reset
        await self.logout_all(db, str(user.id))
        await self._log(db, user_id=str(user.id), action="auth.password_reset", status="success")
        await db.flush()
        return True

    # ── DB Helpers (simplified — replace with async SQLAlchemy in production) ─

    async def _get_user_by_email(self, db, email: str) -> Optional[User]:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_user_by_username(self, db, username: str) -> Optional[User]:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, db, user_id: str) -> User:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            raise AuthError("User not found", "not_found")
        return user

    async def _get_session_by_refresh(self, db, hashed: str) -> Optional[UserSession]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(UserSession)
            .options(selectinload(UserSession.user))
            .where(UserSession.refresh_token_hash == hashed)
        )
        return result.scalar_one_or_none()

    async def _log(self, db, *, user_id: Optional[str] = None, action: str,
                   status: str, ip_address: Optional[str] = None,
                   detail: Optional[dict] = None, risk_score: int = 0) -> None:
        import json as json_lib
        entry = AuditLog(
            id=uuid4(),
            user_id=UUID(user_id) if user_id else None,
            action=action,
            status=status,
            ip_address=ip_address,
            detail=json_lib.dumps(detail) if detail else None,
            risk_score=risk_score,
        )
        db.add(entry)
