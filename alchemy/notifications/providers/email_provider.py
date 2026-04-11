"""
alchemy.notifications.providers.email_provider
================================================
Email notification provider using admin-configured SMTP server.

SMTP is configured ONCE by admin in .env:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=admin@yourdomain.com
    SMTP_PASSWORD=your-app-password
    SMTP_FROM=noreply@yourdomain.com

Users only provide their recipient email address when adding an email channel.
"""
from __future__ import annotations

import asyncio
import os
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


# ── Admin SMTP config from environment ──────────────────────────────────────

def _get_smtp_config() -> dict:
    """Read SMTP config from environment (set by admin in .env)."""
    return {
        "host":     os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.environ.get("SMTP_PORT", "587")),
        "user":     os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", ""),
        "enabled":  bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD")),
    }


# ── HTML email template ─────────────────────────────────────────────────────

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

    SMTP server is configured by admin in .env (SMTP_HOST, SMTP_USER, etc.)
    Users only need to provide their recipient email address.

    User config keys:
        to_address — Where to send notifications (user's email)
    """

    provider_type = ProviderType.EMAIL
    display_name  = "Email"
    emoji_icon    = "📧"

    config_fields = [
        ConfigField(
            key="to_address",
            label="Your Email Address",
            placeholder="you@example.com",
            required=True,
            secret=False,
            help_text="Email address where you want to receive notifications",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        self._check_required(config, "to_address")
        if "@" not in config.get("to_address", ""):
            raise ValueError("Please enter a valid email address")

        # Check admin SMTP is configured
        smtp = _get_smtp_config()
        if not smtp["enabled"]:
            raise ValueError(
                "Email notifications are not available yet. "
                "The server administrator needs to configure SMTP settings."
            )

    async def send(
        self,
        channel: NotificationChannel,
        event: NotificationEvent,
    ) -> SendResult:
        try:
            smtp = _get_smtp_config()

            if not smtp["enabled"]:
                return SendResult(
                    success=False, provider="email",
                    error="SMTP not configured by admin. Set SMTP_USER + SMTP_PASSWORD in .env",
                    status=DeliveryStatus.FAILED,
                )

            to_addr = channel.config["to_address"]
            subject, html_body = self._format_email(event)

            # Build MIME message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Alchemy Trading <{smtp['from_addr']}>"
            msg["To"] = to_addr

            plain = f"{event.title}\n\n{event.message}"
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send in thread pool
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._send_smtp,
                smtp["host"], smtp["port"], smtp["user"], smtp["password"],
                smtp["from_addr"], to_addr, msg,
            )

            log.info("email.sent", to=to_addr, subject=subject)
            return SendResult(
                success=True, provider="email",
                message_id=f"email-{event.created_at.timestamp():.0f}",
                status=DeliveryStatus.DELIVERED,
            )

        except Exception as e:
            log.error("email.send_failed", error=str(e))
            return SendResult(
                success=False, provider="email",
                error=str(e), status=DeliveryStatus.FAILED,
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

        important = {
            k: v for k, v in event.data.items()
            if k in (
                "symbol", "ticker", "strategy", "direction",
                "entry_price", "fill_price", "stop_loss", "take_profit",
                "pnl", "confidence", "status", "workflow_id",
            ) and v is not None
        }

        def _esc(text: str) -> str:
            import html as _html
            return _html.escape(str(text)).replace("{", "&#123;").replace("}", "&#125;")

        data_rows_html = ""
        if important:
            data_rows_html = '<div style="margin-top:16px">'
            for k, v in list(important.items())[:8]:
                label = k.replace("_", " ").title()
                val = f"${v:,.2f}" if isinstance(v, float) else str(v)
                data_rows_html += DATA_ROW.format(key=_esc(label), value=_esc(val))
            data_rows_html += "</div>"

        clean_title = event.title.replace("🟢", "").replace("🔴", "").replace("🟡", "").strip()
        html = ALERT_HTML.format(
            severity_emoji=emoji,
            title=_esc(clean_title),
            message=_esc(event.message),
            data_rows=data_rows_html,
            timestamp=event.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        return subject, html

    def get_setup_instructions(self) -> str:
        smtp = _get_smtp_config()
        if smtp["enabled"]:
            return (
                f"Email notifications are configured and ready!\n"
                f"Server: {smtp['host']}:{smtp['port']}\n"
                f"From: {smtp['from_addr']}\n\n"
                f"Just enter your email address above to receive notifications."
            )
        return (
            "Email notifications are not yet configured.\n"
            "Ask your administrator to set these in the server .env file:\n"
            "  SMTP_HOST=smtp.gmail.com\n"
            "  SMTP_PORT=587\n"
            "  SMTP_USER=admin@domain.com\n"
            "  SMTP_PASSWORD=app-password\n"
            "  SMTP_FROM=noreply@domain.com"
        )
