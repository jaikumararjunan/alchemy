"""
alchemy.api.market_data_routes
=================================
Live market data endpoints powered by Delta Exchange bridge.

Endpoints:
  GET /api/market/prices       — Live multi-symbol prices
  GET /api/market/state        — Market regime + funding rates
  GET /api/market/candles      — OHLCV candle data for charting
  GET /api/market/orderbook    — Level 2 orderbook for a symbol
  GET /api/market/funding      — Funding rates for perpetuals
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/market", tags=["market-data"])


@router.get("/prices")
async def live_prices(
    symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT", description="Comma-separated"),
    user: CurrentUser = Depends(get_current_user),
):
    """Get live prices from Delta Exchange / Binance."""
    from alchemy.trading.delta_bridge import get_delta_bridge
    bridge = get_delta_bridge()
    prices = await bridge.fetch_live_prices()
    requested = [s.strip().upper() for s in symbols.split(",")]
    filtered = {k: v for k, v in prices.items() if k in requested}
    return {"prices": filtered, "count": len(filtered)}


@router.get("/state")
async def market_state(user: CurrentUser = Depends(get_current_user)):
    """Get market regime + funding rates + key prices."""
    from alchemy.trading.delta_bridge import get_delta_bridge
    return await get_delta_bridge().get_market_state()


@router.get("/candles")
async def candle_data(
    symbol: str = Query("BTCUSDT", description="Symbol"),
    interval: str = Query("1h", description="Interval: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=10, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    """Get OHLCV candle data for charting."""
    try:
        import httpx
        # Map interval to Binance format
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        bi = interval_map.get(interval, "1h")
        bsym = symbol.replace("/", "").replace("-", "").upper()

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.binance.com/api/v3/klines",
                                  params={"symbol": bsym, "interval": bi, "limit": limit})
            if r.status_code == 200:
                candles = []
                for k in r.json():
                    candles.append({
                        "time": int(k[0] / 1000),  # Unix seconds for lightweight-charts
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })
                return {"symbol": symbol, "interval": interval, "candles": candles}
    except Exception as e:
        log.warning("market.candles_error", error=str(e))

    return {"symbol": symbol, "interval": interval, "candles": []}


@router.get("/orderbook")
async def orderbook(
    symbol: str = Query("BTCUSDT"),
    depth: int = Query(20, ge=5, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """Get Level 2 orderbook."""
    try:
        import httpx
        bsym = symbol.replace("/", "").replace("-", "").upper()
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.binance.com/api/v3/depth",
                                  params={"symbol": bsym, "limit": depth})
            if r.status_code == 200:
                d = r.json()
                return {
                    "symbol": symbol,
                    "bids": [[float(p), float(q)] for p, q in d.get("bids", [])],
                    "asks": [[float(p), float(q)] for p, q in d.get("asks", [])],
                }
    except Exception as e:
        log.warning("market.orderbook_error", error=str(e))

    return {"symbol": symbol, "bids": [], "asks": []}


@router.get("/funding")
async def funding_rates(user: CurrentUser = Depends(get_current_user)):
    """Get current funding rates for perpetual contracts."""
    from alchemy.trading.delta_bridge import get_delta_bridge
    bridge = get_delta_bridge()
    state = await bridge.get_market_state()
    return {"funding_rates": state.get("funding_rates", {}), "regime": state.get("regime", "unknown")}


# ── Candles ───────────────────────────────────────────────────────────────────

@router.get("/market/candles")
async def get_candles(
    symbol: str = Query("BTCUSDT", description="Trading pair"),
    interval: str = Query("1h", description="1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(200, ge=10, le=1000),
    user: CurrentUser = Depends(get_current_user),
):
    """Fetch historical candlestick data from Binance."""
    from alchemy.services.candle_stream import fetch_candles
    candles = await fetch_candles(symbol, interval, limit)
    return {"symbol": symbol, "interval": interval, "candles": candles, "count": len(candles)}


# ── Options Pricing ───────────────────────────────────────────────────────────

class OptionPriceReq(BaseModel):
    spot: float
    strike: float
    days_to_expiry: int
    risk_free_rate: float = 0.05
    volatility: float
    option_type: str = "call"


@router.post("/options/price")
async def options_price(req: OptionPriceReq, user: CurrentUser = Depends(get_current_user)):
    """Price a European option with full Greeks."""
    from alchemy.services.options_pricer import price_option
    T = req.days_to_expiry / 365
    result = price_option(req.spot, req.strike, T, req.risk_free_rate, req.volatility, req.option_type)
    return {"input": {"spot": req.spot, "strike": req.strike, "days": req.days_to_expiry,
                      "iv": f"{req.volatility*100:.0f}%", "type": req.option_type}, **result.to_dict()}


class IVReq(BaseModel):
    market_price: float
    spot: float
    strike: float
    days_to_expiry: int
    risk_free_rate: float = 0.05
    option_type: str = "call"


@router.post("/options/iv")
async def options_iv(req: IVReq, user: CurrentUser = Depends(get_current_user)):
    """Solve for implied volatility."""
    from alchemy.services.options_pricer import implied_volatility
    T = req.days_to_expiry / 365
    iv = implied_volatility(req.market_price, req.spot, req.strike, T, req.risk_free_rate, req.option_type)
    return {"implied_volatility": round(iv, 4), "iv_pct": f"{iv*100:.1f}%"}


@router.post("/options/scenarios")
async def options_scenarios(req: OptionPriceReq, user: CurrentUser = Depends(get_current_user)):
    """Run what-if scenarios (price, IV, time changes)."""
    from alchemy.services.options_pricer import scenario_analysis
    T = req.days_to_expiry / 365
    return scenario_analysis(req.spot, req.strike, T, req.risk_free_rate, req.volatility, req.option_type)


# ── Weekly Review ─────────────────────────────────────────────────────────────

@router.get("/reports/weekly-review")
async def weekly_review(
    weeks_back: int = Query(1, ge=1, le=12),
    user: CurrentUser = Depends(get_current_user),
):
    """AI-powered weekly trade review with grade and action items."""
    from alchemy.services.weekly_review import generate_weekly_review
    return generate_weekly_review(user.user_id, weeks_back)
