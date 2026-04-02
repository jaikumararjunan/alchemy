"""
alchemy.tokens.manager
=======================
Central token manager for all exchange credentials.

Responsibilities:
  - Register / update / delete exchange tokens
  - Validate tokens against live exchange APIs
  - Schedule and execute automatic token refresh
  - Provide a get_token() interface consumed by all gateways
  - Emit events on token lifecycle changes

Usage::

    manager = TokenManager()

    # Register a Kite token
    manager.register(KiteToken(
        api_key="abc123", api_secret="secret",
        access_token="live_token", paper_mode=False
    ))

    # Get a valid token (raises if invalid / expired)
    token = manager.get_token(ExchangeID.KITE)

    # Status of all tokens
    status = manager.status()
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import structlog

from alchemy.tokens.models import (
    ExchangeID, TokenStatus, TokenRefreshEvent,
    ExchangeToken, KiteToken, DeltaToken, BinanceToken, IBToken,
)
from alchemy.tokens.vault import TokenVault

log = structlog.get_logger(__name__)


class TokenError(Exception):
    """Raised when a token is missing, expired, or invalid."""


class TokenManager:
    """
    Thread-safe central registry for all exchange tokens.

    Token Lifecycle:
        MISSING → (register) → ACTIVE
        ACTIVE  → (time passes) → EXPIRING → EXPIRED
        EXPIRING/EXPIRED → (refresh) → ACTIVE
        ACTIVE  → (validation fails) → INVALID
        INVALID → (re-register) → ACTIVE

    Auto-refresh is triggered:
        - When needs_refresh is True (< 1 hour to expiry)
        - On a background scheduler every 30 minutes
        - Manually via refresh_token(exchange)
    """

    REFRESH_INTERVAL_S = 1800   # 30 minutes

    def __init__(self, vault: Optional[TokenVault] = None) -> None:
        self._vault     = vault or TokenVault()
        self._tokens:   dict[ExchangeID, ExchangeToken] = {}
        self._lock      = threading.RLock()
        self._callbacks: list[Callable[[ExchangeID, TokenStatus], None]] = []
        self._refresh_history: list[TokenRefreshEvent] = []
        self._load_from_vault()
        log.info("token_manager.ready", exchanges=list(self._tokens.keys()))

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, token: ExchangeToken) -> None:
        """Store and activate an exchange token."""
        with self._lock:
            token.status     = TokenStatus.ACTIVE
            token.updated_at = datetime.now(timezone.utc)
            self._tokens[token.exchange] = token
            self._persist(token)
            self._emit(token.exchange, TokenStatus.ACTIVE)
            log.info("token.registered", exchange=token.exchange.value,
                     paper=token.paper_mode, expires=token.expires_at)

    def update_kite_access_token(self, access_token: str) -> None:
        """
        Update Kite access_token after OAuth callback.
        Kite tokens expire at 06:00 AM IST the next day.
        """
        with self._lock:
            token = self._get_or_create(ExchangeID.KITE, KiteToken)
            token.access_token = access_token
            token.status       = TokenStatus.ACTIVE
            # Kite expires at next 06:00 IST
            now_ist  = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            expiry   = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)
            if expiry <= now_ist:
                expiry += timedelta(days=1)
            token.expires_at = expiry - timedelta(hours=5, minutes=30)  # back to UTC
            token.updated_at = datetime.now(timezone.utc)
            self._persist(token)
            self._emit(ExchangeID.KITE, TokenStatus.ACTIVE)
            log.info("kite.token_updated", expires_utc=token.expires_at)

    def deregister(self, exchange: ExchangeID) -> bool:
        """Remove a token from registry and vault."""
        with self._lock:
            if exchange in self._tokens:
                del self._tokens[exchange]
            deleted = self._vault.delete(exchange.value)
            log.info("token.deregistered", exchange=exchange.value)
            return deleted

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_token(self, exchange: ExchangeID) -> ExchangeToken:
        """
        Return a valid token for the exchange.

        Raises:
            TokenError: if the token is missing, expired, or invalid.
        """
        with self._lock:
            token = self._tokens.get(exchange)
            if token is None:
                raise TokenError(f"No token registered for {exchange.value}. "
                                 "Call manager.register() first.")
            if token.is_expired:
                token.status = TokenStatus.EXPIRED
                self._emit(exchange, TokenStatus.EXPIRED)
                raise TokenError(f"{exchange.value} token is expired. "
                                 "Call manager.refresh_token() to renew.")
            if token.status == TokenStatus.INVALID:
                raise TokenError(f"{exchange.value} token is invalid: {token.last_error}")
            if token.needs_refresh:
                token.status = TokenStatus.EXPIRING
                self._emit(exchange, TokenStatus.EXPIRING)
                log.warning("token.expiring_soon",
                            exchange=exchange.value,
                            seconds=token.seconds_to_expiry)
            token.mark_used()
            return token

    def get_token_safe(self, exchange: ExchangeID) -> Optional[ExchangeToken]:
        """Like get_token but returns None instead of raising."""
        try:
            return self.get_token(exchange)
        except TokenError:
            return None

    def all_tokens(self) -> dict[ExchangeID, ExchangeToken]:
        with self._lock:
            return dict(self._tokens)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_token(self, exchange: ExchangeID) -> bool:
        """
        Validate a token by making a lightweight authenticated API call.
        Updates token status accordingly.
        """
        with self._lock:
            token = self._tokens.get(exchange)
            if token is None:
                return False

        try:
            valid = self._call_validate(token)
            with self._lock:
                token.status     = TokenStatus.ACTIVE if valid else TokenStatus.INVALID
                token.updated_at = datetime.now(timezone.utc)
                self._emit(exchange, token.status)
            log.info("token.validated", exchange=exchange.value, valid=valid)
            return valid
        except Exception as e:
            with self._lock:
                token.mark_error(str(e))
            log.error("token.validate_error", exchange=exchange.value, error=str(e))
            return False

    def validate_all(self) -> dict[str, bool]:
        """Validate all registered tokens. Returns {exchange: valid}."""
        return {
            ex.value: self.validate_token(ex)
            for ex in list(self._tokens.keys())
        }

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh_token(self, exchange: ExchangeID, triggered_by: str = "manual") -> bool:
        """
        Attempt to refresh an expiring or expired token.

        Kite: Requires browser automation (Playwright) — returns
              instructions for manual token entry.
        Delta/Binance: Long-lived — logs a rotation reminder.
        IB: Re-connects the TWS session.
        """
        token = self._tokens.get(exchange)
        if token is None:
            log.error("token.refresh_not_found", exchange=exchange.value)
            return False

        old_expiry = token.expires_at
        event = TokenRefreshEvent(exchange=exchange, success=False,
                                  old_expiry=old_expiry, triggered_by=triggered_by)
        try:
            with self._lock:
                token.status = TokenStatus.REFRESHING
            success = self._do_refresh(token)
            event.success    = success
            event.new_expiry = token.expires_at
            if success:
                with self._lock:
                    token.status     = TokenStatus.ACTIVE
                    token.updated_at = datetime.now(timezone.utc)
                    self._persist(token)
                    self._emit(exchange, TokenStatus.ACTIVE)
            log.info("token.refresh", exchange=exchange.value,
                     success=success, new_expiry=token.expires_at)
        except Exception as e:
            event.error = str(e)
            with self._lock:
                token.mark_error(str(e))
            log.error("token.refresh_error", exchange=exchange.value, error=str(e))
        finally:
            self._refresh_history.append(event)
        return event.success

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return status of all tokens (safe — no secrets)."""
        with self._lock:
            result = {}
            for ex, token in self._tokens.items():
                # Refresh status based on current time
                if token.is_expired:
                    token.status = TokenStatus.EXPIRED
                elif token.needs_refresh and token.status == TokenStatus.ACTIVE:
                    token.status = TokenStatus.EXPIRING
                result[ex.value] = token.to_safe_dict()
            # Add MISSING for unconfigured exchanges
            for ex in ExchangeID:
                if ex.value not in result:
                    result[ex.value] = {"exchange": ex.value, "status": "missing"}
            return result

    def refresh_history(self, limit: int = 20) -> list[dict]:
        return [
            {
                "exchange":     e.exchange.value,
                "success":      e.success,
                "timestamp":    e.timestamp.isoformat(),
                "triggered_by": e.triggered_by,
                "error":        e.error,
                "new_expiry":   e.new_expiry.isoformat() if e.new_expiry else None,
            }
            for e in self._refresh_history[-limit:]
        ]

    # ── Event callbacks ───────────────────────────────────────────────────────

    def on_status_change(self, callback: Callable[[ExchangeID, TokenStatus], None]) -> None:
        """Register a callback for token status changes."""
        self._callbacks.append(callback)

    # ── Background refresh scheduler ─────────────────────────────────────────

    def start_auto_refresh(self) -> None:
        """Start background thread that checks and refreshes expiring tokens."""
        t = threading.Thread(target=self._refresh_loop, daemon=True)
        t.start()
        log.info("token.auto_refresh_started", interval_s=self.REFRESH_INTERVAL_S)

    def _refresh_loop(self) -> None:
        import time
        while True:
            time.sleep(self.REFRESH_INTERVAL_S)
            with self._lock:
                to_refresh = [
                    ex for ex, tok in self._tokens.items()
                    if tok.needs_refresh and tok.status != TokenStatus.REFRESHING
                ]
            for ex in to_refresh:
                log.info("token.auto_refresh_trigger", exchange=ex.value)
                self.refresh_token(ex, triggered_by="auto")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _emit(self, exchange: ExchangeID, status: TokenStatus) -> None:
        for cb in self._callbacks:
            try:
                cb(exchange, status)
            except Exception:
                pass

    def _persist(self, token: ExchangeToken) -> None:
        try:
            self._vault.store(token.exchange.value, token.model_dump(mode="json"))
        except Exception as e:
            log.warning("vault.persist_failed", error=str(e))

    def _load_from_vault(self) -> None:
        for exchange_str in self._vault.list_exchanges():
            try:
                data = self._vault.retrieve(exchange_str)
                if data is None:
                    continue
                ex = ExchangeID(exchange_str)
                cls_map = {
                    ExchangeID.KITE:    KiteToken,
                    ExchangeID.DELTA:   DeltaToken,
                    ExchangeID.BINANCE: BinanceToken,
                    ExchangeID.IB:      IBToken,
                }
                token = cls_map[ex](**data)
                self._tokens[ex] = token
                log.info("vault.loaded", exchange=exchange_str)
            except Exception as e:
                log.warning("vault.load_failed", exchange=exchange_str, error=str(e))

    def _get_or_create(self, exchange: ExchangeID, cls) -> ExchangeToken:
        if exchange not in self._tokens:
            self._tokens[exchange] = cls(api_key="", api_secret="")
        return self._tokens[exchange]

    def _call_validate(self, token: ExchangeToken) -> bool:
        """Make a lightweight API call to verify the token is accepted."""
        if token.paper_mode:
            return True    # Paper mode — always valid
        if isinstance(token, KiteToken):
            return self._validate_kite(token)
        if isinstance(token, DeltaToken):
            return self._validate_delta(token)
        if isinstance(token, BinanceToken):
            return self._validate_binance(token)
        if isinstance(token, IBToken):
            return token.connected
        return False

    def _validate_kite(self, token: KiteToken) -> bool:
        try:
            from kiteconnect import KiteConnect
            kc = KiteConnect(api_key=token.api_key)
            if token.access_token:
                kc.set_access_token(token.access_token)
                profile = kc.profile()
                return bool(profile.get("user_name"))
            return False
        except Exception:
            return False

    def _validate_delta(self, token: DeltaToken) -> bool:
        try:
            import httpx, hmac as hmac_lib, hashlib as hs, time
            url  = "https://testnet-api.delta.exchange/v2/profile" if token.testnet else "https://api.delta.exchange/v2/profile"
            ts   = str(int(time.time()))
            sig  = hmac_lib.new(token.api_secret.get_secret_value().encode(),
                                ("GET" + ts + "/v2/profile").encode(), hs.sha256).hexdigest()
            resp = httpx.get(url, headers={"api-key": token.api_key, "timestamp": ts, "signature": sig}, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _validate_binance(self, token: BinanceToken) -> bool:
        try:
            import httpx, hmac as hmac_lib, hashlib as hs, time
            from urllib.parse import urlencode
            base = "https://testnet.binancefuture.com" if token.testnet else "https://fapi.binance.com"
            params = {"timestamp": int(time.time() * 1000)}
            qs = urlencode(params)
            sig = hmac_lib.new(token.api_secret.get_secret_value().encode(), qs.encode(), hs.sha256).hexdigest()
            resp = httpx.get(f"{base}/fapi/v2/balance", params={**params, "signature": sig},
                             headers={"X-MBX-APIKEY": token.api_key}, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _do_refresh(self, token: ExchangeToken) -> bool:
        """Exchange-specific refresh logic."""
        if isinstance(token, KiteToken):
            log.warning("kite.manual_refresh_required",
                        msg="Kite requires browser login — use /tokens/kite/refresh-url endpoint")
            return False
        if isinstance(token, (DeltaToken, BinanceToken)):
            log.info("token.long_lived_reminder",
                     exchange=token.exchange.value,
                     msg="Token is long-lived — rotate manually every 90 days")
            # Extend soft-expiry reminder by 90 days
            token.expires_at = datetime.now(timezone.utc) + timedelta(days=90)
            return True
        return False


# ── Singleton ──────────────────────────────────────────────────────────────────
_manager_instance: Optional[TokenManager] = None

def get_token_manager() -> TokenManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = TokenManager()
    return _manager_instance
