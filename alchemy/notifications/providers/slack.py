"""
alchemy.notifications.providers.slack
=======================================
Slack Incoming Webhook notification provider.

Setup:
  1. Go to https://api.slack.com/apps → Create New App → From Scratch
  2. Name: "Alchemy Alerts", pick your workspace
  3. Left sidebar → Incoming Webhooks → Activate → Add New Webhook
  4. Select a channel (e.g., #trading-alerts) → Allow
  5. Copy the Webhook URL
  6. Enter it in Alchemy → Notifications → Add Channel → Slack

Docs: https://api.slack.com/messaging/webhooks
"""
from __future__ import annotations

from typing import Any

import structlog

from alchemy.notifications.base import (
    BaseNotificationProvider, ConfigField, SendResult,
)
from alchemy.notifications.models import (
    DeliveryStatus, EventSeverity, NotificationChannel,
    NotificationEvent, ProviderType,
)

log = structlog.get_logger(__name__)

# Map severity to Slack color (left bar on attachment)
_SEVERITY_COLOR = {
    EventSeverity.INFO:     "#36a64f",
    EventSeverity.SUCCESS:  "#2eb886",
    EventSeverity.WARNING:  "#daa038",
    EventSeverity.CRITICAL: "#cc0000",
}


class SlackProvider(BaseNotificationProvider):
    """
    Slack Incoming Webhook provider.

    Sends rich Block Kit messages with color-coded severity,
    key data fields, and an optional action button.

    Config keys:
        webhook_url — Slack Incoming Webhook URL
        channel     — Override channel (optional, e.g., "#alerts")
        username    — Bot display name (default: "Alchemy")
        icon_emoji  — Bot icon (default: ":robot_face:")
    """

    provider_type = ProviderType.SLACK
    display_name  = "Slack"
    emoji_icon    = "💬"

    config_fields = [
        ConfigField(
            key="webhook_url",
            label="Webhook URL",
            placeholder="https://hooks.slack.com/services/T00/B00/xxxx",
            required=True,
            secret=True,
            help_text="Incoming Webhook URL from your Slack app settings",
        ),
        ConfigField(
            key="channel",
            label="Channel Override",
            placeholder="#trading-alerts",
            required=False,
            help_text="Override the default channel (optional)",
        ),
        ConfigField(
            key="username",
            label="Bot Username",
            placeholder="Alchemy",
            required=False,
            help_text="Display name for the bot (default: Alchemy)",
        ),
        ConfigField(
            key="icon_emoji",
            label="Bot Icon",
            placeholder=":robot_face:",
            required=False,
            help_text="Emoji icon for the bot (default: :robot_face:)",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "webhook_url")
        url = config["webhook_url"]
        if not url.startswith("https://hooks.slack.com/"):
            raise ValueError(
                "webhook_url must start with https://hooks.slack.com/"
            )

    async def send(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        try:
            import httpx

            webhook_url = channel.config["webhook_url"]
            username    = channel.config.get("username", "Alchemy")
            icon_emoji  = channel.config.get("icon_emoji", ":robot_face:")

            payload = self._build_payload(event, username, icon_emoji)

            # Optional channel override
            override_channel = channel.config.get("channel")
            if override_channel:
                payload["channel"] = override_channel

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)

            if resp.status_code == 200:
                log.info("slack.sent", event=event.event_type.value)
                return SendResult(
                    success=True,
                    provider="slack",
                    message_id=f"slack-{event.id[:8]}",
                    status=DeliveryStatus.DELIVERED,
                )
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                log.error("slack.send_failed", error=error)
                return SendResult(
                    success=False,
                    provider="slack",
                    error=error,
                    status=DeliveryStatus.FAILED,
                )

        except ImportError:
            return SendResult(
                success=False, provider="slack",
                error="httpx not installed: pip install httpx",
                status=DeliveryStatus.FAILED,
            )
        except Exception as e:
            log.error("slack.exception", error=str(e))
            return SendResult(
                success=False, provider="slack",
                error=str(e), status=DeliveryStatus.FAILED,
            )

    def _build_payload(
        self,
        event: NotificationEvent,
        username: str,
        icon_emoji: str,
    ) -> dict:
        """Build Slack message payload with attachments."""
        from alchemy.notifications.base import SEVERITY_EMOJI

        emoji = SEVERITY_EMOJI.get(event.severity, "📣")
        color = _SEVERITY_COLOR.get(event.severity, "#36a64f")
        title = event.title.replace("🟢", "").replace("🔴", "").replace("🟡", "").strip()

        # Build fields from event data
        fields = []
        important_keys = (
            "ticker", "symbol", "side", "qty", "fill_price",
            "pnl", "exchange", "strategy", "status", "workflow_id",
        )
        for k, v in event.data.items():
            if k in important_keys and v is not None:
                fields.append({
                    "title": k.replace("_", " ").title(),
                    "value": str(v),
                    "short": True,
                })

        attachment = {
            "color":      color,
            "title":      f"{emoji} {title}",
            "text":       event.message,
            "fields":     fields[:8],  # Slack limit
            "footer":     "Alchemy Trading Platform",
            "footer_icon": "https://cdn-icons-png.flaticon.com/512/2991/2991148.png",
            "ts":         int(event.created_at.timestamp()),
        }

        return {
            "username":   username,
            "icon_emoji": icon_emoji,
            "attachments": [attachment],
        }

    def get_setup_instructions(self) -> str:
        return (
            "1. Go to https://api.slack.com/apps → Create New App → From Scratch\n"
            "2. Name: 'Alchemy Alerts', pick your workspace\n"
            "3. Left sidebar → Incoming Webhooks → Toggle Activate to On\n"
            "4. Click 'Add New Webhook to Workspace'\n"
            "5. Select a channel (e.g., #trading-alerts) → Allow\n"
            "6. Copy the Webhook URL and paste it above"
        )
