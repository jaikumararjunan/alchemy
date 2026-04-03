"""
alchemy.notifications.providers.whatsapp
==========================================
WhatsApp notification provider.

Supports two backends:
  1. Twilio WhatsApp API (recommended — easy setup, sandbox available)
  2. Meta Cloud API (official, requires Business verification)

Twilio Setup:
  1. Sign up at twilio.com → get Account SID + Auth Token
  2. Enable WhatsApp Sandbox: console.twilio.com/develop/sms/try-it-out/whatsapp-learn
  3. Send "join <keyword>" to +1 415 523 8886 to join the sandbox
  4. Your WhatsApp number must be in E.164 format: +919876543210

Meta Cloud API Setup:
  1. Create a Meta Business account
  2. Set up WhatsApp Business Platform
  3. Get Phone Number ID + Access Token from developers.facebook.com
  4. Add recipient's phone number to test numbers

Docs:
  Twilio: https://www.twilio.com/docs/whatsapp
  Meta:   https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

from typing import Any, Literal

import structlog

from alchemy.notifications.base import (
    BaseNotificationProvider, ConfigField, SendResult
)
from alchemy.notifications.models import (
    DeliveryStatus, NotificationChannel, NotificationEvent, ProviderType
)

log = structlog.get_logger(__name__)

Backend = Literal["twilio", "meta"]


class WhatsAppProvider(BaseNotificationProvider):
    """
    WhatsApp provider supporting Twilio (default) and Meta Cloud API.

    Config for Twilio backend:
        backend        — "twilio"
        account_sid    — Twilio Account SID (starts with AC...)
        auth_token     — Twilio Auth Token
        from_number    — Twilio WhatsApp number (e.g. "whatsapp:+14155238886")
        to_number      — Recipient WhatsApp number (e.g. "+919876543210")

    Config for Meta Cloud API backend:
        backend        — "meta"
        access_token   — Meta System User Access Token
        phone_number_id — WhatsApp Business Phone Number ID
        to_number      — Recipient phone number in E.164 format
    """

    provider_type = ProviderType.WHATSAPP
    display_name  = "WhatsApp"
    emoji_icon    = "💬"

    config_fields = [
        ConfigField(
            key="backend",
            label="API Provider",
            required=True,
            field_type="select",
            help_text="Choose Twilio (easier) or Meta Cloud API (official)",
        ),
        ConfigField(
            key="to_number",
            label="Your WhatsApp Number",
            placeholder="+919876543210",
            required=True,
            field_type="phone",
            help_text="Your phone number in E.164 format (+country code + number)",
        ),
        ConfigField(
            key="account_sid",
            label="Twilio Account SID",
            placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            required=False,
            secret=True,
            help_text="From Twilio console (only for Twilio backend)",
        ),
        ConfigField(
            key="auth_token",
            label="Twilio Auth Token",
            required=False,
            secret=True,
            help_text="From Twilio console (only for Twilio backend)",
        ),
        ConfigField(
            key="from_number",
            label="Twilio WhatsApp From",
            placeholder="whatsapp:+14155238886",
            required=False,
            help_text="Twilio sandbox: whatsapp:+14155238886",
        ),
        ConfigField(
            key="access_token",
            label="Meta Access Token",
            required=False,
            secret=True,
            help_text="Meta System User token (only for Meta backend)",
        ),
        ConfigField(
            key="phone_number_id",
            label="Meta Phone Number ID",
            required=False,
            help_text="WhatsApp Business Phone Number ID from Meta console",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "to_number", "backend")
        to = config["to_number"]
        if not to.startswith("+"):
            raise ValueError("to_number must be in E.164 format starting with + (e.g. +919876543210)")

        backend = config.get("backend", "twilio")
        if backend == "twilio":
            self._check_required(config, "account_sid", "auth_token", "from_number")
        elif backend == "meta":
            self._check_required(config, "access_token", "phone_number_id")
        else:
            raise ValueError(f"Unknown backend: {backend}. Use 'twilio' or 'meta'")

    async def send(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        backend = channel.config.get("backend", "twilio")
        if backend == "twilio":
            return await self._send_twilio(channel, event)
        elif backend == "meta":
            return await self._send_meta(channel, event)
        else:
            return SendResult(
                success=False, provider="whatsapp",
                error=f"Unknown backend: {backend}", status=DeliveryStatus.FAILED,
            )

    async def _send_twilio(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        try:
            import httpx, base64

            sid       = channel.config["account_sid"]
            token     = channel.config["auth_token"]
            from_num  = channel.config.get("from_number", "whatsapp:+14155238886")
            to_num    = channel.config["to_number"]
            if not to_num.startswith("whatsapp:"):
                to_num = f"whatsapp:{to_num}"

            body = self.format_message(event, "plain")
            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    headers={"Authorization": f"Basic {auth}"},
                    data={"From": from_num, "To": to_num, "Body": body},
                )
                data = resp.json()

            if resp.status_code == 201:
                log.info("whatsapp.twilio_sent", to=to_num, sid=data.get("sid"))
                return SendResult(
                    success=True, provider="whatsapp",
                    message_id=data.get("sid"),
                    status=DeliveryStatus.SENT,
                    raw_response=data,
                )
            else:
                error = data.get("message", f"HTTP {resp.status_code}")
                log.error("whatsapp.twilio_failed", error=error)
                return SendResult(
                    success=False, provider="whatsapp",
                    error=error, status=DeliveryStatus.FAILED, raw_response=data,
                )

        except ImportError:
            return SendResult(success=False, provider="whatsapp",
                              error="httpx not installed", status=DeliveryStatus.FAILED)
        except Exception as e:
            log.error("whatsapp.twilio_exception", error=str(e))
            return SendResult(success=False, provider="whatsapp",
                              error=str(e), status=DeliveryStatus.FAILED)

    async def _send_meta(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        try:
            import httpx

            access_token    = channel.config["access_token"]
            phone_number_id = channel.config["phone_number_id"]
            to_number       = channel.config["to_number"].lstrip("+")   # Meta expects no +

            body = self.format_message(event, "plain")

            url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type":    "individual",
                "to":                to_number,
                "type":              "text",
                "text":              {"preview_url": False, "body": body},
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
                data = resp.json()

            if resp.status_code == 200 and "messages" in data:
                msg_id = data["messages"][0].get("id")
                log.info("whatsapp.meta_sent", to=to_number, msg_id=msg_id)
                return SendResult(
                    success=True, provider="whatsapp",
                    message_id=msg_id, status=DeliveryStatus.SENT, raw_response=data,
                )
            else:
                error = str(data.get("error", {}).get("message", f"HTTP {resp.status_code}"))
                log.error("whatsapp.meta_failed", error=error)
                return SendResult(
                    success=False, provider="whatsapp",
                    error=error, status=DeliveryStatus.FAILED, raw_response=data,
                )

        except ImportError:
            return SendResult(success=False, provider="whatsapp",
                              error="httpx not installed", status=DeliveryStatus.FAILED)
        except Exception as e:
            log.error("whatsapp.meta_exception", error=str(e))
            return SendResult(success=False, provider="whatsapp",
                              error=str(e), status=DeliveryStatus.FAILED)

    def get_setup_instructions(self) -> str:
        return (
            "Twilio (Recommended for testing):\n"
            "1. Sign up at twilio.com and get Account SID + Auth Token\n"
            "2. Go to console.twilio.com → Messaging → Try it out → Send a WhatsApp message\n"
            "3. Send 'join <keyword>' from your WhatsApp to +1 415 523 8886\n"
            "4. Enter your Twilio credentials and your WhatsApp number above\n\n"
            "Meta Cloud API:\n"
            "1. Create a Meta Business account at developers.facebook.com\n"
            "2. Set up WhatsApp Business Platform\n"
            "3. Get Phone Number ID and System User Access Token\n"
            "4. Add your phone number to test recipients"
        )
