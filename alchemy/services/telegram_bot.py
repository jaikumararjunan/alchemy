"""
alchemy.services.telegram_bot
================================
Telegram bot for trade notifications and portfolio queries.

Setup:
  1. Create bot via @BotFather → get BOT_TOKEN
  2. Set TELEGRAM_BOT_TOKEN in .env
  3. User sends /start to bot → gets chat_id
  4. Set TELEGRAM_CHAT_ID in .env or via API

Commands:
  /start      — Register for alerts
  /portfolio  — Current portfolio summary
  /pnl        — Today's P&L
  /positions  — Open positions
  /status     — System health + bot status
  /stop       — Pause alerts
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

import structlog
log = structlog.get_logger(__name__)

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS telegram_users (
        chat_id TEXT PRIMARY KEY,
        user_id TEXT DEFAULT '',
        username TEXT DEFAULT '',
        alerts_enabled INTEGER DEFAULT 1,
        registered_at TEXT DEFAULT (datetime('now'))
    )""")
    return c


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API."""
    if not BOT_TOKEN:
        log.warning("telegram.no_bot_token")
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            if r.status_code == 200:
                log.info("telegram.sent", chat_id=chat_id[:6])
                return True
            log.warning("telegram.send_failed", status=r.status_code, body=r.text[:100])
    except Exception as e:
        log.error("telegram.send_error", error=str(e))
    return False


async def send_trade_alert(chat_id: str, symbol: str, side: str, price: float,
                            pnl: float = 0, strategy: str = "") -> bool:
    """Send formatted trade alert."""
    emoji = "🟢" if side.lower() in ("buy", "long") else "🔴"
    pnl_str = f"\n💰 P&L: <b>${pnl:+.2f}</b>" if pnl else ""
    strat_str = f"\n📋 Strategy: {strategy}" if strategy else ""

    text = (
        f"{emoji} <b>{side.upper()}</b> {symbol}\n"
        f"💲 Price: <code>${price:,.2f}</code>"
        f"{pnl_str}{strat_str}\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )
    return await send_message(chat_id, text)


async def send_portfolio_summary(chat_id: str, user_id: str) -> bool:
    """Send portfolio summary to Telegram."""
    try:
        from alchemy.paper_trading.engine import get_paper_engine
        engine = get_paper_engine()
        p = engine.get_portfolio(user_id)

        positions_text = ""
        for sym, pos in list(p.positions.items())[:5]:
            side_emoji = "📈" if pos.side.value == "long" else "📉"
            positions_text += f"  {side_emoji} {sym}: {pos.quantity} @ ${pos.avg_entry_price:,.2f}\n"

        if not positions_text:
            positions_text = "  No open positions\n"

        text = (
            f"📊 <b>Portfolio Summary</b>\n"
            f"{'─' * 28}\n"
            f"💰 Value: <code>${p.portfolio_value:,.2f}</code>\n"
            f"💵 Cash: <code>${p.cash_balance:,.2f}</code>\n"
            f"📈 Return: <b>{p.total_return_pct:+.2f}%</b>\n"
            f"📋 Trades: {len(p.trade_log)}\n"
            f"\n<b>Positions:</b>\n{positions_text}"
            f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        return await send_message(chat_id, text)
    except Exception as e:
        return await send_message(chat_id, f"❌ Error fetching portfolio: {str(e)[:100]}")


def register_chat(chat_id: str, user_id: str = "", username: str = ""):
    """Register a Telegram chat for alerts."""
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO telegram_users
            (chat_id, user_id, username, alerts_enabled) VALUES (?,?,?,1)""",
            (chat_id, user_id, username))


def get_alert_chats(user_id: str = "") -> list[str]:
    """Get all chat IDs that should receive alerts."""
    with _conn() as c:
        if user_id:
            rows = c.execute("SELECT chat_id FROM telegram_users WHERE user_id=? AND alerts_enabled=1",
                             (user_id,)).fetchall()
        else:
            rows = c.execute("SELECT chat_id FROM telegram_users WHERE alerts_enabled=1").fetchall()
    return [r["chat_id"] for r in rows]


async def broadcast_trade_alert(symbol: str, side: str, price: float,
                                 pnl: float = 0, strategy: str = "",
                                 user_id: str = ""):
    """Broadcast trade alert to all registered Telegram users."""
    chats = get_alert_chats(user_id)
    for chat_id in chats:
        await send_trade_alert(chat_id, symbol, side, price, pnl, strategy)
