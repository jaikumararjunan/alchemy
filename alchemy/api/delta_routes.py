"""
alchemy.api.delta_routes
============================
Delta Exchange testnet bridge API.

Endpoints:
  GET  /api/delta/status       — Connection + config status
  GET  /api/delta/prices       — Live prices from Delta
  GET  /api/delta/positions    — Current Delta positions
  GET  /api/delta/wallet       — Wallet balance
  GET  /api/delta/funding      — Funding rates
  POST /api/delta/order        — Place order on Delta testnet
  POST /api/delta/close        — Close a Delta position
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/delta", tags=["delta-exchange"])


@router.get("/status")
async def delta_status(user: CurrentUser = Depends(get_current_user)):
    """Check Delta Exchange connection status."""
    from alchemy.services.delta_bridge import is_configured, DELTA_TESTNET
    return {
        "configured": is_configured(),
        "testnet": DELTA_TESTNET,
        "exchange": "Delta Exchange",
        "setup_guide": "Set DELTA_API_KEY and DELTA_API_SECRET in .env" if not is_configured() else "",
    }


@router.get("/prices")
async def delta_prices(
    symbols: str = "BTCUSD,ETHUSD,SOLUSD",
    user: CurrentUser = Depends(get_current_user),
):
    """Get live prices from Delta Exchange."""
    from alchemy.services.delta_bridge import fetch_live_prices
    sym_list = [s.strip() for s in symbols.split(",")]
    prices = await fetch_live_prices(sym_list)
    return {"prices": prices, "count": len(prices)}


@router.get("/positions")
async def delta_positions(user: CurrentUser = Depends(get_current_user)):
    """Get current Delta Exchange positions."""
    from alchemy.services.delta_bridge import sync_positions
    positions = await sync_positions()
    return {"positions": positions, "count": len(positions)}


@router.get("/wallet")
async def delta_wallet(user: CurrentUser = Depends(get_current_user)):
    """Get Delta Exchange wallet balance."""
    from alchemy.services.delta_bridge import get_wallet_balance
    return await get_wallet_balance()


@router.get("/funding")
async def delta_funding(
    symbols: str = "BTCUSD,ETHUSD,SOLUSD",
    user: CurrentUser = Depends(get_current_user),
):
    """Get current funding rates."""
    from alchemy.services.delta_bridge import get_funding_rates
    sym_list = [s.strip() for s in symbols.split(",")]
    rates = await get_funding_rates(sym_list)
    return {"rates": rates}


class DeltaOrderRequest(BaseModel):
    symbol: str
    side: str  # buy or sell
    size: float
    order_type: str = "market_order"
    leverage: int = 5


@router.post("/order")
async def delta_place_order(req: DeltaOrderRequest,
                              user: CurrentUser = Depends(get_current_user)):
    """Place an order on Delta Exchange (testnet)."""
    from alchemy.services.delta_bridge import execute_on_delta
    result = await execute_on_delta(
        symbol=req.symbol, side=req.side, size=req.size,
        order_type=req.order_type, leverage=req.leverage,
    )
    if result.get("status") == "error":
        raise HTTPException(400, result.get("message", "Order failed"))
    return result


@router.post("/close/{symbol}")
async def delta_close_position(symbol: str,
                                 user: CurrentUser = Depends(get_current_user)):
    """Close a Delta Exchange position."""
    from alchemy.services.delta_bridge import is_configured, get_delta_gateway
    if not is_configured():
        raise HTTPException(400, "Delta Exchange not configured")
    try:
        gw = get_delta_gateway()
        result = gw.close_position(symbol)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(400, str(e)[:200])
