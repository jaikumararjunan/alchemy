"""
alchemy.api.export_routes
============================
Export and integration endpoints.

Telegram:
  POST /api/telegram/register    — Register chat for alerts
  POST /api/telegram/test        — Send test message
  GET  /api/telegram/status      — Bot connection status

Reports:
  GET  /api/reports/portfolio    — Portfolio summary JSON
  GET  /api/reports/portfolio/csv — Download portfolio as CSV
  GET  /api/reports/trades/csv   — Download trade history as CSV
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(tags=["exports"])


# ── Telegram ──────────────────────────────────────────────────────────────────

class TelegramRegisterRequest(BaseModel):
    chat_id: str
    username: str = ""


@router.post("/telegram/register")
async def register_telegram(req: TelegramRegisterRequest,
                              user: CurrentUser = Depends(get_current_user)):
    """Register Telegram chat for trade alerts."""
    from alchemy.services.telegram_bot import register_chat
    register_chat(req.chat_id, user.user_id, req.username)
    return {"ok": True, "message": f"Chat {req.chat_id} registered for alerts"}


@router.post("/telegram/test")
async def test_telegram(user: CurrentUser = Depends(get_current_user)):
    """Send a test message to all registered Telegram chats."""
    from alchemy.services.telegram_bot import get_alert_chats, send_message
    chats = get_alert_chats(user.user_id)
    if not chats:
        raise HTTPException(400, "No Telegram chats registered. Send /start to your bot first.")
    results = []
    for chat_id in chats:
        ok = await send_message(chat_id, "✅ <b>Alchemy Test</b>\nYour Telegram alerts are working!")
        results.append({"chat_id": chat_id, "sent": ok})
    return {"ok": True, "results": results}


@router.get("/telegram/status")
async def telegram_status(user: CurrentUser = Depends(get_current_user)):
    """Get Telegram bot connection status."""
    import os
    from alchemy.services.telegram_bot import get_alert_chats, BOT_TOKEN
    chats = get_alert_chats(user.user_id)
    return {
        "configured": bool(BOT_TOKEN),
        "registered_chats": len(chats),
        "chat_ids": [c[:6] + "..." for c in chats],
    }


# ── Portfolio Report ──────────────────────────────────────────────────────────

@router.get("/reports/portfolio")
async def portfolio_report(user: CurrentUser = Depends(get_current_user)):
    """Full portfolio report JSON."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    p = engine.get_portfolio(user.user_id)

    positions = []
    for sym, pos in p.positions.items():
        positions.append({
            "symbol": sym,
            "side": pos.side.value,
            "quantity": pos.quantity,
            "avg_entry": round(pos.avg_entry_price, 6),
            "strategy": pos.strategy or "",
        })

    wins = len([t for t in p.trade_log if t.get("net_pnl", 0) > 0])
    losses = len([t for t in p.trade_log if t.get("net_pnl", 0) <= 0])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_value": round(p.portfolio_value, 2),
        "cash_balance": round(p.cash_balance, 2),
        "starting_balance": round(p.starting_balance, 2),
        "total_return_pct": round(p.total_return_pct, 2),
        "realized_pnl": round(p.realized_pnl, 2),
        "unrealized_pnl": round(p.unrealized_pnl, 2),
        "open_positions": len(positions),
        "total_trades": len(p.trade_log),
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": round(wins / max(len(p.trade_log), 1) * 100, 1),
        "positions": positions,
        "recent_trades": p.trade_log[-10:],
    }


@router.get("/reports/portfolio/csv")
async def portfolio_csv(user: CurrentUser = Depends(get_current_user)):
    """Download portfolio positions as CSV."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    p = engine.get_portfolio(user.user_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Symbol", "Side", "Quantity", "Avg Entry Price", "Strategy"])
    for sym, pos in p.positions.items():
        writer.writerow([sym, pos.side.value, pos.quantity, round(pos.avg_entry_price, 6), pos.strategy or ""])

    output.seek(0)
    filename = f"alchemy_positions_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/reports/trades/csv")
async def trades_csv(user: CurrentUser = Depends(get_current_user)):
    """Download complete trade history as CSV."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    p = engine.get_portfolio(user.user_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Symbol", "Side", "Quantity", "Entry Price", "Exit Price",
                      "Gross P&L", "Fee", "Net P&L", "Return %", "Strategy", "Closed At"])
    for t in p.trade_log:
        writer.writerow([
            t.get("symbol", ""), t.get("side", ""), t.get("quantity", ""),
            t.get("entry_price", ""), t.get("exit_price", ""),
            t.get("gross_pnl", ""), t.get("fee", ""), t.get("net_pnl", ""),
            t.get("return_pct", ""), t.get("strategy", ""), t.get("closed_at", ""),
        ])

    output.seek(0)
    filename = f"alchemy_trades_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
