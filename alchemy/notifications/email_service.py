"""
alchemy.notifications.email_service
====================================
SMTP email service for OTP verification and 2FA codes.
Supports: Gmail, Outlook, SendGrid, AWS SES, custom SMTP.
"""
from __future__ import annotations
import os, smtplib, ssl, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

log = logging.getLogger(__name__)


class EmailConfig:
    host:     str
    port:     int
    username: str
    password: str
    from_addr:str
    use_tls:  bool

    def __init__(self):
        self.host      = os.environ.get("SMTP_HOST",     "smtp.gmail.com")
        self.port      = int(os.environ.get("SMTP_PORT", "587"))
        self.username  = os.environ.get("SMTP_USER",     "")
        self.password  = os.environ.get("SMTP_PASSWORD", "")
        self.from_addr = os.environ.get("SMTP_FROM",     self.username)
        self.use_tls   = os.environ.get("SMTP_TLS",      "true").lower() == "true"
        self.enabled   = bool(self.username and self.password)


def _get_cfg():
    """Always read fresh config from env (not cached at import time)."""
    return EmailConfig()


def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """Send email. Returns True on success, False on failure."""
    _cfg = _get_cfg()
    if not _cfg.enabled:
        log.warning("email.disabled — set SMTP_USER + SMTP_PASSWORD in .env.local")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Alchemy Trading <{_cfg.from_addr}>"
        msg["To"]      = to
        if text: msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        ctx = ssl.create_default_context()
        if _cfg.use_tls:
            with smtplib.SMTP(_cfg.host, _cfg.port) as s:
                s.ehlo(); s.starttls(context=ctx); s.ehlo()
                s.login(_cfg.username, _cfg.password)
                s.sendmail(_cfg.from_addr, to, msg.as_string())
        else:
            with smtplib.SMTP_SSL(_cfg.host, _cfg.port, context=ctx) as s:
                s.login(_cfg.username, _cfg.password)
                s.sendmail(_cfg.from_addr, to, msg.as_string())

        log.info("email.sent", to=to, subject=subject)
        return True
    except Exception as e:
        log.error("email.failed", to=to, error=str(e))
        return False


OTP_HTML = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Inter,ui-sans-serif,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:40px 20px">
<table width="480" cellpadding="0" cellspacing="0"
  style="background:#1e293b;border-radius:16px;border:1px solid #334155;overflow:hidden">
  <tr><td style="padding:32px 40px;background:linear-gradient(135deg,#1e40af,#7c3aed)">
    <div style="font-size:28px;font-weight:800;color:#fff;letter-spacing:-0.5px">🔮 Alchemy</div>
    <div style="color:#93c5fd;font-size:13px;margin-top:4px">AI Trading Platform</div>
  </td></tr>
  <tr><td style="padding:36px 40px">
    <h2 style="color:#f1f5f9;margin:0 0 8px;font-size:22px;font-weight:700">{title}</h2>
    <p style="color:#94a3b8;margin:0 0 32px;font-size:14px;line-height:1.6">{message}</p>
    <div style="background:#0f172a;border:1px solid #3b82f6;border-radius:12px;padding:24px;text-align:center;margin-bottom:28px">
      <div style="font-size:40px;font-weight:800;color:#60a5fa;letter-spacing:12px;font-family:monospace">{otp}</div>
      <div style="color:#64748b;font-size:12px;margin-top:8px">Valid for {expires_in}</div>
    </div>
    <p style="color:#64748b;font-size:12px;margin:0">If you didn't request this, ignore this email.
    Never share your OTP with anyone.</p>
  </td></tr>
  <tr><td style="padding:20px 40px;background:#0f172a;border-top:1px solid #1e293b">
    <p style="color:#475569;font-size:11px;margin:0;text-align:center">
      © 2026 Alchemy Trading Platform · Secure · Encrypted</p>
  </td></tr>
</table></td></tr></table></body></html>
"""


def send_otp_email(to: str, otp: str, purpose: str = "verification") -> bool:
    titles = {
        "verification": "Verify Your Email",
        "login":        "Your Login OTP",
        "password_reset": "Reset Your Password",
        "2fa_backup":   "2FA Backup Code",
    }
    messages = {
        "verification":   "Enter this code to verify your email and activate your account.",
        "login":          "Enter this code to complete your sign-in. Do not share it with anyone.",
        "password_reset": "Use this code to reset your password.",
        "2fa_backup":     "Your two-factor authentication backup code.",
    }
    html = OTP_HTML.format(
        title      = titles.get(purpose, "Your OTP Code"),
        message    = messages.get(purpose, "Use this code to continue."),
        otp        = otp,
        expires_in = "10 minutes",
    )
    text = f"Your Alchemy OTP: {otp}\nValid for 10 minutes."
    return send_email(to, titles.get(purpose, "Alchemy OTP"), html, text)


def send_2fa_enabled_email(to: str) -> bool:
    html = OTP_HTML.format(
        title="Two-Factor Authentication Enabled",
        message="2FA has been enabled on your account. Use Google Authenticator or Authy to generate codes.",
        otp="✓ 2FA ON",
        expires_in="permanent",
    )
    return send_email(to, "2FA Enabled — Alchemy", html)


# ── Trade Alert Emails ────────────────────────────────────────────────────────

def send_trade_alert_email(to: str, event_type: str, symbol: str,
                             side: str, price: float, pnl: float = 0,
                             quantity: float = 0) -> bool:
    """Send email alert for trade events (SL/TP trigger, fill, etc.)."""
    emoji = "🎯" if event_type == "take_profit" else "🛑" if event_type == "stop_loss" else "📊"
    label = {
        "take_profit": "Take Profit Triggered",
        "stop_loss": "Stop Loss Triggered",
        "trade_fill": "Trade Filled",
        "signal": "New Signal",
    }.get(event_type, event_type.replace("_", " ").title())

    pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
    pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

    subject = f"{emoji} Alchemy: {label} — {symbol}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#0f172a;color:#f1f5f9;padding:24px;border-radius:16px;">
        <h2 style="margin:0 0 16px;color:#3b82f6;">{emoji} {label}</h2>
        <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:8px 0;color:#94a3b8;">Symbol</td><td style="text-align:right;font-weight:bold;">{symbol}</td></tr>
            <tr><td style="padding:8px 0;color:#94a3b8;">Side</td><td style="text-align:right;font-weight:bold;">{side.upper()}</td></tr>
            <tr><td style="padding:8px 0;color:#94a3b8;">Price</td><td style="text-align:right;">${price:,.2f}</td></tr>
            {"<tr><td style='padding:8px 0;color:#94a3b8;'>Quantity</td><td style='text-align:right;'>" + f"{quantity}" + "</td></tr>" if quantity else ""}
            <tr style="border-top:1px solid #334155;"><td style="padding:12px 0;color:#94a3b8;font-weight:bold;">P&L</td>
                <td style="text-align:right;font-weight:bold;font-size:18px;color:{pnl_color};">{pnl_str}</td></tr>
        </table>
        <p style="margin-top:20px;font-size:12px;color:#64748b;">
            Alchemy AI Trading Platform — <a href="http://213.199.38.90" style="color:#3b82f6;">Open Dashboard</a>
        </p>
    </div>
    """
    return send_email(to, subject, html)
