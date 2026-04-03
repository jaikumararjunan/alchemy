"""
alchemy.notifications.base
===========================
Abstract base class for all notification providers.

To add a new notification channel:
  1. Create alchemy/notifications/providers/{name}.py
  2. Inherit from BaseNotificationProvider
  3. Implement: send(), validate_config(), format_message()
  4. Register in alchemy/notifications/providers/registry.py

That's it — the dispatcher picks it up automatically.

Example (adding Discord in 5 minutes):
    # providers/discord.py
    class DiscordProvider(BaseNotificationProvider):
        provider_type = ProviderType.DISCORD
        display_name  = "Discord"
        config_fields = [ConfigField("webhook_url", "Webhook URL", required=True)]

        async def send(self, channel, event):
            import httpx
            await httpx.AsyncClient().post(channel.config["webhook_url"],
                json={"content": self.format_message(event, "plain")})
            return SendResult(success=True, provider="discord")

        def validate_config(self, config):
            if "webhook_url" not in config: raise ValueError("webhook_url required")
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from alchemy.notifications.models import (
    DeliveryStatus, EventSeverity, EventType, NotificationChannel,
    NotificationEvent, ProviderType
)


@dataclass
class SendResult:
    """Result of a send() call."""
    success:      bool
    provider:     str
    message_id:   Optional[str] = None
    error:        Optional[str] = None
    status:       DeliveryStatus = DeliveryStatus.SENT
    raw_response: dict = field(default_factory=dict)


@dataclass
class ConfigField:
    """Describes a required/optional config field for UI rendering."""
    key:         str
    label:       str
    placeholder: str     = ""
    required:    bool    = True
    secret:      bool    = False   # Mask in UI
    help_text:   str     = ""
    field_type:  str     = "text"  # text | select | toggle | phone


# Emoji prefix for severity levels
SEVERITY_EMOJI = {
    EventSeverity.INFO:     "ℹ️",
    EventSeverity.SUCCESS:  "✅",
    EventSeverity.WARNING:  "⚠️",
    EventSeverity.CRITICAL: "🚨",
}

# Max message lengths per provider
MAX_LENGTH = {
    ProviderType.SMS:      160,
    ProviderType.TELEGRAM: 4096,
    ProviderType.WHATSAPP: 1600,
    ProviderType.EMAIL:    None,
    ProviderType.SLACK:    3000,
    ProviderType.DISCORD:  2000,
    ProviderType.WEBHOOK:  None,
}


class BaseNotificationProvider(ABC):
    """
    Abstract base for all notification providers.

    Subclasses MUST define:
        provider_type: ProviderType
        display_name:  str
        config_fields: list[ConfigField]

    Subclasses MUST implement:
        send(channel, event) -> SendResult
        validate_config(config) -> None  (raise ValueError on invalid)
    """

    # Subclass must set these
    provider_type: ProviderType
    display_name:  str
    config_fields: list[ConfigField] = []
    emoji_icon:    str = "📣"

    # ── Must implement ────────────────────────────────────────────────────────

    @abstractmethod
    async def send(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        """Send a notification. Returns SendResult — never raises."""
        ...

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate provider config. Raises ValueError with human-readable message."""
        ...

    # ── May override ──────────────────────────────────────────────────────────

    def format_message(self, event: NotificationEvent, style: str = "markdown") -> str:
        """
        Format an event into provider-appropriate text.

        Styles:
            markdown — Telegram/Discord-flavoured markdown
            plain    — SMS/WhatsApp plain text
            html     — Email HTML
        """
        emoji = SEVERITY_EMOJI.get(event.severity, "📣")
        max_len = MAX_LENGTH.get(getattr(self, 'provider_type', None))

        if style == "markdown":
            text = f"{emoji} *{event.title}*\n\n{event.message}"
            if event.data:
                extras = [f"• {k}: `{v}`" for k, v in event.data.items()
                          if k not in ("run_id",) and v is not None]
                if extras:
                    text += "\n\n" + "\n".join(extras[:5])
        elif style == "html":
            text = f"<b>{emoji} {event.title}</b><br><br>{event.message.replace(chr(10),'<br>')}"
        else:  # plain
            # Strip markdown for SMS
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', event.message)
            text = re.sub(r'\*(.+?)\*',     r'\1', text)
            text = f"{emoji} {event.title}\n{text}"

        if max_len and len(text) > max_len:
            text = text[:max_len - 3] + "..."
        return text

    async def test_connection(self, config: dict[str, Any]) -> SendResult:
        """Send a test notification to verify config. Default implementation."""
        channel = NotificationChannel(
            user_id="test",
            provider=self.provider_type,
            name="Test",
            config=config,
        )
        test_event = NotificationEvent(
            event_type=EventType.CUSTOM,
            severity=EventSeverity.INFO,
            title=f"🔮 Alchemy Test — {self.display_name}",
            message="✅ Notification channel connected successfully! You will receive trading alerts here.",
            source="test",
        )
        return await self.send(channel, test_event)

    def get_setup_instructions(self) -> str:
        """Return human-readable setup instructions. Override in subclass."""
        return f"Configure your {self.display_name} credentials below."

    def required_fields(self) -> list[str]:
        return [f.key for f in self.config_fields if f.required]

    def _check_required(self, config: dict, *keys: str) -> None:
        missing = [k for k in keys if not config.get(k)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
