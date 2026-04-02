"""
alchemy.tokens.models
=====================
Data models for exchange authentication tokens.

Each exchange uses a different auth pattern:
  - Kite Connect : API key + secret → daily access_token (expires at 6am IST)
  - Delta Exchange: API key + secret (long-lived, HMAC-signed per request)
  - Binance       : API key + secret (long-lived, HMAC-signed per request)
  - Interactive Brokers: No token — TCP session via IBController/Gateway
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, SecretStr


class ExchangeID(str, Enum):
    KITE    = "kite"
    DELTA   = "delta"
    BINANCE = "binance"
    IB      = "ib"


class TokenStatus(str, Enum):
    ACTIVE    = "active"      # Valid and usable
    EXPIRING  = "expiring"    # Valid but < 1 hour to expiry
    EXPIRED   = "expired"     # Past expiry — needs refresh
    INVALID   = "invalid"     # Validation failed
    MISSING   = "missing"     # Not configured
    REFRESHING= "refreshing"  # Currently being refreshed


class ExchangeToken(BaseModel):
    """Base token model — one per exchange connection."""

    exchange:    ExchangeID
    api_key:     str
    api_secret:  SecretStr
    status:      TokenStatus = TokenStatus.MISSING
    created_at:  datetime    = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:  datetime    = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at:  Optional[datetime] = None
    last_used_at:Optional[datetime] = None
    last_error:  Optional[str]      = None
    use_count:   int  = 0
    paper_mode:  bool = True

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def seconds_to_expiry(self) -> Optional[float]:
        if self.expires_at is None:
            return None
        delta = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)

    @property
    def needs_refresh(self) -> bool:
        if self.expires_at is None:
            return False
        secs = self.seconds_to_expiry or 0
        return secs < 3600  # Refresh when < 1 hour remaining

    def mark_used(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)
        self.use_count    += 1
        self.updated_at   = datetime.now(timezone.utc)

    def mark_error(self, error: str) -> None:
        self.last_error  = error
        self.status      = TokenStatus.INVALID
        self.updated_at  = datetime.now(timezone.utc)

    def to_safe_dict(self) -> dict:
        """Return dict safe for API responses — secrets redacted."""
        return {
            "exchange":      self.exchange.value,
            "api_key":       self.api_key[:6] + "…" + self.api_key[-4:] if len(self.api_key) > 10 else "***",
            "status":        self.status.value,
            "paper_mode":    self.paper_mode,
            "created_at":    self.created_at.isoformat(),
            "expires_at":    self.expires_at.isoformat() if self.expires_at else None,
            "seconds_to_expiry": self.seconds_to_expiry,
            "needs_refresh": self.needs_refresh,
            "use_count":     self.use_count,
            "last_error":    self.last_error,
        }


class KiteToken(ExchangeToken):
    """
    Zerodha Kite Connect token.

    Kite uses a 3-step OAuth flow:
        1. Redirect user to login URL
        2. User logs in → callback with request_token
        3. POST /session/token with request_token → access_token

    The access_token expires at 06:00 AM IST every day.
    Auto-refresh requires Playwright/Selenium to simulate login.
    """
    exchange:       ExchangeID    = ExchangeID.KITE
    access_token:   Optional[str] = None
    request_token:  Optional[str] = None
    login_url:      Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self.access_token is not None and not self.is_expired


class DeltaToken(ExchangeToken):
    """
    Delta Exchange API token.

    Delta uses per-request HMAC-SHA256 signing:
        signature = HMAC(secret, method + timestamp + path + body)

    Tokens are long-lived — rotate manually every 90 days.
    No OAuth / access_token needed.
    """
    exchange:    ExchangeID = ExchangeID.DELTA
    testnet:     bool       = True
    rate_limit:  int        = 300    # requests per minute


class BinanceToken(ExchangeToken):
    """
    Binance API token.

    Binance uses HMAC-SHA256 on query string for signed endpoints.
    Tokens are long-lived — IP whitelisting recommended.
    Supports Ed25519 key pairs for higher security.
    """
    exchange:     ExchangeID = ExchangeID.BINANCE
    testnet:      bool       = False
    market_type:  str        = "futures_usdm"   # spot | futures_usdm | futures_coinm
    recv_window:  int        = 5000             # milliseconds
    ip_whitelist: list[str]  = Field(default_factory=list)


class IBToken(ExchangeToken):
    """
    Interactive Brokers session — no API token, TCP connection.
    Credential fields store TWS login for ib-controller.
    """
    exchange:   ExchangeID = ExchangeID.IB
    host:       str        = "127.0.0.1"
    port:       int        = 7497
    client_id:  int        = 1
    account_id: Optional[str] = None
    connected:  bool       = False

    @property
    def is_expired(self) -> bool:
        return False   # IB sessions don't expire via token


class TokenRefreshEvent(BaseModel):
    """Audit record of a token refresh attempt."""
    exchange:   ExchangeID
    success:    bool
    timestamp:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    old_expiry: Optional[datetime] = None
    new_expiry: Optional[datetime] = None
    error:      Optional[str]      = None
    triggered_by: str = "auto"    # auto | manual | api
