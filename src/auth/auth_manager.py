"""
Authentication and 2FA management for Alchemy API.

Handles JWT tokens, bcrypt password hashing, and TOTP-based two-factor
authentication (RFC 6238 — compatible with Google Authenticator / Authy).

Auth flow:
  1. POST /api/auth/login         → verify username + password
                                    → return short-lived temp_token (5 min)
  2. POST /api/auth/verify-2fa   → verify TOTP code + temp_token
                                    → return full access_token (24 h JWT)
  3. All protected endpoints      → Authorization: Bearer <access_token>
"""

import base64
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

import pyotp
import qrcode
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.utils.logger import get_logger

logger = get_logger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
TEMP_TOKEN_EXPIRE_MINUTES = 5  # Only valid for the 2FA verification step

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthManager:
    """
    Core authentication manager.

    Requires:
      - secret_key   : random 32+ byte hex string for JWT signing
      - username     : dashboard admin username
      - password_hash: bcrypt hash of the admin password
      - totp_secret  : base32 TOTP secret (RFC 4648)
    """

    def __init__(
        self,
        secret_key: str,
        username: str,
        password_hash: str,
        totp_secret: str,
    ) -> None:
        self.secret_key = secret_key
        self.username = username
        self.password_hash = password_hash
        self.totp_secret = totp_secret
        self.totp = pyotp.TOTP(totp_secret)
        logger.info("AuthManager initialised (2FA enabled)")

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Return a bcrypt hash suitable for AUTH_PASSWORD_HASH env var."""
        return pwd_context.hash(plain_password)

    @staticmethod
    def generate_totp_secret() -> str:
        """Generate a fresh base32 TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def generate_jwt_secret() -> str:
        """Generate a cryptographically-random JWT signing key."""
        return secrets.token_hex(32)

    # ── Verification ──────────────────────────────────────────────────────────

    def verify_password(self, plain_password: str) -> bool:
        return pwd_context.verify(plain_password, self.password_hash)

    def verify_totp(self, code: str) -> bool:
        """Accept current window ±1 (30-second drift tolerance)."""
        return self.totp.verify(code.strip(), valid_window=1)

    def verify_token(self, token: str, token_type: str = "access") -> Optional[str]:
        """Decode and validate a JWT.  Returns the username or None."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM])
            if payload.get("type") != token_type:
                return None
            return payload.get("sub")
        except JWTError:
            return None

    # ── Token creation ────────────────────────────────────────────────────────

    def create_temp_token(self) -> str:
        """Short-lived token returned after password check; used for 2FA step."""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=TEMP_TOKEN_EXPIRE_MINUTES
        )
        return jwt.encode(
            {"sub": self.username, "type": "temp", "exp": expire},
            self.secret_key,
            algorithm=ALGORITHM,
        )

    def create_access_token(self) -> str:
        """Full 24-hour access token returned after successful 2FA."""
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        return jwt.encode(
            {"sub": self.username, "type": "access", "exp": expire},
            self.secret_key,
            algorithm=ALGORITHM,
        )

    # ── TOTP / QR helpers ─────────────────────────────────────────────────────

    def get_totp_provisioning_uri(self, issuer: str = "Alchemy Trading Bot") -> str:
        """Return otpauth:// URI for QR code generation."""
        return self.totp.provisioning_uri(name=self.username, issuer_name=issuer)

    def get_qr_code_base64(self) -> str:
        """Return a base64-encoded PNG QR code for the TOTP setup screen."""
        uri = self.get_totp_provisioning_uri()
        img = qrcode.make(uri)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
