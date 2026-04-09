"""
alchemy.notifications.models
=============================
Data models for the notification system.

Design:
  NotificationChannel  — a user's configured delivery endpoint (e.g. their Telegram chat)
  NotificationEvent    — a platform event that can trigger notifications
  DeliveryRecord       — immutable log of every send attempt
  NotificationRule     — which events go to which channels for which user
  NotificationPreference — per-user global settings (quiet hours, digest mode)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Event types ───────────────────────────────────────────────────────────────

class EventType(str, Enum):
    # Trading signals
    SIGNAL_BUY            = "signal.buy"
    SIGNAL_SELL           = "signal.sell"
    SIGNAL_HOLD           = "signal.hold"

    # Order lifecycle
    ORDER_PLACED          = "order.placed"
    ORDER_FILLED          = "order.filled"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_REJECTED        = "order.rejected"
    ORDER_CANCELLED       = "order.cancelled"

    # Risk management
    RISK_EMERGENCY_STOP   = "risk.emergency_stop"
    RISK_STOP_CLEARED     = "risk.stop_cleared"
    RISK_DRAWDOWN_ALERT   = "risk.drawdown_alert"
    RISK_DAILY_LOSS_LIMIT = "risk.daily_loss_limit"
    RISK_POSITION_LIMIT   = "risk.position_limit"

    # Token / Exchange
    TOKEN_EXPIRING        = "token.expiring"
    TOKEN_EXPIRED         = "token.expired"
    TOKEN_REFRESHED       = "token.refreshed"
    EXCHANGE_DISCONNECTED = "exchange.disconnected"

    # Security / Auth
    AUTH_LOGIN_NEW_IP     = "auth.login_new_ip"
    AUTH_2FA_DISABLED     = "auth.2fa_disabled"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    AUTH_ACCOUNT_LOCKED   = "auth.account_locked"

    # Price alerts (user-configured)
    PRICE_ABOVE           = "price.above"
    PRICE_BELOW           = "price.below"

    # System
    SYSTEM_STARTUP        = "system.startup"
    SYSTEM_ERROR          = "system.error"
    DAILY_SUMMARY         = "daily.summary"
    CUSTOM                = "custom"


# Event severity
class EventSeverity(str, Enum):
    INFO     = "info"
    SUCCESS  = "success"
    WARNING  = "warning"
    CRITICAL = "critical"


EVENT_SEVERITY: dict[EventType, EventSeverity] = {
    EventType.SIGNAL_BUY:            EventSeverity.INFO,
    EventType.SIGNAL_SELL:           EventSeverity.INFO,
    EventType.ORDER_FILLED:          EventSeverity.SUCCESS,
    EventType.ORDER_REJECTED:        EventSeverity.WARNING,
    EventType.RISK_EMERGENCY_STOP:   EventSeverity.CRITICAL,
    EventType.RISK_DRAWDOWN_ALERT:   EventSeverity.WARNING,
    EventType.RISK_DAILY_LOSS_LIMIT: EventSeverity.CRITICAL,
    EventType.TOKEN_EXPIRING:        EventSeverity.WARNING,
    EventType.TOKEN_EXPIRED:         EventSeverity.CRITICAL,
    EventType.AUTH_LOGIN_NEW_IP:     EventSeverity.WARNING,
    EventType.AUTH_2FA_DISABLED:     EventSeverity.CRITICAL,
    EventType.AUTH_ACCOUNT_LOCKED:   EventSeverity.CRITICAL,
    EventType.SYSTEM_ERROR:          EventSeverity.CRITICAL,
}


# ── Provider types ─────────────────────────────────────────────────────────────

class ProviderType(str, Enum):
    TELEGRAM  = "telegram"
    WHATSAPP  = "whatsapp"
    SMS       = "sms"
    EMAIL     = "email"
    SLACK     = "slack"
    DISCORD   = "discord"
    WEBHOOK   = "webhook"
    PUSHOVER  = "pushover"
    # New providers: add an entry here + create providers/{name}.py


class DeliveryStatus(str, Enum):
    PENDING   = "pending"
    QUEUED    = "queued"
    SENT      = "sent"
    DELIVERED = "delivered"
    FAILED    = "failed"
    RETRYING  = "retrying"
    SKIPPED   = "skipped"   # Quiet hours, deduplication, etc.


# ── Core models ────────────────────────────────────────────────────────────────

class NotificationChannel(BaseModel):
    """
    A configured delivery channel for a user.
    e.g. "Jai's Telegram" → Telegram chat_id 123456789
    """
    id:          str = Field(default_factory=lambda: str(uuid4()))
    user_id:     str
    provider:    ProviderType
    name:        str                    # Display name: "My Telegram", "Work SMS"
    enabled:     bool = True

    # Provider-specific config (encrypted at rest in production)
    config:      dict[str, Any] = Field(default_factory=dict)
    # Examples:
    #   Telegram: {"chat_id": "123456789", "bot_token": "..."}
    #   WhatsApp: {"to": "+919876543210", "account_sid": "...", "auth_token": "..."}
    #   SMS:      {"to": "+919876543210", "provider": "twilio", "sid": "...", "token": "..."}

    # Delivery stats
    total_sent:    int = 0
    total_failed:  int = 0
    last_sent_at:  Optional[datetime] = None
    last_error:    Optional[str] = None

    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def safe_dict(self) -> dict:
        """Return dict with secrets redacted."""
        safe_config = {}
        SENSITIVE = {"bot_token","auth_token","api_key","secret","password","token","sid"}
        for k, v in self.config.items():
            if any(s in k.lower() for s in SENSITIVE):
                safe_config[k] = "***" + str(v)[-4:] if len(str(v)) > 4 else "***"
            else:
                safe_config[k] = v
        return {**self.model_dump(exclude={"config"}), "config": safe_config}


class NotificationEvent(BaseModel):
    """
    A platform event to be dispatched to relevant channels.
    Created by any module (risk manager, workflow engine, auth service, etc.)
    """
    id:          str = Field(default_factory=lambda: str(uuid4()))
    event_type:  EventType
    severity:    EventSeverity = EventSeverity.INFO
    user_id:     Optional[str] = None   # None = broadcast to all admins
    title:       str
    message:     str
    data:        dict[str, Any] = Field(default_factory=dict)  # Rich payload
    source:      str = "alchemy"   # Module that triggered this
    idempotency_key: Optional[str] = None   # Prevent duplicate sends
    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_signal(cls, signal, user_id: Optional[str] = None) -> "NotificationEvent":
        emoji = "🟢" if signal.signal == "BUY" else "🔴" if signal.signal == "SELL" else "🟡"
        return cls(
            event_type=EventType.SIGNAL_BUY if signal.signal=="BUY" else
                       EventType.SIGNAL_SELL if signal.signal=="SELL" else EventType.SIGNAL_HOLD,
            severity=EventSeverity.INFO,
            user_id=user_id,
            title=f"{emoji} {signal.signal} Signal — {signal.ticker}",
            message=(f"**{signal.ticker}** {signal.signal} on {signal.market}\n"
                     f"Position: {signal.position_pct*100:.1f}%  |  "
                     f"Stop: {signal.stop_loss_pct*100:.1f}%  |  "
                     f"TP: {signal.take_profit_pct*100:.1f}%\n"
                     f"Sentiment: {signal.sentiment_score:.2f}  |  "
                     f"Vol: {signal.forecast_vol*100:.0f}%"),
            data={"ticker":signal.ticker, "signal":signal.signal,
                  "position_pct":signal.position_pct, "run_id":signal.run_id},
            source="ai_agent",
        )

    @classmethod
    def from_order(cls, workflow_state, user_id: Optional[str] = None) -> "NotificationEvent":
        status = workflow_state.status.value
        emoji  = "✅" if status in ("filled","settled") else "❌" if status in ("rejected","error") else "⏳"
        return cls(
            event_type=EventType.ORDER_FILLED if status in ("filled","settled") else
                       EventType.ORDER_REJECTED if status in ("rejected","error") else
                       EventType.ORDER_PLACED,
            severity=EventSeverity.SUCCESS if status in ("filled","settled") else
                     EventSeverity.WARNING if status in ("rejected","error") else EventSeverity.INFO,
            user_id=user_id,
            title=f"{emoji} Order {status.title()} — {workflow_state.request.symbol}",
            message=(f"**{workflow_state.request.side.value.upper()} "
                     f"{workflow_state.request.quantity} {workflow_state.request.symbol}**\n"
                     f"Status: {status}  |  Exchange: {workflow_state.routed_to or '—'}\n"
                     f"Fill: {workflow_state.fill_price or '—'}  |  "
                     f"Duration: {workflow_state.duration_ms:.0f}ms"),
            data={"workflow_id": workflow_state.workflow_id,
                  "symbol": workflow_state.request.symbol,
                  "fill_price": workflow_state.fill_price},
            source="workflow_engine",
        )

    @classmethod
    def risk_alert(cls, risk_status: dict, user_id: Optional[str] = None) -> "NotificationEvent":
        return cls(
            event_type=EventType.RISK_EMERGENCY_STOP,
            severity=EventSeverity.CRITICAL,
            user_id=user_id,
            title="🚨 Emergency Stop Activated",
            message=(f"All trading halted.\n"
                     f"Daily P&L: ₹{risk_status.get('daily_pnl',0):,.0f}\n"
                     f"Drawdown: {risk_status.get('current_drawdown',0)*100:.2f}%"),
            data=risk_status,
            source="risk_manager",
        )


class DeliveryRecord(BaseModel):
    """Immutable log of every notification send attempt."""
    id:           str = Field(default_factory=lambda: str(uuid4()))
    event_id:     str
    channel_id:   str
    user_id:      str
    provider:     ProviderType
    status:       DeliveryStatus = DeliveryStatus.PENDING
    message_id:   Optional[str] = None   # Provider-returned message ID
    error:        Optional[str] = None
    attempts:     int = 0
    sent_at:      Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationRule(BaseModel):
    """
    User-configured rule: when event X happens, notify via channel Y.

    Example:
        If RISK_EMERGENCY_STOP → send to all my channels immediately
        If SIGNAL_BUY && severity >= WARNING → send to Telegram only
    """
    id:             str = Field(default_factory=lambda: str(uuid4()))
    user_id:        str
    name:           str
    enabled:        bool = True

    event_types:    list[EventType]     = Field(default_factory=list)  # [] = all events
    min_severity:   EventSeverity       = EventSeverity.INFO
    channel_ids:    list[str]           = Field(default_factory=list)  # [] = all channels
    providers:      list[ProviderType]  = Field(default_factory=list)  # filter by provider

    # Throttle: don't send same event_type more than once per N seconds
    throttle_s:     int = 0

    # Quiet hours (user's local time)
    quiet_hours_start: Optional[int] = None  # 0-23
    quiet_hours_end:   Optional[int] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationPreference(BaseModel):
    """Per-user global notification preferences."""
    user_id:         str
    enabled:         bool = True
    quiet_hours_start: Optional[int] = None  # Hour 0-23
    quiet_hours_end:   Optional[int] = None
    timezone_str:    str = "Asia/Kolkata"
    digest_mode:     bool = False      # Batch non-critical alerts
    digest_interval_m: int = 60       # Digest every N minutes
    max_per_hour:    int = 50          # Hard rate limit
    created_at:      datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
