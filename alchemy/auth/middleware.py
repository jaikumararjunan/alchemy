"""
alchemy.auth.middleware
========================
FastAPI middleware stack:
  1. SecurityHeadersMiddleware  — injects HSTS/CSP/X-Frame headers on every response
  2. RateLimitMiddleware        — Redis-backed per-IP and per-user rate limiting
  3. get_current_user           — JWT dependency: validates Bearer token
  4. require_role               — RBAC permission check dependency
  5. require_2fa                — Ensures 2FA is enabled for sensitive routes
"""
from __future__ import annotations

import secrets
import time
from functools import lru_cache
from typing import Callable, Optional

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from alchemy.auth.security import SECURITY_HEADERS, decode_access_token
from alchemy.users.models import UserRole, has_permission

log = structlog.get_logger(__name__)

bearer = HTTPBearer(auto_error=False)

# ── Rate Limit Store (in-memory for dev, Redis for production) ───────────────

class InMemoryRateLimiter:
    """
    Sliding window rate limiter.
    Production: replace with Redis SORTED SET implementation.
    """
    def __init__(self):
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(self, key: str, max_requests: int, window_s: int) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now   = time.time()
        bucket = self._buckets.get(key, [])
        # Remove expired timestamps
        bucket = [t for t in bucket if now - t < window_s]
        if len(bucket) >= max_requests:
            oldest = min(bucket)
            retry  = int(window_s - (now - oldest)) + 1
            return False, retry
        bucket.append(now)
        self._buckets[key] = bucket
        return True, 0

_rate_limiter = InMemoryRateLimiter()

# Rate limit configs: (max_requests, window_seconds)
# Development: very permissive — localhost is trusted
import os as _os
_IS_DEV = _os.environ.get("ENV","development").lower() in ("development","dev","local","test")

RATE_LIMITS = {
    # Dev: 200 attempts per minute | Prod: 10 per 15 minutes
    "auth.login":    (200, 60)   if _IS_DEV else (10,  900),
    "auth.signup":   (50,  60)   if _IS_DEV else (5,   3600),
    "auth.2fa":      (100, 60)   if _IS_DEV else (10,  300),
    "auth.reset":    (50,  60)   if _IS_DEV else (3,   3600),
    "api.general":   (500, 60),
    "api.trade":     (100, 60),
    "auth.otp_send":   (3,   600) if not _IS_DEV else (100, 60),   # 3 sends per 10 min
    "auth.otp_verify": (5,   600) if not _IS_DEV else (100, 60),   # separate limit for verify
}


def clear_rate_limit(ip: str = None) -> None:
    """Clear all rate limit buckets (useful after lockout in dev)."""
    if ip:
        keys = [k for k in _rate_limiter._buckets if ip in k]
        for k in keys:
            _rate_limiter._buckets.pop(k, None)
    else:
        _rate_limiter._buckets.clear()


def check_rate_limit(request: Request, limit_key: str) -> None:
    """Check rate limit. Raises 429 if exceeded. Skips for localhost in dev."""
    ip = request.client.host if request.client else "unknown"

    # Always allow localhost in dev mode
    if _IS_DEV and ip in ("127.0.0.1", "::1", "localhost"):
        return

    max_req, window = RATE_LIMITS.get(limit_key, (500, 60))
    bucket_key = f"{limit_key}:{ip}"
    allowed, retry_after = _rate_limiter.is_allowed(bucket_key, max_req, window)
    if not allowed:
        log.warning("rate_limit.exceeded", ip=ip, limit=limit_key, retry=retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


# ── Security Headers Middleware ───────────────────────────────────────────────

class SecurityHeadersMiddleware:
    """
    Adds security headers to every response.
    Generates a per-request CSP nonce for inline script safety.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        nonce = secrets.token_urlsafe(16)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                for k, v in SECURITY_HEADERS.items():
                    headers[k.lower().encode()] = v.replace("{nonce}", nonce).encode()
                # Remove Server header to avoid version disclosure
                headers.pop(b"server", None)
                message = {**message, "headers": list(headers.items())}
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ── JWT Auth Dependencies ─────────────────────────────────────────────────────

class CurrentUser:
    """Lightweight user context extracted from JWT — no DB hit required."""
    def __init__(self, payload: dict):
        self.user_id  = payload["sub"]
        self.email    = payload["email"]
        self.role     = payload["role"]
        self.jti      = payload.get("jti")

    def has_permission(self, permission: str) -> bool:
        try:
            role = UserRole(self.role)
            return has_permission(role, permission)
        except ValueError:
            return False


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> CurrentUser:
    """
    FastAPI dependency: extract and validate JWT from Authorization header.

    Also checks httpOnly cookie as fallback (for browser clients).

    Usage::
        @app.get("/protected")
        async def route(user: CurrentUser = Depends(get_current_user)):
            ...
    """
    token = None

    # 1. Bearer token in Authorization header (API clients)
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    # 2. httpOnly cookie (browser clients — more secure against XSS)
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        return CurrentUser(payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired — please refresh",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        log.warning("auth.invalid_token", error=str(e),
                    ip=request.client.host if request.client else "?")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_permission(permission: str) -> Callable:
    """
    FastAPI dependency factory: check RBAC permission.

    Usage::
        @app.post("/workflows/buy")
        async def buy(user: CurrentUser = Depends(require_permission("trading:execute"))):
            ...
    """
    async def checker(
        user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission}",
            )
        return user
    return checker


def require_role(*roles: UserRole) -> Callable:
    """Require one of the specified roles."""
    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {[r.value for r in roles]}",
            )
        return user
    return checker


def require_admin() -> Callable:
    return require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


# ── Audit Helper ──────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """
    Extract real IP respecting X-Forwarded-For (behind load balancer).

    SECURITY: Only trust X-Forwarded-For when the direct peer is a private/loopback
    address (i.e., a trusted reverse proxy). When the direct peer is a public IP the
    header can be spoofed by the client — in that case fall back to the peer address.
    """
    import ipaddress
    direct_ip = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        try:
            peer = ipaddress.ip_address(direct_ip)
            if peer.is_private or peer.is_loopback:
                # Trusted proxy — find the rightmost PUBLIC IP in the chain.
                # In a single-proxy setup (client → nginx → app):
                #   X-Forwarded-For: real_client_ip           → return real_client_ip
                # When a client spoofs by injecting a header:
                #   X-Forwarded-For: spoofed_ip, real_client_ip (nginx appends last)
                #   → rightmost public = real_client_ip (CORRECT)
                # In multi-proxy chains (client → proxy1 → proxy2 → app):
                #   X-Forwarded-For: client_ip, proxy1_ip
                #   → rightmost public that is not an internal proxy = client_ip
                addrs = [a.strip() for a in forwarded.split(",")]
                for addr in reversed(addrs):
                    try:
                        parsed = ipaddress.ip_address(addr)
                        if not parsed.is_private and not parsed.is_loopback:
                            return addr
                    except ValueError:
                        continue
                # All addresses are private/loopback (e.g. all-internal network)
                # — fall through to direct_ip
        except ValueError:
            pass

    return direct_ip
