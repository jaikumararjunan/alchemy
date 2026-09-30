"""alchemy.api.dhan_routes — Dhan market data + order routes (paper by default)

Live orders need ALL of:
  * Dhan token saved with paper_trading=False (Tokens page)
  * 2FA enabled on the Alchemy account
  * ``confirm_live: true`` in the request body
and are still bounded by the gateway's max_order_value / max_order_qty limits.
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from alchemy.auth.guards import require_2fa
from alchemy.auth.middleware import CurrentUser, get_current_user
from alchemy.execution.dhan_gateway import DhanError, DhanGateway

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/dhan", tags=["dhan"])

# One gateway per user so the local kill switch and paper order book persist.
_gateways: dict[str, tuple[tuple, DhanGateway]] = {}


def _gateway(user_id: str) -> DhanGateway:
    from alchemy.api.token_routes import _load
    data = _load(user_id, "dhan")
    if not data:
        raise HTTPException(404, "Dhan not connected. Add your Client ID + Access Token in Tokens.")
    token = data.get("access_token") or data.get("api_key")
    client_id = data.get("client_id")
    if not token or not client_id:
        raise HTTPException(400, "Dhan needs both Client ID and Access Token.")
    cfg = (client_id, token, bool(data.get("paper_trading", True)),
           float(data.get("max_order_value", 50_000)))
    cached = _gateways.get(user_id)
    if cached and cached[0] == cfg:
        return cached[1]
    gw = DhanGateway(client_id, token, paper_trading=cfg[2], max_order_value=cfg[3])
    if cached:   # carry the kill switch across credential/mode edits
        gw.kill_switch = cached[1].kill_switch
        cached[1].close()
    _gateways[user_id] = (cfg, gw)
    return gw


async def _call(fn, *a, **kw):
    try:
        return await run_in_threadpool(fn, *a, **kw)
    except DhanError as e:
        raise HTTPException(400, str(e))


# ── Schemas ──────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: Optional[str] = None          # e.g. RELIANCE — resolved via scrip master
    security_id: Optional[str] = None     # or pass Dhan securityId directly
    exchange_segment: str = "NSE_EQ"
    transaction_type: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    price: float = 0
    trigger_price: float = 0
    confirm_live: bool = False


class ModifyRequest(BaseModel):
    order_type: str = "LIMIT"
    quantity: int = Field(gt=0)
    price: float = 0
    trigger_price: float = 0


# ── Status / market data (read-only) ─────────────────────────────────────────

@router.get("/status")
async def status(user: CurrentUser = Depends(get_current_user)):
    gw = _gateway(user.user_id)
    funds = await _call(gw.connect)
    return {"connected": True, "mode": "paper" if gw.paper else "LIVE",
            "kill_switch": gw.kill_switch, "max_order_value": gw.max_order_value, "funds": funds}


@router.get("/instrument/{symbol}")
async def instrument(symbol: str, exchange: str = "NSE",
                     user: CurrentUser = Depends(get_current_user)):
    inst = await _call(_gateway(user.user_id).find_instrument, symbol, exchange)
    if not inst:
        raise HTTPException(404, f"{symbol} not found on {exchange}")
    return inst


@router.get("/quote")
async def quote(symbols: str = Query(..., description="comma-separated, e.g. RELIANCE,TCS"),
                exchange: str = "NSE", full: bool = False,
                user: CurrentUser = Depends(get_current_user)):
    """Live LTP (or full quote with depth when full=true) for NSE/BSE equities."""
    gw = _gateway(user.user_id)
    req: dict[str, list[int]] = {}
    for s in [x.strip() for x in symbols.split(",") if x.strip()][:20]:
        inst = await _call(gw.find_instrument, s, exchange)
        if not inst:
            raise HTTPException(404, f"{s} not found")
        req.setdefault(inst["exchange_segment"], []).append(int(inst["security_id"]))
    return await _call(gw.get_quote if full else gw.get_ltp, req)


@router.get("/candles/{symbol}")
async def candles(symbol: str, from_date: str, to_date: str, interval: int = 0,
                  user: CurrentUser = Depends(get_current_user)):
    """interval=0 → daily (YYYY-MM-DD); else minutes (1/5/15/25/60, 'YYYY-MM-DD HH:MM:SS')."""
    gw = _gateway(user.user_id)
    inst = await _call(gw.find_instrument, symbol)
    if not inst:
        raise HTTPException(404, f"{symbol} not found")
    args = (inst["security_id"], inst["exchange_segment"], "EQUITY", from_date, to_date)
    return await _call(gw.get_historical, *args) if interval == 0 \
        else await _call(gw.get_intraday, *args, interval)


@router.get("/positions")
async def positions(user: CurrentUser = Depends(get_current_user)):
    return await _call(_gateway(user.user_id).get_positions)


@router.get("/holdings")
async def holdings(user: CurrentUser = Depends(get_current_user)):
    return await _call(_gateway(user.user_id).get_holdings)


@router.get("/orders")
async def orders(user: CurrentUser = Depends(get_current_user)):
    return await _call(_gateway(user.user_id).get_order_book)


# ── Trading ──────────────────────────────────────────────────────────────────

@router.post("/orders")
async def place_order(req: OrderRequest, user: CurrentUser = Depends(require_2fa)):
    gw = _gateway(user.user_id)
    if not gw.paper and not req.confirm_live:
        raise HTTPException(400, "LIVE mode: resend with confirm_live=true to place a real order.")

    security_id, segment = req.security_id, req.exchange_segment
    if not security_id:
        if not req.symbol:
            raise HTTPException(400, "Provide symbol or security_id")
        inst = await _call(gw.find_instrument, req.symbol)
        if not inst:
            raise HTTPException(404, f"{req.symbol} not found")
        security_id, segment = inst["security_id"], inst["exchange_segment"]

    log.warning("dhan.order_request", user=user.user_id, live=not gw.paper, symbol=req.symbol,
                security_id=security_id, side=req.transaction_type, qty=req.quantity)
    return await _call(
        gw.place_order, security_id=security_id, exchange_segment=segment,
        transaction_type=req.transaction_type, quantity=req.quantity,
        order_type=req.order_type, product_type=req.product_type,
        price=req.price, trigger_price=req.trigger_price,
    )


@router.put("/orders/{order_id}")
async def modify_order(order_id: str, req: ModifyRequest, user: CurrentUser = Depends(require_2fa)):
    return await _call(_gateway(user.user_id).modify_order, order_id, req.order_type,
                       req.quantity, req.price, req.trigger_price)


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, user: CurrentUser = Depends(require_2fa)):
    return await _call(_gateway(user.user_id).cancel_order, order_id)


@router.post("/kill-switch")
async def kill_switch(active: bool = True, user: CurrentUser = Depends(get_current_user)):
    """Activating is always allowed (no 2FA) — it only ever reduces risk."""
    gw = _gateway(user.user_id)
    if not active:
        # re-enabling trading is the risky direction
        require_2fa(user)
    return await _call(gw.activate_kill_switch if active else gw.deactivate_kill_switch)
