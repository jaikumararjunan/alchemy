"""
Notification system for Alchemy bot.
Sends alerts via Telegram for trade signals, stops, and errors.
"""

import os
from dataclasses import dataclass

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Notification:
    title: str
    message: str
    level: str = "info"  # "info", "success", "warning", "error", "trade"


class TelegramNotifier:
    """
    Sends trading alerts to Telegram.
    Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
    """

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        if self.enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.info(
                "Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)"
            )

    def send(self, notification: Notification) -> bool:
        if not self.enabled:
            return False
        emoji = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "trade": "📊",
        }
        icon = emoji.get(notification.level, "ℹ️")
        text = f"{icon} *{notification.title}*\n\n{notification.message}"
        return self._send_message(text)

    def send_trade_signal(
        self,
        action: str,
        symbol: str,
        price: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        reasoning: str,
    ) -> bool:
        emoji = "🟢" if "buy" in action.lower() else "🔴"
        rr = (
            abs(take_profit - price) / abs(price - stop_loss)
            if abs(price - stop_loss) > 0
            else 0
        )
        msg = (
            f"{emoji} *{action.upper()} {symbol}*\n\n"
            f"💰 Price: `${price:,.2f}`\n"
            f"🛑 Stop Loss: `${stop_loss:,.2f}`\n"
            f"🎯 Take Profit: `${take_profit:,.2f}`\n"
            f"📈 Risk:Reward: `{rr:.2f}:1`\n"
            f"🧠 Confidence: `{confidence * 100:.0f}%`\n\n"
            f"_Reasoning: {reasoning[:200]}_"
        )
        return self._send_message(msg)

    def send_stop_triggered(
        self, symbol: str, side: str, price: float, entry: float, pnl: float
    ) -> bool:
        emoji = "🔴" if pnl < 0 else "🟢"
        msg = (
            f"{emoji} *STOP TRIGGERED: {symbol}*\n\n"
            f"Position: `{side.upper()}`\n"
            f"Entry: `${entry:,.2f}`\n"
            f"Exit: `${price:,.2f}`\n"
            f"P&L: `{'+' if pnl >= 0 else ''}{pnl:.2f} USDT`"
        )
        return self._send_message(msg)

    def send_daily_summary(self, stats: dict) -> bool:
        wr = stats.get("win_rate", 0)
        pnl = stats.get("total_pnl", 0)
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg = (
            f"{emoji} *ALCHEMY Daily Summary*\n\n"
            f"💼 Trades: `{stats.get('trades', 0)}`\n"
            f"🏆 Win Rate: `{wr:.1f}%`\n"
            f"💰 Total P&L: `{'+' if pnl >= 0 else ''}{pnl:.2f} USDT`\n"
            f"📊 Profit Factor: `{stats.get('profit_factor', 0):.2f}`\n"
            f"📉 Max Drawdown: `{stats.get('max_drawdown_pct', 0):.2f}%`"
        )
        return self._send_message(msg)

    def send_risk_alert(self, alert_type: str, details: str) -> bool:
        msg = f"⚠️ *RISK ALERT: {alert_type}*\n\n{details}"
        return self._send_message(msg)

    def send_geo_alert(self, event: str, impact: float, region: str) -> bool:
        emoji = "🟢" if impact > 0 else "🔴"
        msg = (
            f"{emoji} *Geopolitical Alert*\n\n"
            f"Event: {event}\n"
            f"Region: {region}\n"
            f"Crypto Impact: `{'+' if impact >= 0 else ''}{impact:.2f}`"
        )
        return self._send_message(msg)

    def _send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            return False


# Global notifier instance
notifier = TelegramNotifier()
