"""
alchemy.auth.otp_store
=======================
In-memory OTP store with TTL (Redis-ready for production).
Stores email-OTP pairs for verification and 2FA login.
"""
from __future__ import annotations
import secrets, time, hashlib
from typing import Optional

_WINDOW = 600  # 10 minutes TTL


class OTPStore:
    """Thread-safe in-memory OTP store with TTL."""
    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}  # key → (hashed_otp, expiry)

    def _key(self, purpose: str, identifier: str) -> str:
        return f"{purpose}:{identifier.lower()}"

    def _hash(self, otp: str) -> str:
        return hashlib.sha256(otp.encode()).hexdigest()

    def generate(self, purpose: str, identifier: str, length: int = 6) -> str:
        """Generate and store a numeric OTP. Returns the plain OTP."""
        otp = "".join([str(secrets.randbelow(10)) for _ in range(length)])
        key = self._key(purpose, identifier)
        self._store[key] = (self._hash(otp), time.time() + _WINDOW)
        return otp

    def verify(self, purpose: str, identifier: str, otp: str,
                consume: bool = True) -> bool:
        """Verify OTP. consume=True deletes it after successful verify."""
        key = self._key(purpose, identifier)
        entry = self._store.get(key)
        if not entry:
            return False
        hashed_otp, expiry = entry
        if time.time() > expiry:
            self._store.pop(key, None)
            return False
        if not secrets.compare_digest(self._hash(otp), hashed_otp):
            return False
        if consume:
            self._store.pop(key, None)
        return True

    def invalidate(self, purpose: str, identifier: str) -> None:
        self._store.pop(self._key(purpose, identifier), None)

    def cleanup(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)


# Singleton
_store = OTPStore()


def generate_otp(purpose: str, identifier: str, length: int = 6) -> str:
    return _store.generate(purpose, identifier, length)


def verify_otp(purpose: str, identifier: str, otp: str, consume: bool = True) -> bool:
    return _store.verify(purpose, identifier, otp, consume)


def invalidate_otp(purpose: str, identifier: str) -> None:
    _store.invalidate(purpose, identifier)
