"""
alchemy.api.webhook_routes
============================
Webhook integration — receive trade signals from TradingView, custom sources.
Each user gets a unique webhook URL with secret token.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS webhook_tokens (
        user_id TEXT PRIMARY KEY,
        token TEXT NOT NULL UNIQUE,
        enabled INTEGER DEFAULT 1,
        auto_execute INTEGER DEFAULT 0,
        max_position_pct REAL DEFAULT 5.0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS webhook_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        source TEXT DEFAULT '',
        payload TEXT DEFAULT '{}',
        action TEXT DEFAULT '',
        result TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    return c


@router.post("/setup")
async def setup_webhook(user: CurrentUser = Depends(get_current_user)):
    """Generate a unique webhook URL for receiving external signals."""
    with _conn() as c:
        existing = c.execute("SELECT token FROM webhook_tokens WHERE user_id=?",
                             (user.user_id,)).fetchone()
        if existing:
            token = existing[0]
        else:
            token = secrets.token_urlsafe(32)
            c.execute("INSERT INTO webhook_tokens (user_id, token) VALUES (?,?)",
                      (user.user_id, token))

    base = os.environ.get("BASE_URL", "http://213.199.38.90")
    return {
        "ok": True,
        "webhook_url": f"{base}/api/webhook/receive/{token}",
        "token": token,
        "message": "Use this URL in TradingView alerts or any HTTP client",
        "tradingview_format": {
            "message": '{"symbol":"{{ticker}}","side":"{{strategy.order.action}}","price":{{close}},"quantity":0}',
        },
    }


@router.get("/config")
async def get_webhook_config(user: CurrentUser = Depends(get_current_user)):
    """Get webhook configuration."""
    with _conn() as c:
        row = c.execute("SELECT * FROM webhook_tokens WHERE user_id=?",
                        (user.user_id,)).fetchone()
    if not row:
        return {"configured": False}
    d = dict(row)
    base = os.environ.get("BASE_URL", "http://213.199.38.90")
    return {
        "configured": True,
        "webhook_url": f"{base}/api/webhook/receive/{d['token']}",
        "enabled": bool(d["enabled"]),
        "auto_execute": bool(d["auto_execute"]),
        "max_position_pct": d["max_position_pct"],
    }


@router.post("/configure")
async def configure_webhook(body: dict, user: CurrentUser = Depends(get_current_user)):
    """Update webhook settings."""
    with _conn() as c:
        if "enabled" in body:
            c.execute("UPDATE webhook_tokens SET enabled=? WHERE user_id=?",
                      (1 if body["enabled"] else 0, user.user_id))
        if "auto_execute" in body:
            c.execute("UPDATE webhook_tokens SET auto_execute=? WHERE user_id=?",
                      (1 if body["auto_execute"] else 0, user.user_id))
        if "max_position_pct" in body:
            c.execute("UPDATE webhook_tokens SET max_position_pct=? WHERE user_id=?",
                      (float(body["max_position_pct"]), user.user_id))
    return {"ok": True}


@router.get("/log")
async def webhook_log(user: CurrentUser = Depends(get_current_user)):
    """Get recent webhook events."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM webhook_log WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            (user.user_id,)).fetchall()
    return {"events": [dict(r) for r in rows]}


# ── Public Receiver (no auth — uses token) ────────────────────────────────────

@router.post("/receive/{token}")
async def receive_webhook(token: str, request: Request):
    """
    Receive external trade signal.
    Supports TradingView JSON format:
      {"symbol":"BTCUSDT","side":"buy","price":73000,"quantity":0.01}
    Also supports plain text: "BUY BTCUSDT"
    """
    with _conn() as c:
        row = c.execute("SELECT user_id, enabled, auto_execute, max_position_pct FROM webhook_tokens WHERE token=?",
                        (token,)).fetchone()

    if not row:
        raise HTTPException(404, "Invalid webhook token")

    user_id = row[0]
    enabled = row[1]
    auto_execute = row[2]
    max_pct = row[3]

    if not enabled:
        raise HTTPException(403, "Webhook disabled")

    # Parse payload
    try:
        body = await request.json()
    except Exception:
        text = (await request.body()).decode("utf-8", errors="ignore").strip()
        body = _parse_text_signal(text)

    symbol = (body.get("symbol") or body.get("ticker") or "").upper()
    side = (body.get("side") or body.get("action") or body.get("order_action") or "").lower()
    price = float(body.get("price") or body.get("close") or 0)
    quantity = float(body.get("quantity") or body.get("qty") or body.get("contracts") or 0)

    if not symbol or not side:
        raise HTTPException(400, "Missing symbol or side")

    # Normalize side
    if side in ("buy", "long"):
        side = "buy"
    elif side in ("sell", "short"):
        side = "sell"
    else:
        raise HTTPException(400, f"Invalid side: {side}")

    result = {"symbol": symbol, "side": side, "price": price, "received": True}

    # Auto-execute if enabled
    if auto_execute:
        try:
            from alchemy.paper_trading.engine import get_paper_engine
            engine = get_paper_engine()
            portfolio = engine.get_portfolio(user_id)

            if quantity <= 0 and price > 0:
                budget = portfolio.cash_balance * (max_pct / 100)
                quantity = round(budget / price, 6)

            if price <= 0:
                import httpx
                resp = httpx.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5)
                price = float(resp.json().get("price", 0))

            order = engine.place_order(
                user_id=user_id, symbol=symbol, side=side,
                quantity=quantity, current_price=price,
                order_type="market", strategy="webhook",
                notes=f"Webhook signal: {json.dumps(body)[:100]}",
            )
            result["executed"] = True
            result["order_status"] = order.status.value
            result["quantity"] = quantity
            result["price"] = price

            log.info("webhook.executed", user_id=user_id[:8], symbol=symbol, side=side, qty=quantity)

            # Push notification
            try:
                from alchemy.api.push_routes import notify_trade_fill
                import asyncio
                asyncio.create_task(notify_trade_fill(user_id, symbol, side, quantity, price))
            except Exception:
                pass

        except Exception as e:
            result["executed"] = False
            result["error"] = str(e)
    else:
        result["executed"] = False
        result["note"] = "Auto-execute disabled. Signal logged only."

    # Log
    with _conn() as c:
        c.execute("INSERT INTO webhook_log (user_id, source, payload, action, result) VALUES (?,?,?,?,?)",
                  (user_id, "external", json.dumps(body)[:500], f"{side} {symbol}",
                   json.dumps(result)[:500]))

    return result


def _parse_text_signal(text: str) -> dict:
    """Parse plain text signal like 'BUY BTCUSDT' or 'SELL ETHUSDT 0.5'."""
    parts = text.upper().split()
    result = {}
    if len(parts) >= 2:
        result["side"] = parts[0].lower()
        result["symbol"] = parts[1] if "USDT" in parts[1] else parts[1] + "USDT"
    if len(parts) >= 3:
        try:
            result["quantity"] = float(parts[2])
        except ValueError:
            pass
    return result
