"""
alchemy.services.delta_bridge
================================
Bridge between Delta Exchange testnet and the autonomous trading engine.

Connects live Delta Exchange market data to:
  - Paper trading engine (for realistic simulation)
  - Autonomous trading engine (for live signal execution)
  - Price stream service (for real-time WebSocket prices)

Modes:
  - testnet: Uses Delta testnet API (play money)
  - live: Uses Delta mainnet API (real money — requires explicit opt-in)

Setup:
  1. Create testnet account at https://testnet.delta.exchange
  2. Generate API key + secret
  3. Set in .env:
     DELTA_API_KEY=your_testnet_key
     DELTA_API_SECRET=your_testnet_secret
     DELTA_TESTNET=true

Features:
  - Auto-sync Delta positions → paper trading dashboard
  - Route autonomous signals to Delta testnet orders
  - Live P&L tracking from Delta positions
  - Funding rate monitoring
  - Position auto-close on SL/TP
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

import structlog
log = structlog.get_logger(__name__)

DELTA_KEY = os.environ.get("DELTA_API_KEY", "")
DELTA_SECRET = os.environ.get("DELTA_API_SECRET", "")
DELTA_TESTNET = os.environ.get("DELTA_TESTNET", "true").lower() in ("true", "1", "yes")


def is_configured() -> bool:
    """Check if Delta Exchange credentials are configured."""
    return bool(DELTA_KEY and DELTA_SECRET)


def get_delta_gateway():
    """Get or create Delta Exchange gateway instance."""
    from alchemy.execution.crypto.delta_gateway import DeltaGateway
    return DeltaGateway(
        api_key=DELTA_KEY,
        api_secret=DELTA_SECRET,
        testnet_mode=DELTA_TESTNET,
        paper_trading=not DELTA_KEY,
    )


async def fetch_live_prices(symbols: list[str] = None) -> dict:
    """Fetch live prices from Delta Exchange."""
    symbols = symbols or ["BTCUSD", "ETHUSD", "SOLUSD"]
    prices = {}
    try:
        gw = get_delta_gateway()
        for sym in symbols:
            try:
                ticker = gw.get_ticker(sym)
                if ticker:
                    prices[sym] = {
                        "mark_price": float(ticker.get("mark_price", 0) or 0),
                        "last_price": float(ticker.get("close", 0) or ticker.get("last_price", 0) or 0),
                        "bid": float(ticker.get("best_bid", 0) or 0),
                        "ask": float(ticker.get("best_ask", 0) or 0),
                        "volume_24h": float(ticker.get("turnover_usd", 0) or 0),
                        "funding_rate": float(ticker.get("funding_rate", 0) or 0),
                        "open_interest": float(ticker.get("oi_value", 0) or 0),
                    }
            except Exception as e:
                log.warning("delta.ticker_failed", symbol=sym, error=str(e)[:60])
    except Exception as e:
        log.error("delta.gateway_failed", error=str(e))
    return prices


async def sync_positions() -> list[dict]:
    """Sync Delta Exchange positions to internal tracking."""
    if not is_configured():
        return []
    try:
        gw = get_delta_gateway()
        positions = gw.get_positions()
        synced = []
        for pos in positions:
            if float(pos.get("size", 0)) != 0:
                synced.append({
                    "symbol": pos.get("symbol", ""),
                    "side": "long" if float(pos.get("size", 0)) > 0 else "short",
                    "size": abs(float(pos.get("size", 0))),
                    "entry_price": float(pos.get("entry_price", 0)),
                    "mark_price": float(pos.get("mark_price", 0)),
                    "pnl": float(pos.get("realized_pnl", 0)) + float(pos.get("unrealized_pnl", 0)),
                    "leverage": float(pos.get("leverage", 1)),
                    "liquidation_price": float(pos.get("liquidation_price", 0)),
                })
        log.info("delta.positions_synced", count=len(synced))
        return synced
    except Exception as e:
        log.error("delta.sync_failed", error=str(e))
        return []


async def execute_on_delta(symbol: str, side: str, size: float,
                            order_type: str = "market_order",
                            leverage: int = 5) -> dict:
    """Execute a trade on Delta Exchange (testnet or live)."""
    if not is_configured():
        return {"status": "error", "message": "Delta Exchange not configured"}

    try:
        gw = get_delta_gateway()

        # Set leverage
        try:
            gw.set_leverage(symbol, leverage)
        except Exception:
            pass

        # Place order
        result = gw.place_order(
            symbol=symbol,
            side=side,
            size=size,
            order_type=order_type,
        )

        log.info("delta.order_placed",
                 symbol=symbol, side=side, size=size,
                 order_id=result.get("id"), status=result.get("state"))

        return {
            "status": "success",
            "exchange": "delta",
            "testnet": DELTA_TESTNET,
            "order_id": result.get("id"),
            "symbol": symbol,
            "side": side,
            "size": size,
            "state": result.get("state"),
            "price": result.get("average_fill_price"),
        }
    except Exception as e:
        log.error("delta.order_failed", symbol=symbol, side=side, error=str(e))
        return {"status": "error", "message": str(e)[:200]}


async def get_wallet_balance() -> dict:
    """Get Delta Exchange wallet balance."""
    if not is_configured():
        return {"configured": False}
    try:
        gw = get_delta_gateway()
        balances = gw.get_wallet_balance()
        return {
            "configured": True,
            "testnet": DELTA_TESTNET,
            "balances": balances,
        }
    except Exception as e:
        return {"configured": True, "error": str(e)[:100]}


async def get_funding_rates(symbols: list[str] = None) -> list[dict]:
    """Get current funding rates for perpetual contracts."""
    symbols = symbols or ["BTCUSD", "ETHUSD", "SOLUSD"]
    rates = []
    try:
        gw = get_delta_gateway()
        for sym in symbols:
            try:
                data = gw.get_funding_rate(sym)
                if data:
                    rates.append({
                        "symbol": sym,
                        "funding_rate": float(data.get("funding_rate", 0)),
                        "predicted_rate": float(data.get("predicted_funding_rate", 0) or 0),
                        "next_funding": data.get("next_funding_time", ""),
                    })
            except Exception:
                pass
    except Exception as e:
        log.error("delta.funding_failed", error=str(e))
    return rates
