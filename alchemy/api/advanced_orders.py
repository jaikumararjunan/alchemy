"""
alchemy.api.advanced_orders
=============================
Advanced order types: OCO, Bracket, Trailing Stop.
All orders are tracked and auto-managed by the price update loop.
"""
from __future__ import annotations

import json
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/orders/advanced", tags=["advanced-orders"])

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS advanced_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        order_type TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL NOT NULL,
        entry_price REAL DEFAULT 0,
        stop_loss REAL DEFAULT 0,
        take_profit REAL DEFAULT 0,
        trailing_pct REAL DEFAULT 0,
        trailing_peak REAL DEFAULT 0,
        status TEXT DEFAULT 'active',
        filled_price REAL DEFAULT 0,
        pnl REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    return c


class OCOOrderRequest(BaseModel):
    symbol: str
    side: str  # buy or sell
    quantity: float
    stop_loss: float
    take_profit: float
    entry_price: float = 0


class BracketOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float


class TrailingStopRequest(BaseModel):
    symbol: str
    side: str  # long or short
    quantity: float
    trailing_pct: float  # e.g. 2.0 = 2% trailing


@router.post("/oco")
async def create_oco_order(req: OCOOrderRequest,
                            user: CurrentUser = Depends(get_current_user)):
    """
    OCO (One-Cancels-Other): Set both SL and TP.
    When one triggers, the other is automatically cancelled.
    """
    with _conn() as c:
        c.execute("""INSERT INTO advanced_orders
            (user_id, order_type, symbol, side, quantity, stop_loss, take_profit, entry_price)
            VALUES (?,?,?,?,?,?,?,?)""",
            (user.user_id, "oco", req.symbol.upper(), req.side, req.quantity,
             req.stop_loss, req.take_profit, req.entry_price))
        order_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    log.info("advanced.oco_created", symbol=req.symbol, sl=req.stop_loss, tp=req.take_profit)
    return {"ok": True, "id": order_id, "type": "oco",
            "message": f"OCO order: SL=${req.stop_loss:,.2f} / TP=${req.take_profit:,.2f}"}


@router.post("/bracket")
async def create_bracket_order(req: BracketOrderRequest,
                                 user: CurrentUser = Depends(get_current_user)):
    """
    Bracket Order: Entry + SL + TP as atomic unit.
    Places entry order, then automatically sets SL and TP on fill.
    """
    # Execute entry immediately via paper engine
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()

    order = engine.place_order(
        user_id=user.user_id, symbol=req.symbol.upper(), side=req.side,
        quantity=req.quantity, current_price=req.entry_price,
        order_type="market", stop_loss=req.stop_loss, take_profit=req.take_profit,
        strategy="bracket",
    )

    with _conn() as c:
        c.execute("""INSERT INTO advanced_orders
            (user_id, order_type, symbol, side, quantity, entry_price, stop_loss, take_profit, status)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (user.user_id, "bracket", req.symbol.upper(), req.side, req.quantity,
             req.entry_price, req.stop_loss, req.take_profit, "filled"))
        order_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    log.info("advanced.bracket_created", symbol=req.symbol, entry=req.entry_price,
             sl=req.stop_loss, tp=req.take_profit)
    return {"ok": True, "id": order_id, "type": "bracket",
            "order_status": order.status.value,
            "message": f"Bracket: {req.side} @ ${req.entry_price:,.2f} | SL=${req.stop_loss:,.2f} | TP=${req.take_profit:,.2f}"}


@router.post("/trailing-stop")
async def create_trailing_stop(req: TrailingStopRequest,
                                 user: CurrentUser = Depends(get_current_user)):
    """
    Trailing Stop: Follows price by X%, closes when price reverses.
    For LONG: stop follows price up, triggers when price drops X% from peak.
    For SHORT: stop follows price down, triggers when price rises X% from trough.
    """
    # Get current price
    import httpx
    try:
        resp = httpx.get(f"https://api.binance.com/api/v3/ticker/price?symbol={req.symbol.upper()}", timeout=5)
        current = float(resp.json().get("price", 0))
    except Exception:
        current = 0

    with _conn() as c:
        c.execute("""INSERT INTO advanced_orders
            (user_id, order_type, symbol, side, quantity, trailing_pct, trailing_peak, entry_price)
            VALUES (?,?,?,?,?,?,?,?)""",
            (user.user_id, "trailing_stop", req.symbol.upper(), req.side, req.quantity,
             req.trailing_pct, current, current))
        order_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    log.info("advanced.trailing_created", symbol=req.symbol, pct=req.trailing_pct, peak=current)
    return {"ok": True, "id": order_id, "type": "trailing_stop",
            "trailing_pct": req.trailing_pct, "initial_peak": current,
            "message": f"Trailing stop: {req.trailing_pct}% from peak/trough"}


@router.get("")
async def list_advanced_orders(
    status: str = Query("active"),
    user: CurrentUser = Depends(get_current_user),
):
    """List advanced orders."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM advanced_orders WHERE user_id=? AND status=? ORDER BY created_at DESC",
                         (user.user_id, status)).fetchall()
    return {"orders": [dict(r) for r in rows]}


@router.delete("/{order_id}")
async def cancel_advanced_order(order_id: int,
                                  user: CurrentUser = Depends(get_current_user)):
    """Cancel an advanced order."""
    with _conn() as c:
        c.execute("UPDATE advanced_orders SET status='cancelled', updated_at=datetime('now') WHERE id=? AND user_id=?",
                  (order_id, user.user_id))
    return {"ok": True}


# ── Price Check Engine (called from update-prices) ────────────────────────────

def check_advanced_orders(user_id: str, prices: dict) -> list[str]:
    """Check and trigger advanced orders based on current prices. Returns events."""
    events = []
    with _conn() as c:
        rows = c.execute("SELECT * FROM advanced_orders WHERE user_id=? AND status='active'",
                         (user_id,)).fetchall()

        for row in rows:
            r = dict(row)
            sym = r["symbol"]
            price = prices.get(sym, 0)
            if not price:
                continue

            if r["order_type"] == "oco":
                triggered = _check_oco(r, price)
                if triggered:
                    _execute_advanced_close(user_id, r, price, triggered, c)
                    events.append(f"OCO_{triggered.upper()}: {sym} @ {price}")

            elif r["order_type"] == "trailing_stop":
                triggered = _check_trailing(r, price, c)
                if triggered:
                    _execute_advanced_close(user_id, r, price, "trailing_stop", c)
                    events.append(f"TRAILING_STOP: {sym} @ {price}")

    return events


def _check_oco(order: dict, price: float) -> str | None:
    """Check OCO: returns 'stop_loss' or 'take_profit' or None."""
    side = order["side"]
    sl, tp = order["stop_loss"], order["take_profit"]

    if side in ("buy", "long"):
        if sl > 0 and price <= sl:
            return "stop_loss"
        if tp > 0 and price >= tp:
            return "take_profit"
    else:
        if sl > 0 and price >= sl:
            return "stop_loss"
        if tp > 0 and price <= tp:
            return "take_profit"
    return None


def _check_trailing(order: dict, price: float, conn) -> bool:
    """Check trailing stop. Updates peak. Returns True if triggered."""
    side = order["side"]
    pct = order["trailing_pct"]
    peak = order["trailing_peak"]

    if side in ("buy", "long"):
        if price > peak:
            conn.execute("UPDATE advanced_orders SET trailing_peak=?, updated_at=datetime('now') WHERE id=?",
                         (price, order["id"]))
            peak = price
        trigger = peak * (1 - pct / 100)
        return price <= trigger
    else:
        if price < peak or peak == 0:
            conn.execute("UPDATE advanced_orders SET trailing_peak=?, updated_at=datetime('now') WHERE id=?",
                         (price, order["id"]))
            peak = price
        trigger = peak * (1 + pct / 100)
        return price >= trigger


def _execute_advanced_close(user_id: str, order: dict, price: float,
                              trigger: str, conn):
    """Execute close and update order status."""
    try:
        from alchemy.paper_trading.engine import get_paper_engine
        engine = get_paper_engine()
        engine.close_position(user_id=user_id, symbol=order["symbol"], current_price=price)
    except Exception as e:
        log.warning("advanced.close_failed", error=str(e))

    conn.execute(
        "UPDATE advanced_orders SET status=?, filled_price=?, updated_at=datetime('now') WHERE id=?",
        (f"triggered_{trigger}", price, order["id"]))
    log.info("advanced.triggered", type=order["order_type"], trigger=trigger,
             symbol=order["symbol"], price=price)
