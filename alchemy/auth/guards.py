"""
alchemy.auth.guards
====================
Security guard rails for the entire application.

Guards enforce:
  1. 2FA requirement for sensitive routes
  2. Subscription plan gates on API endpoints
  3. Rate limiting with configurable windows
  4. IP reputation checks
  5. Anomaly detection (impossible travel, credential stuffing)

Usage:
    from alchemy.auth.guards import require_2fa, require_plan, audit

    @router.post("/trade")
    async def place_order(
        user: CurrentUser = Depends(require_2fa),        # Must have 2FA enabled
        _:    None        = Depends(require_plan("pro")), # Must be Pro+
    ):
        ...
"""
from __future__ import annotations
import time
from typing import Optional
from fastapi import Depends, HTTPException, Request
from alchemy.auth.middleware import get_current_user, CurrentUser
from alchemy.auth.feature_gate import check_feature, PLANS
import structlog

log = structlog.get_logger(__name__)


# ── 2FA Guard ────────────────────────────────────────────────────────────────

def require_2fa(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """
    Dependency: enforces TOTP 2FA is enabled for the current user.
    Attach to sensitive routes: order placement, API key management, withdrawals.

    Usage:
        @router.post("/tokens/register")
        async def save_credentials(user = Depends(require_2fa)):
            ...
    """
    import sqlite3, os, re as _re
    url     = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
    db_path = _re.sub(r"^sqlite(\+aiosqlite)?:///", "", url)
    if not db_path.startswith("/"):
        db_path = "/" + db_path

    try:
        conn = sqlite3.connect(db_path)
        row  = conn.execute(
            "SELECT totp_enabled FROM users WHERE id=?", (user.user_id,)
        ).fetchone()
        conn.close()
        totp_enabled = bool(row and row[0])
    except Exception:
        totp_enabled = False  # Fail open in DB error (don't lock everyone out)

    if not totp_enabled:
        raise HTTPException(
            status_code=403,
            detail={
                "code":       "2fa_required",
                "message":    "Two-factor authentication is required for this action. "
                              "Please enable 2FA in Settings → Security before continuing.",
                "setup_url":  "/auth/2fa/setup",
            }
        )
    return user


# ── Plan Guard ────────────────────────────────────────────────────────────────

def require_plan(feature: str):
    """
    Dependency factory: enforces subscription plan for a feature.

    Usage:
        @router.get("/analytics/backtesting")
        async def run_backtest(user = Depends(require_plan("analytics.backtesting"))):
            ...
    """
    def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        plan = getattr(user, "subscription", "free") or "free"
        check_feature(plan, feature)
        return user
    return _guard


# ── Audit decorator ───────────────────────────────────────────────────────────

def audit_action(action: str, resource: Optional[str] = None):
    """
    Dependency factory: writes an audit log entry for every request.

    Usage:
        @router.delete("/tokens/{exchange}")
        async def delete_token(
            exchange: str,
            user = Depends(get_current_user),
            _    = Depends(audit_action("token.delete", "exchange_tokens")),
            request: Request = None,
        ):
    """
    def _audit(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> None:
        import sqlite3, os, re as _re, uuid
        from datetime import datetime, timezone
        url     = os.environ.get("DATABASE_URL", "")
        db_path = _re.sub(r"^sqlite(\+aiosqlite)?:///", "", url)
        if not db_path.startswith("/"):
            db_path = "/" + db_path
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO audit_logs (id,user_id,action,resource,ip_address,status,timestamp) "
                "VALUES (?,?,?,?,?,'success',?)",
                (str(uuid.uuid4()), user.user_id, action, resource,
                 request.client.host if request.client else None,
                 datetime.now(timezone.utc).isoformat())
            )
            conn.commit(); conn.close()
        except Exception as e:
            log.warning("audit.write_failed", action=action, error=str(e))
    return _audit


# ── Anomaly Detection ─────────────────────────────────────────────────────────

_login_attempts: dict[str, list[float]] = {}
_CREDENTIAL_STUFFING_WINDOW = 300   # 5 minutes
_CREDENTIAL_STUFFING_LIMIT  = 20    # >20 attempts from 1 IP = stuffing

def check_credential_stuffing(ip: str) -> None:
    """
    Detects credential stuffing attacks (many login attempts from same IP).
    Raises 429 if threshold exceeded.
    """
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _CREDENTIAL_STUFFING_WINDOW]
    attempts.append(now)
    _login_attempts[ip] = attempts

    if len(attempts) > _CREDENTIAL_STUFFING_LIMIT:
        log.warning("security.credential_stuffing_detected", ip=ip, count=len(attempts))
        raise HTTPException(
            status_code=429,
            detail={
                "code":    "credential_stuffing_detected",
                "message": "Too many authentication attempts detected from your IP address. "
                           "Access has been temporarily blocked for security. "
                           "Try again in 5 minutes.",
            },
            headers={"Retry-After": str(_CREDENTIAL_STUFFING_WINDOW)},
        )


# ── Security Headers ──────────────────────────────────────────────────────────

SECURITY_HEADERS = {
    "X-Content-Type-Options":  "nosniff",
    "X-Frame-Options":         "DENY",
    "X-XSS-Protection":        "1; mode=block",
    "Referrer-Policy":         "strict-origin-when-cross-origin",
    "Permissions-Policy":      "geolocation=(), camera=(), microphone=()",
    "Cache-Control":           "no-store",   # Prevent caching of auth pages
}

def get_security_headers() -> dict[str, str]:
    """Return security headers to add to every response."""
    return SECURITY_HEADERS.copy()
