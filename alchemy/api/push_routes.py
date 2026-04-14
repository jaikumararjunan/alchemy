"""
alchemy.api.push_routes
========================
Push notification device token registration and sending.
Stores Expo push tokens per user for trade alerts.
"""
from __future__ import annotations

import json
import sqlite3
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/push", tags=["push-notifications"])

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.execute("""CREATE TABLE IF NOT EXISTS push_tokens (
        user_id TEXT NOT NULL,
        token TEXT NOT NULL,
        platform TEXT DEFAULT 'expo',
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, token)
    )""")
    return c


class RegisterTokenRequest(BaseModel):
    token: str
    platform: str = "expo"


class SendPushRequest(BaseModel):
    title: str
    body: str
    data: dict = {}


@router.post("/register")
async def register_push_token(req: RegisterTokenRequest,
                                user: CurrentUser = Depends(get_current_user)):
    """Register a push notification token for the current user."""
    if not req.token or not req.token.startswith("ExponentPushToken"):
        raise HTTPException(400, "Invalid Expo push token")

    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO push_tokens (user_id, token, platform) VALUES (?, ?, ?)",
            (user.user_id, req.token, req.platform)
        )
    log.info("push.token_registered", user_id=user.user_id[:8], platform=req.platform)
    return {"ok": True, "message": "Push token registered"}


@router.delete("/register")
async def unregister_push_token(req: RegisterTokenRequest,
                                  user: CurrentUser = Depends(get_current_user)):
    """Remove a push token."""
    with _conn() as c:
        c.execute("DELETE FROM push_tokens WHERE user_id=? AND token=?",
                  (user.user_id, req.token))
    return {"ok": True}


@router.get("/tokens")
async def list_tokens(user: CurrentUser = Depends(get_current_user)):
    """List registered push tokens for current user."""
    with _conn() as c:
        rows = c.execute("SELECT token, platform, created_at FROM push_tokens WHERE user_id=?",
                         (user.user_id,)).fetchall()
    return {"tokens": [{"token": r[0][:20] + "...", "platform": r[1], "created_at": r[2]} for r in rows]}


@router.post("/test")
async def test_push(user: CurrentUser = Depends(get_current_user)):
    """Send a test push notification to current user's devices."""
    sent = await send_push_to_user(
        user.user_id,
        title="Alchemy Test",
        body="Push notifications are working!",
        data={"type": "test"}
    )
    return {"ok": True, "sent": sent}


# ── Send Push to User ─────────────────────────────────────────────────────────

async def send_push_to_user(user_id: str, title: str, body: str,
                              data: dict = None, channel: str = "trade-alerts") -> int:
    """Send push notification to all of a user's registered devices."""
    with _conn() as c:
        rows = c.execute("SELECT token FROM push_tokens WHERE user_id=?",
                         (user_id,)).fetchall()

    if not rows:
        return 0

    tokens = [r[0] for r in rows]
    sent = 0

    try:
        import httpx
        messages = [{
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
            "channelId": channel,
        } for token in tokens]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                sent = len(tokens)
                log.info("push.sent", user_id=user_id[:8], count=sent)
            else:
                log.warning("push.send_failed", status=resp.status_code)
    except Exception as e:
        log.error("push.send_error", error=str(e))

    return sent


async def notify_trade_fill(user_id: str, symbol: str, side: str,
                              quantity: float, price: float, pnl: float = 0):
    """Send push notification for trade fill."""
    emoji = "🟢" if side.lower() in ("buy", "long") else "🔴"
    title = f"{emoji} {side.upper()} {symbol}"
    body = f"Qty: {quantity} @ ${price:,.2f}"
    if pnl != 0:
        body += f" | P&L: {'+'if pnl>0 else ''}${pnl:,.2f}"

    await send_push_to_user(user_id, title, body, {
        "type": "trade_fill", "symbol": symbol, "side": side,
        "quantity": quantity, "price": price, "pnl": pnl,
    }, channel="trade-alerts")


async def notify_sl_tp_trigger(user_id: str, symbol: str, trigger_type: str,
                                 price: float, pnl: float):
    """Send push notification for SL/TP trigger."""
    emoji = "🎯" if trigger_type == "take_profit" else "🛑"
    label = "Take Profit" if trigger_type == "take_profit" else "Stop Loss"
    title = f"{emoji} {label}: {symbol}"
    body = f"Closed @ ${price:,.2f} | P&L: {'+'if pnl>0 else ''}${pnl:,.2f}"

    await send_push_to_user(user_id, title, body, {
        "type": "sl_tp", "symbol": symbol, "trigger": trigger_type,
        "price": price, "pnl": pnl,
    }, channel="trade-alerts")


async def notify_signal(user_id: str, symbol: str, direction: str,
                          confidence: float, strategy: str):
    """Send push notification for autonomous signal."""
    emoji = "📈" if direction == "long" else "📉"
    title = f"{emoji} Signal: {direction.upper()} {symbol}"
    body = f"Strategy: {strategy} | Confidence: {confidence:.0%}"

    await send_push_to_user(user_id, title, body, {
        "type": "signal", "symbol": symbol, "direction": direction,
        "confidence": confidence, "strategy": strategy,
    }, channel="trade-alerts")
