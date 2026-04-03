"""
alchemy.notifications.providers.telegram
==========================================
Telegram Bot API notification provider.

Setup:
  1. Open Telegram, search @BotFather
  2. Send /newbot, follow instructions → get bot_token
  3. Start a chat with your bot (required before it can message you)
  4. Get your chat_id: message @userinfobot or use /getChatId bot
  5. Enter bot_token + chat_id in the Alchemy notification settings

Group/Channel support:
  - Add bot to a group/channel
  - Get group chat_id (negative number, e.g. -100123456789)
  - Grant the bot "Send Messages" permission

Docs: https://core.telegram.org/bots/api
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import structlog

from alchemy.notifications.base import (
    BaseNotificationProvider, ConfigField, SendResult
)
from alchemy.notifications.models import (
    DeliveryStatus, NotificationChannel, NotificationEvent, ProviderType
)

log = structlog.get_logger(__name__)


class TelegramProvider(BaseNotificationProvider):
    """
    Telegram Bot API provider.

    Sends rich Markdown messages with inline keyboards for quick actions.
    Supports personal chats, groups, and channels.

    Config keys:
        bot_token  — Bot token from @BotFather (e.g. "5432198765:AAF...")
        chat_id    — Target chat ID (personal: positive int, group: negative int)
        parse_mode — "MarkdownV2" | "HTML" (default: MarkdownV2)
        silent     — True = send without sound notification
    """

    provider_type = ProviderType.TELEGRAM
    display_name  = "Telegram"
    emoji_icon    = "✈️"

    config_fields = [
        ConfigField(
            key="bot_token",
            label="Bot Token",
            placeholder="5432198765:AAFr8k...",
            required=True,
            secret=True,
            help_text="Get from @BotFather on Telegram → /newbot",
        ),
        ConfigField(
            key="chat_id",
            label="Chat ID",
            placeholder="123456789",
            required=True,
            secret=False,
            help_text="Your Telegram user ID or group/channel ID. Message @userinfobot to find it.",
        ),
        ConfigField(
            key="parse_mode",
            label="Parse Mode",
            placeholder="MarkdownV2",
            required=False,
            field_type="select",
            help_text="Message formatting style",
        ),
        ConfigField(
            key="silent",
            label="Silent Notifications",
            required=False,
            field_type="toggle",
            help_text="Send without sound",
        ),
    ]

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "bot_token", "chat_id")
        token = config["bot_token"]
        if ":" not in token or len(token) < 30:
            raise ValueError(
                "bot_token looks invalid. It should look like '5432198765:AAFr8kXY...'"
            )

    async def send(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        try:
            import httpx
            token     = channel.config["bot_token"]
            chat_id   = channel.config["chat_id"]
            parse_mode = channel.config.get("parse_mode", "MarkdownV2")
            silent    = channel.config.get("silent", False)

            text = self._format_telegram(event, parse_mode)

            payload = {
                "chat_id":              chat_id,
                "text":                 text,
                "parse_mode":           parse_mode,
                "disable_notification": silent,
                "disable_web_page_preview": True,
            }

            # Add inline keyboard for actionable events
            keyboard = self._build_keyboard(event)
            if keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}

            url = self.BASE_URL.format(token=token, method="sendMessage")

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            if resp.status_code == 200 and data.get("ok"):
                msg_id = str(data["result"]["message_id"])
                log.info("telegram.sent", chat_id=chat_id, msg_id=msg_id)
                return SendResult(
                    success=True, provider="telegram",
                    message_id=msg_id,
                    status=DeliveryStatus.DELIVERED,
                    raw_response=data,
                )
            else:
                error = data.get("description", f"HTTP {resp.status_code}")
                log.error("telegram.send_failed", chat_id=chat_id, error=error)
                return SendResult(
                    success=False, provider="telegram",
                    error=error, status=DeliveryStatus.FAILED,
                    raw_response=data,
                )

        except ImportError:
            return SendResult(
                success=False, provider="telegram",
                error="httpx not installed: pip install httpx",
                status=DeliveryStatus.FAILED,
            )
        except Exception as e:
            log.error("telegram.exception", error=str(e))
            return SendResult(
                success=False, provider="telegram",
                error=str(e), status=DeliveryStatus.FAILED,
            )

    def _format_telegram(self, event: NotificationEvent, parse_mode: str) -> str:
        """Format message with Telegram-specific markdown."""
        from alchemy.notifications.base import SEVERITY_EMOJI
        emoji = SEVERITY_EMOJI.get(event.severity, "📣")

        if parse_mode == "MarkdownV2":
            # MarkdownV2 requires escaping special chars
            def esc(t: str) -> str:
                for ch in r"_*[]()~`>#+-=|{}.!\\":
                    t = t.replace(ch, f"\\{ch}")
                return t

            title   = esc(event.title.replace("🟢","").replace("🔴","").replace("🟡","").strip())
            message = esc(event.message)
            text    = f"{emoji} *{title}*\n\n{message}"

            # Add key data fields
            important = {k: v for k, v in event.data.items()
                         if k in ("ticker","symbol","fill_price","pnl","workflow_id","status")
                         and v is not None}
            if important:
                text += "\n\n"
                for k, v in list(important.items())[:5]:
                    text += f"• {esc(k.replace('_',' ').title())}: `{esc(str(v))}`\n"

            text += f"\n_Alchemy • {esc(event.created_at.strftime('%H:%M:%S IST'))}_"
        else:
            # HTML
            text = (f"<b>{emoji} {event.title}</b>\n\n"
                    f"{event.message}\n\n"
                    f"<i>Alchemy • {event.created_at.strftime('%H:%M:%S IST')}</i>")

        return text[:4096]

    def _build_keyboard(self, event: NotificationEvent) -> list[list[dict]]:
        """Build inline keyboard for actionable events."""
        from alchemy.notifications.models import EventType
        keyboards = {
            EventType.RISK_EMERGENCY_STOP: [[
                {"text": "🔓 Clear Stop", "callback_data": "risk:clear_stop"},
                {"text": "📊 Dashboard", "url": "http://localhost:3000/risk"},
            ]],
            EventType.SIGNAL_BUY: [[
                {"text": "📈 View Signal", "url": "http://localhost:3000/signals"},
            ]],
            EventType.ORDER_FILLED: [[
                {"text": "📋 View Portfolio", "url": "http://localhost:3000/portfolio"},
            ]],
        }
        return keyboards.get(event.event_type, [])

    def get_setup_instructions(self) -> str:
        return (
            "1. Open Telegram and search for @BotFather\n"
            "2. Send /newbot and follow the instructions to create your bot\n"
            "3. Copy the bot token (looks like 5432198765:AAFr8k...)\n"
            "4. Start a chat with your new bot (click Start)\n"
            "5. Message @userinfobot to get your Chat ID\n"
            "6. Enter both values above and click Test Connection"
        )
