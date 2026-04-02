"""
alchemy.api.crypto_routes
=========================
FastAPI router exposing Delta Exchange and Binance endpoints
for the React frontend.
"""
from __future__ import annotations
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from alchemy.execution.crypto.delta_gateway   import DeltaGateway
from alchemy.execution.crypto.binance_gateway import BinanceGateway

router = APIRouter(prefix="/crypto", tags=["crypto"])

# Singleton gateways (paper mode by default — swap via settings)
_delta   = DeltaGateway(paper_trading=True, testnet_mode=True)
_binance = BinanceGateway(market="futures_usdm", paper_trading=True, testnet=True)


# ── Request schemas ───────────────────────────────────────────────────────────

class DeltaOrderRequest(BaseModel):
    symbol:     str
    side:       Literal["buy", "sell"]
    size:       int
    order_type: str  = "market_order"
    leverage:   int  = 1
    limit_price: Optional[float] = None

class BinanceOrderRequest(BaseModel):
    symbol:     str
    side:       Literal["BUY", "SELL"]
    quantity:   float
    order_type: str  = "MARKET"
    leverage:   int  = 1
    price:      Optional[float] = None


# ══════════════════════════════════════════════════════════════════════════════
# DELTA EXCHANGE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/delta/products")
async def delta_products():
    try:
        return _delta.get_products()
    except Exception as e:
        raise HTTPException(502, f"Delta API error: {e}")

@router.get("/delta/ticker/{symbol}")
async def delta_ticker(symbol: str):
    try:
        return _delta.get_ticker(symbol)
    except Exception as e:
        raise HTTPException(502, f"Delta ticker error: {e}")

@router.get("/delta/orderbook/{symbol}")
async def delta_orderbook(symbol: str, depth: int = Query(10, ge=1, le=50)):
    try:
        return _delta.get_orderbook(symbol, depth)
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/delta/positions")
async def delta_positions():
    try:
        return _delta.get_positions()
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/delta/balance")
async def delta_balance():
    try:
        return _delta.get_wallet_balance()
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/delta/funding/{symbol}")
async def delta_funding(symbol: str):
    try:
        return _delta.get_funding_rate(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))

@router.post("/delta/order")
async def delta_place_order(req: DeltaOrderRequest):
    try:
        return _delta.place_order(
            symbol=req.symbol, side=req.side, size=req.size,
            order_type=req.order_type, leverage=req.leverage,  # type: ignore[arg-type]
            limit_price=req.limit_price,
        )
    except Exception as e:
        raise HTTPException(400, str(e))

@router.delete("/delta/orders/{symbol}")
async def delta_cancel_all(symbol: str):
    try:
        return _delta.cancel_all_orders(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# BINANCE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/binance/ticker/{symbol}")
async def binance_ticker(symbol: str):
    try:
        return _binance.get_ticker(symbol)
    except Exception as e:
        raise HTTPException(502, f"Binance ticker error: {e}")

@router.get("/binance/klines/{symbol}")
async def binance_klines(
    symbol: str,
    interval: str = Query("1h"),
    limit:    int = Query(100, ge=1, le=1000),
):
    try:
        return _binance.get_klines(symbol, interval=interval, limit=limit)
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/binance/balance")
async def binance_balance():
    try:
        return _binance.get_balance()
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/binance/positions")
async def binance_positions():
    try:
        return _binance.get_positions()
    except Exception as e:
        raise HTTPException(502, str(e))

@router.get("/binance/funding/{symbol}")
async def binance_funding(symbol: str):
    try:
        return _binance.get_funding_rate(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))

@router.post("/binance/order")
async def binance_place_order(req: BinanceOrderRequest):
    try:
        return _binance.place_order(
            symbol=req.symbol, side=req.side,  # type: ignore[arg-type]
            quantity=req.quantity, order_type=req.order_type,  # type: ignore[arg-type]
            leverage=req.leverage, price=req.price,
        )
    except Exception as e:
        raise HTTPException(400, str(e))

@router.delete("/binance/orders/{symbol}")
async def binance_cancel_all(symbol: str):
    try:
        return _binance.cancel_all_orders(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))

@router.post("/binance/close/{symbol}")
async def binance_close_position(symbol: str):
    try:
        return _binance.close_position(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))
