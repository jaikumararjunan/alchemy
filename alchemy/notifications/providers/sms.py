"""
alchemy.notifications.providers.sms
=====================================
SMS notification provider.

Supports three SMS backends:
  1. Twilio  — Global, reliable, easy sandbox
  2. MSG91   — India-optimised, DLT registered, transactional SMS
  3. AWS SNS — Good for AWS deployments, 200+ countries

India DLT (Distributed Ledger Technology) Note:
  TRAI mandates DLT registration for commercial SMS in India.
  MSG91 handles DLT natively. For Twilio, register your template separately.

Docs:
  Twilio: https://www.twilio.com/docs/sms
  MSG91:  https://docs.msg91.com/
  SNS:    https://docs.aws.amazon.com/sns/latest/dg/sms_publish-to-phone.html
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

Backend = Literal["twilio", "msg91", "aws_sns"]


class SMSProvider(BaseNotificationProvider):
    """
    Multi-backend SMS provider.

    Config for Twilio:
        backend     — "twilio"
        account_sid — Twilio Account SID
        auth_token  — Twilio Auth Token
        from_number — Twilio phone number (e.g. "+12015551234")
        to_number   — Recipient in E.164 format

    Config for MSG91 (India recommended):
        backend    — "msg91"
        api_key    — MSG91 Auth Key
        sender_id  — 6-char DLT registered sender ID (e.g. "ALCHMY")
        template_id — DLT registered template ID
        to_number  — Recipient mobile (10 digits or E.164)

    Config for AWS SNS:
        backend          — "aws_sns"
        aws_access_key   — AWS Access Key ID
        aws_secret_key   — AWS Secret Access Key
        aws_region       — AWS region (e.g. "ap-south-1")
        to_number        — Recipient in E.164 format
        sender_id        — SMS Sender ID (optional)
    """

    provider_type = ProviderType.SMS
    display_name  = "SMS"
    emoji_icon    = "📱"

    config_fields = [
        ConfigField(
            key="backend",
            label="SMS Provider",
            required=True,
            field_type="select",
            help_text="twilio | msg91 | aws_sns",
        ),
        ConfigField(
            key="to_number",
            label="Mobile Number",
            placeholder="+919876543210",
            required=True,
            field_type="phone",
            help_text="E.164 format: +[country][number]",
        ),
        # Twilio fields
        ConfigField(key="account_sid", label="Twilio Account SID",
                    required=False, secret=True),
        ConfigField(key="auth_token",  label="Twilio Auth Token",
                    required=False, secret=True),
        ConfigField(key="from_number", label="Twilio From Number",
                    placeholder="+12015551234", required=False),
        # MSG91 fields
        ConfigField(key="api_key",     label="MSG91 Auth Key",
                    required=False, secret=True),
        ConfigField(key="sender_id",   label="Sender ID (DLT)",
                    placeholder="ALCHMY", required=False,
                    help_text="6-char DLT registered sender ID"),
        ConfigField(key="template_id", label="DLT Template ID",
                    required=False,
                    help_text="DLT registered template ID for India"),
        # AWS SNS fields
        ConfigField(key="aws_access_key", label="AWS Access Key",
                    required=False, secret=True),
        ConfigField(key="aws_secret_key", label="AWS Secret Key",
                    required=False, secret=True),
        ConfigField(key="aws_region",     label="AWS Region",
                    placeholder="ap-south-1", required=False),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "to_number", "backend")
        backend = config.get("backend", "twilio")

        if backend == "twilio":
            self._check_required(config, "account_sid", "auth_token", "from_number")
        elif backend == "msg91":
            self._check_required(config, "api_key", "sender_id")
        elif backend == "aws_sns":
            self._check_required(config, "aws_access_key", "aws_secret_key", "aws_region")
        else:
            raise ValueError(f"Unknown SMS backend: {backend}. Use twilio | msg91 | aws_sns")

        to = config["to_number"]
        if not to.startswith("+") and not to.isdigit():
            raise ValueError("to_number must be in E.164 format (+919876543210) or 10-digit mobile")

    async def send(
        self,
        channel: NotificationChannel,
        event:   NotificationEvent,
    ) -> SendResult:
        backend = channel.config.get("backend", "twilio")
        dispatch = {
            "twilio":  self._send_twilio,
            "msg91":   self._send_msg91,
            "aws_sns": self._send_sns,
        }
        handler = dispatch.get(backend)
        if not handler:
            return SendResult(success=False, provider="sms",
                              error=f"Unknown backend: {backend}", status=DeliveryStatus.FAILED)
        return await handler(channel, event)

    async def _send_twilio(self, channel: NotificationChannel, event: NotificationEvent) -> SendResult:
        try:
            import httpx, base64

            sid      = channel.config["account_sid"]
            token    = channel.config["auth_token"]
            from_num = channel.config["from_number"]
            to_num   = self._normalise_number(channel.config["to_number"])
            body     = self.format_message(event, "plain")[:160]

            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    headers={"Authorization": f"Basic {auth}"},
                    data={"From": from_num, "To": to_num, "Body": body},
                )
                data = resp.json()

            if resp.status_code == 201:
                log.info("sms.twilio_sent", to=to_num, sid=data.get("sid"))
                return SendResult(success=True, provider="sms",
                                  message_id=data.get("sid"),
                                  status=DeliveryStatus.SENT, raw_response=data)
            else:
                error = data.get("message", f"HTTP {resp.status_code}")
                return SendResult(success=False, provider="sms",
                                  error=error, status=DeliveryStatus.FAILED, raw_response=data)

        except Exception as e:
            log.error("sms.twilio_exception", error=str(e))
            return SendResult(success=False, provider="sms",
                              error=str(e), status=DeliveryStatus.FAILED)

    async def _send_msg91(self, channel: NotificationChannel, event: NotificationEvent) -> SendResult:
        """
        MSG91 REST API v2 — preferred for India.
        Supports DLT-registered templates for compliance.
        """
        try:
            import httpx

            api_key     = channel.config["api_key"]
            sender_id   = channel.config.get("sender_id", "ALCHMY")
            template_id = channel.config.get("template_id", "")
            to_num      = self._normalise_number(channel.config["to_number"], strip_plus=True)
            body        = self.format_message(event, "plain")[:160]

            payload: dict = {
                "sender":   sender_id,
                "route":    "4",         # Transactional route
                "country":  "91",        # India
                "sms": [{
                    "message": body,
                    "to":      [to_num],
                }],
            }
            if template_id:
                payload["DLT_TE_ID"] = template_id

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.msg91.com/api/v2/sendsms",
                    headers={"authkey": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                data = resp.json()

            if data.get("type") == "success":
                log.info("sms.msg91_sent", to=to_num, msg_id=data.get("message"))
                return SendResult(success=True, provider="sms",
                                  message_id=data.get("message"),
                                  status=DeliveryStatus.SENT, raw_response=data)
            else:
                error = data.get("message", "MSG91 error")
                return SendResult(success=False, provider="sms",
                                  error=error, status=DeliveryStatus.FAILED, raw_response=data)

        except Exception as e:
            log.error("sms.msg91_exception", error=str(e))
            return SendResult(success=False, provider="sms",
                              error=str(e), status=DeliveryStatus.FAILED)

    async def _send_sns(self, channel: NotificationChannel, event: NotificationEvent) -> SendResult:
        """AWS SNS SMS publish."""
        try:
            import aioboto3  # type: ignore

            access_key = channel.config["aws_access_key"]
            secret_key = channel.config["aws_secret_key"]
            region     = channel.config.get("aws_region", "ap-south-1")
            sender_id  = channel.config.get("sender_id", "Alchemy")
            to_num     = self._normalise_number(channel.config["to_number"])
            body       = self.format_message(event, "plain")[:160]

            session = aioboto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            async with session.client("sns") as sns:
                resp = await sns.publish(
                    PhoneNumber=to_num,
                    Message=body,
                    MessageAttributes={
                        "AWS.SNS.SMS.SenderID":   {"DataType":"String","StringValue":sender_id},
                        "AWS.SNS.SMS.SMSType":    {"DataType":"String","StringValue":"Transactional"},
                    },
                )

            msg_id = resp.get("MessageId")
            log.info("sms.sns_sent", to=to_num, msg_id=msg_id)
            return SendResult(success=True, provider="sms",
                              message_id=msg_id, status=DeliveryStatus.SENT)

        except ImportError:
            return SendResult(success=False, provider="sms",
                              error="aioboto3 not installed: pip install aioboto3",
                              status=DeliveryStatus.FAILED)
        except Exception as e:
            log.error("sms.sns_exception", error=str(e))
            return SendResult(success=False, provider="sms",
                              error=str(e), status=DeliveryStatus.FAILED)

    def _normalise_number(self, number: str, strip_plus: bool = False) -> str:
        number = number.strip().replace(" ", "").replace("-", "")
        if not number.startswith("+"):
            if len(number) == 10:   # Indian 10-digit
                number = "+91" + number
            else:
                number = "+" + number
        return number.lstrip("+") if strip_plus else number

    def get_setup_instructions(self) -> str:
        return (
            "Twilio: Sign up at twilio.com, get Account SID + Auth Token + phone number.\n\n"
            "MSG91 (India recommended): Sign up at msg91.com.\n"
            "  Register your sender ID and templates on DLT portal (trai.gov.in/dlt).\n"
            "  Get your Auth Key from the MSG91 dashboard.\n\n"
            "AWS SNS: Create an IAM user with sns:Publish permission.\n"
            "  Get Access Key + Secret Key from AWS IAM console."
        )
