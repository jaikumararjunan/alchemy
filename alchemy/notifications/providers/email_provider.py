"""
alchemy.notifications.providers.email_provider
================================================
Gmail / SMTP email notification provider.

Setup:
  1. Enable 2-Step Verification on your Google Account
  2. Go to https://myaccount.google.com/apppasswords
  3. Generate an App Password for "Mail"
  4. Use your Gmail address as smtp_user and the App Password as smtp_password

Supports: Gmail, Outlook, SendGrid, AWS SES, any SMTP server.

Docs: https://support.google.com/mail/answer/185833
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

from alchemy.notifications.base import (
    BaseNotificationProvider, ConfigField, SendResult,
)
from alchemy.notifications.models import (
    DeliveryStatus, NotificationChannel, NotificationEvent, ProviderType,
)

log = structlog.get_logger(__name__)


# ── HTML email template for trade alerts ────────────────────────────────────

ALERT_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Inter,ui-sans-serif,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:40px 20px">
<table width="520" cellpadding="0" cellspacing="0"
  style="background:#1e293b;border-radius:16px;border:1px solid #334155;overflow:hidden">
  <tr><td style="padding:24px 32px;background:linear-gradient(135deg,#1e40af,#7c3aed)">
    <div style="font-size:24px;font-weight:800;color:#fff;letter-spacing:-0.5px">
      {severity_emoji} {title}
    </div>
    <div style="color:#93c5fd;font-size:12px;margin-top:4px">Alchemy AI Trading Platform</div>
  </td></tr>
  <tr><td style="padding:28px 32px">
    <p style="color:#e2e8f0;font-size:14px;line-height:1.7;margin:0 0 20px;white-space:pre-line">{message}</p>
    {data_rows}
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #334155">
      <p style="color:#64748b;font-size:11px;margin:0">
        Sent by Alchemy Notification Engine &middot; {timestamp}
      </p>
    </div>
  </td></tr>
</table></td></tr></table></body></html>
"""

DATA_ROW = (
    '<div style="display:inline-block;background:#0f172a;border:1px solid #334155;'
    'border-radius:8px;padding:8px 14px;margin:3px 4px 3px 0">'
    '<span style="color:#64748b;font-size:11px">{key}</span><br>'
    '<span style="color:#f1f5f9;font-size:14px;font-weight:600">{value}</span>'
    '</div>'
)


class EmailProvider(BaseNotificationProvider):
    """
    SMTP email notification provider.

    Sends rich HTML emails for trade alerts, risk events, and system notifications.
    Works with Gmail (App Passwords), Outlook, SendGrid, AWS SES, etc.

    Config keys:
        smtp_host     — SMTP server hostname (default: smtp.gmail.com)
        smtp_port     — SMTP port (default: 587 for TLS)
        smtp_user     — Email address / username
        smtp_password — Password or App Password
        from_address  — From address (defaults to smtp_user)
        to_address    — Recipient email address
    """

    provider_type = ProviderType.EMAIL
    display_name  = "Email (Gmail/SMTP)"
    emoji_icon    = "📧"

    config_fields = [
        ConfigField(
            key="smtp_host",
            label="SMTP Host",
            placeholder="smtp.gmail.com",
            required=False,
            help_text="SMTP server (default: smtp.gmail.com)",
        ),
        ConfigField(
            key="smtp_port",
            label="SMTP Port",
            placeholder="587",
            required=False,
            help_text="587 for TLS, 465 for SSL",
        ),
        ConfigField(
            key="smtp_user",
            label="Email / Username",
            placeholder="you@gmail.com",
            required=True,
            secret=False,
            help_text="Your email address or SMTP username",
        ),
        ConfigField(
            key="smtp_password",
            label="Password / App Password",
            placeholder="xxxx xxxx xxxx xxxx",
            required=True,
            secret=True,
            help_text="Gmail: use App Password (myaccount.google.com/apppasswords)",
        ),
        ConfigField(
            key="from_address",
            label="From Address",
            placeholder="alchemy@yourdomain.com",
            required=False,
            help_text="Defaults to your email address",
        ),
        ConfigField(
            key="to_address",
            label="Recipient Email",
            placeholder="alerts@yourdomain.com",
            required=True,
            secret=False,
            help_text="Where to send notifications",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "smtp_user", "smtp_password", "to_address")
        if "@" not in config.get("smtp_user", ""):
            raise ValueError("smtp_user should be a valid email address")
        if "@" not in config.get("to_address", ""):
            raise ValueError("to_address should be a valid email address")

    async def send(
        self,
        channel: NotificationChannel,
        event: NotificationEvent,
    ) -> SendResult:
        try:
            host = channel.config.get("smtp_host", "smtp.gmail.com")
            port = int(channel.config.get("smtp_port", "587"))
            user = channel.config["smtp_user"]
            password = channel.config["smtp_password"]
            from_addr = channel.config.get("from_address", user)
            to_addr = channel.config["to_address"]

            subject, html_body = self._format_email(event)

            # Build MIME message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Alchemy Trading <{from_addr}>"
            msg["To"] = to_addr

            # Plain text fallback
            plain = f"{event.title}\n\n{event.message}"
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_smtp, host, port, user, password, from_addr, to_addr, msg,
            )

            log.info("email.sent", to=to_addr, subject=subject)
            return SendResult(
                success=True,
                provider="email",
                message_id=f"email-{event.created_at.timestamp():.0f}",
                status=DeliveryStatus.DELIVERED,
            )

        except Exception as e:
            log.error("email.send_failed", error=str(e))
            return SendResult(
                success=False,
                provider="email",
                error=str(e),
                status=DeliveryStatus.FAILED,
            )

    @staticmethod
    def _send_smtp(
        host: str, port: int, user: str, password: str,
        from_addr: str, to_addr: str, msg: MIMEMultipart,
    ) -> None:
        """Synchronous SMTP send (run in executor)."""
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx) as server:
                server.login(user, password)
                server.sendmail(from_addr, to_addr, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, to_addr, msg.as_string())

    def _format_email(self, event: NotificationEvent) -> tuple[str, str]:
        """Format event into email subject + HTML body."""
        from alchemy.notifications.base import SEVERITY_EMOJI
        emoji = SEVERITY_EMOJI.get(event.severity, "📣")

        subject = f"[Alchemy] {event.title}"

        # Build data rows for key fields
        important = {
            k: v for k, v in event.data.items()
            if k in (
                "symbol", "ticker", "strategy", "direction",
                "entry_price", "fill_price", "stop_loss", "take_profit",
                "pnl", "confidence", "status", "workflow_id",
            ) and v is not None
        }
        data_rows_html = ""
        if important:
            data_rows_html = '<div style="margin-top:16px">'
            for k, v in list(important.items())[:8]:
                label = k.replace("_", " ").title()
                val = f"${v:,.2f}" if isinstance(v, float) else str(v)
                data_rows_html += DATA_ROW.format(key=label, value=val)
            data_rows_html += "</div>"

        html = ALERT_HTML.format(
            severity_emoji=emoji,
            title=event.title.replace("🟢", "").replace("🔴", "").replace("🟡", "").strip(),
            message=event.message,
            data_rows=data_rows_html,
            timestamp=event.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        return subject, html

    def get_setup_instructions(self) -> str:
        return (
            "1. Go to your Google Account settings\n"
            "2. Enable 2-Step Verification if not already enabled\n"
            "3. Go to https://myaccount.google.com/apppasswords\n"
            "4. Select 'Mail' and generate an App Password\n"
            "5. Copy the 16-character password (e.g. 'abcd efgh ijkl mnop')\n"
            "6. Enter your Gmail address as 'Email' and the App Password above\n"
            "7. Set the recipient email where you want to receive alerts\n"
            "8. Click Test Connection to verify"
        )
