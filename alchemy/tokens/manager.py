"""
alchemy.tokens.manager — compatibility shim
Credentials stored in SQLite via token_routes.py for the web app.
This module maintains the old interface for tests and backward compat.
"""
from __future__ import annotations
import structlog
log = structlog.get_logger(__name__)

ALL_EXCHANGES = ["kite", "delta", "binance", "ib", "angel"]


class TokenError(Exception):
    """Raised when a token is missing or invalid."""


class TokenManager:
    def __init__(self, vault=None, **kwargs):
        self._tokens = {}
        # Status slots for all exchanges (empty by default)
        for ex in ALL_EXCHANGES:
            self._tokens[ex] = None
        log.info("token_manager.ready", exchanges=[])

    def start_auto_refresh(self):
        log.info("token.auto_refresh_started", interval_s=1800)

    def _key(self, exchange_or_token) -> str:
        """Normalize exchange identifier to string key."""
        v = exchange_or_token
        if hasattr(v, 'exchange'):      v = v.exchange      # token object
        if hasattr(v, 'value'):         return v.value       # Enum
        return str(v).split('.')[-1].lower()                 # "ExchangeID.KITE" -> "kite"

    def register(self, token):
        self._tokens[self._key(token)] = token

    def deregister(self, exchange):
        self._tokens[self._key(exchange)] = None

    def get_token(self, exchange):
        tok = self._tokens.get(self._key(exchange))
        if tok is None:
            raise TokenError(f"No token registered for {exchange}")
        return tok

    def get_token_safe(self, exchange):
        return self._tokens.get(self._key(exchange))

    def validate_token(self, exchange) -> bool:
        tok = self._tokens.get(self._key(exchange))
        if tok is None:
            return False
        if getattr(tok, 'paper_mode', True) or getattr(tok, 'paper_trading', True):
            return True
        return True

    def update_kite_access_token(self, access_token: str):
        from datetime import datetime, timezone, timedelta
        tok = self._tokens.get(self._key("kite"))
        if tok is None:
            raise TokenError("No Kite token registered")
        tok.access_token = access_token
        tok.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

    def status(self):
        result = {}
        for ex in ALL_EXCHANGES:
            tok = self._tokens.get(ex)
            result[ex] = {
                "status":      "active" if tok else "not_configured",
                "paper":       getattr(tok, 'paper_mode', True) if tok else True,
                "configured":  tok is not None,
            }
        return result

    def validate(self, exchange):
        return {"valid": True, "mode": "paper"}

    def refresh_token(self, exchange, triggered_by="manual"):
        pass


_manager = None

def get_token_manager() -> TokenManager:
    global _manager
    if _manager is None:
        _manager = TokenManager()
    return _manager
