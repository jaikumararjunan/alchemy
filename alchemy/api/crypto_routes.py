"""
alchemy.api.crypto_routes  v2.0
Returns REAL data from Delta Exchange and Binance.
Uses stored user credentials from token_routes.
"""
from __future__ import annotations
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from alchemy.auth.middleware import get_current_user, CurrentUser

def _require_live(user_id: str, exchange: str) -> dict:
    """Raise 403 if token is in paper/testnet mode. Returns token data."""
    from alchemy.api.token_routes import _load_token
    data = _load_token(user_id, exchange)
    if not data:
        raise HTTPException(403, f"No {exchange} credentials. Connect in Tokens page first.")
    if data.get("paper_trading", True):
        raise HTTPException(403,
            f"{exchange} is in PAPER mode. Switch to live mode in Tokens to place real orders.")
    return data


def _record_trade_in_portfolio(user_id: str, symbol: str, side: str, quantity: float,
                                 price: float, exchange: str, strategy: str = "live_manual"):
    """Record a live trade in the paper trading engine for unified dashboard visibility."""
    try:
        from alchemy.paper_trading.engine import get_paper_engine
        from alchemy.paper_trading import PositionSide
        engine = get_paper_engine()
        portfolio = engine.get_portfolio(user_id)
        normalized_side = "buy" if side.upper() in ("BUY", "LONG") else "sell"

        # Check if this is closing an existing position or opening new
        pos = portfolio.positions.get(symbol.upper())

        if normalized_side == "buy" and pos and pos.side == PositionSide.SHORT:
            # Buying to close short
            engine.close_position(user_id=user_id, symbol=symbol,
                                   current_price=price, quantity=quantity)
        elif normalized_side == "sell" and pos and pos.side == PositionSide.LONG:
            # Selling to close long
            engine.close_position(user_id=user_id, symbol=symbol,
                                   current_price=price, quantity=quantity)
        else:
            # Opening new position (long or short)
            engine.place_order(
                user_id=user_id, symbol=symbol, side=normalized_side,
                quantity=quantity, current_price=price,
                order_type="market", strategy=f"live_{exchange}",
                notes=f"Live {exchange} trade",
            )

        import structlog
        structlog.get_logger(__name__).info(
            "live_trade.recorded", user_id=user_id[:8], symbol=symbol,
            side=side, qty=quantity, price=price, exchange=exchange)
    except Exception as e:
        import structlog
        structlog.get_logger(__name__).warning(
            "live_trade.record_failed", error=str(e), symbol=symbol)


router = APIRouter(prefix="/crypto", tags=["crypto"])

# ── Proxy endpoints (CSP-safe fallback) ──────────────────────────────────────

@router.get("/proxy/klines")
async def proxy_klines(symbol: str, interval: str = "1m", limit: int = 250):
    """Proxy Binance klines through backend (bypasses browser CSP)."""
    import httpx
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = httpx.get(url, timeout=10)
        return r.json()
    except Exception as e:
        raise HTTPException(502, f"Binance proxy error: {e}")


@router.get("/proxy/ticker/{symbol}")
async def proxy_ticker(symbol: str):
    """Proxy Binance ticker price through backend."""
    import httpx
    try:
        r = httpx.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5)
        return r.json()
    except Exception as e:
        raise HTTPException(502, str(e))



def _delta(user_id: str = None, testnet: bool = True):
    """Get Delta gateway: use user's stored token if available, else public API."""
    if user_id:
        try:
            from alchemy.api.token_routes import get_live_gateway
            gw = get_live_gateway("delta", user_id)
            if gw: return gw
        except Exception:
            pass
    from alchemy.execution.crypto.delta_gateway import DeltaGateway
    return DeltaGateway(paper_trading=True, testnet_mode=testnet)


def _binance(user_id: str = None, testnet: bool = False):
    """Get Binance gateway: use user's stored token if available, else public API."""
    if user_id:
        try:
            from alchemy.api.token_routes import get_live_gateway
            gw = get_live_gateway("binance", user_id)
            if gw: return gw
        except Exception:
            pass
    from alchemy.execution.crypto.binance_gateway import BinanceGateway
    return BinanceGateway(market="futures_usdm", paper_trading=True, testnet=testnet)


class OrderRequest(BaseModel):
    symbol:     str
    side:       str
    size:       float
    order_type: str           = "market_order"
    leverage:   int           = 1
    price:      Optional[float] = None


# ── Delta Exchange ─────────────────────────────────────────────────────────────

@router.get("/delta/products")
async def delta_products(user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_products()
    except Exception as e:
        raise HTTPException(502, f"Delta API error: {e}")


@router.get("/delta/ticker/{symbol}")
async def delta_ticker(symbol: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_ticker(symbol)
    except Exception as e:
        raise HTTPException(502, f"Delta ticker error: {e}")


@router.get("/delta/orderbook/{symbol}")
async def delta_orderbook(symbol: str,
                            depth: int = Query(10, ge=1, le=50),
                            user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_orderbook(symbol, depth)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/delta/positions")
async def delta_positions(user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_positions()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/delta/balance")
async def delta_balance(user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_wallet_balance()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/delta/funding/{symbol}")
async def delta_funding(symbol: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return _delta(user.user_id).get_funding_rate(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/delta/order")
async def delta_place_order(req: OrderRequest,
                              user: CurrentUser = Depends(get_current_user)):
    _require_live(user.user_id, "delta")
    try:
        gw = _delta(user.user_id)
        result = gw.place_order(
            symbol=req.symbol, side=req.side, size=int(req.size),
            order_type=req.order_type, leverage=req.leverage,
            limit_price=req.price,
        )
        # Record in unified portfolio
        fill_price = float(result.get("avg_fill_price", 0) or result.get("price", 0) or req.price or 0)
        _record_trade_in_portfolio(user.user_id, req.symbol, req.side,
                                    float(req.size), fill_price, "delta")
        return result
    except Exception as e:
        raise HTTPException(502, str(e))


@router.delete("/delta/orders/{symbol}")
async def delta_cancel_all(symbol: str, user: CurrentUser = Depends(get_current_user)):
    _require_live(user.user_id, "delta")
    try:
        return _delta(user.user_id).cancel_all_orders(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))


# ── Binance ────────────────────────────────────────────────────────────────────

@router.get("/binance/ticker/{symbol}")
async def binance_ticker(symbol: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return _binance(user.user_id).get_ticker(symbol)
    except Exception as e:
        raise HTTPException(502, f"Binance ticker error: {e}")


@router.get("/binance/klines/{symbol}")
async def binance_klines(symbol: str,
                          interval: str = Query("1h"),
                          limit:    int  = Query(100, ge=1, le=1500),
                          user: CurrentUser = Depends(get_current_user)):
    try:
        return _binance(user.user_id).get_klines(symbol, interval=interval, limit=limit)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/binance/balance")
async def binance_balance(user: CurrentUser = Depends(get_current_user)):
    try:
        return _binance(user.user_id).get_balance()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/binance/positions")
async def binance_positions(user: CurrentUser = Depends(get_current_user)):
    try:
        return _binance(user.user_id).get_positions()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/binance/funding/{symbol}")
async def binance_funding(symbol: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return _binance(user.user_id).get_funding_rate(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/binance/order")
async def binance_place_order(req: OrderRequest,
                               user: CurrentUser = Depends(get_current_user)):
    _require_live(user.user_id, "binance")
    try:
        gw = _binance(user.user_id)
        result = gw.place_order(
            symbol=req.symbol, side=req.side.upper(),
            quantity=req.size, order_type=req.order_type.upper(),
            leverage=req.leverage, price=req.price,
        )
        # Record in unified portfolio
        fill_price = float(result.get("avgPrice", 0) or result.get("price", 0) or req.price or 0)
        fill_qty = float(result.get("executedQty", 0) or req.size or 0)
        _record_trade_in_portfolio(user.user_id, req.symbol, req.side,
                                    fill_qty, fill_price, "binance")
        return result
    except Exception as e:
        raise HTTPException(502, str(e))


@router.delete("/binance/orders/{symbol}")
async def binance_cancel_all(symbol: str, user: CurrentUser = Depends(get_current_user)):
    _require_live(user.user_id, "binance")
    try:
        return _binance(user.user_id).cancel_all_orders(symbol)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/binance/close/{symbol}")
async def binance_close_position(symbol: str, user: CurrentUser = Depends(get_current_user)):
    _require_live(user.user_id, "binance")
    try:
        gw = _binance(user.user_id)
        result = gw.close_position(symbol)
        # Record close in unified portfolio
        fill_price = float(result.get("avgPrice", 0) or result.get("price", 0) or 0)
        fill_qty = float(result.get("executedQty", 0) or 0)
        _record_trade_in_portfolio(user.user_id, symbol, "SELL",
                                    fill_qty, fill_price, "binance")
        return result
    except Exception as e:
        raise HTTPException(502, str(e))


# ── Market data — NO auth needed (public endpoints) ───────────────────────────

@router.get("/market/btc-price")
async def btc_price():
    """Public BTC price from Delta Exchange — no auth needed."""
    try:
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        gw = DeltaGateway(paper_trading=True, testnet_mode=True)
        t  = gw.get_ticker("BTCUSD")
        return {"symbol": "BTCUSD", "price": t.get("mark_price"), "source": "delta"}
    except Exception:
        try:
            # Fallback to Binance public API
            import httpx
            r = httpx.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=5)
            return {"symbol": "BTCUSDT", "price": float(r.json()["price"]), "source": "binance"}
        except Exception as e:
            raise HTTPException(502, f"Cannot fetch BTC price: {e}")
