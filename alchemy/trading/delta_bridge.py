"""
alchemy.trading.delta_bridge
================================
Bridge between Delta Exchange testnet and the autonomous trading engine.

Connects the DeltaGateway (real market data) to the paper trading engine
so autonomous signals can be validated against live market conditions.

Features:
  - Fetch live prices from Delta Exchange testnet
  - Feed into strategy engine for signal generation
  - Validate paper orders against real bid/ask spreads
  - Track funding rates for perpetual futures
  - Market regime detection from real orderbook data

Setup:
  1. Create testnet account: https://testnet.delta.exchange
  2. Generate API keys in testnet dashboard
  3. Set DELTA_API_KEY, DELTA_API_SECRET, DELTA_TESTNET=true in .env
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
log = structlog.get_logger(__name__)

# Symbols to track on Delta
DELTA_SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD"]

# Map Delta symbols to Alchemy paper trading symbols
SYMBOL_MAP = {
    "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT",
    "BNBUSD": "BNBUSDT", "XRPUSD": "XRPUSDT",
}
REVERSE_MAP = {v: k for k, v in SYMBOL_MAP.items()}


class DeltaBridge:
    """
    Bridge between Delta Exchange and Alchemy's paper trading engine.

    Usage:
        bridge = DeltaBridge(testnet=True)
        prices = await bridge.fetch_live_prices()
        bridge.update_paper_positions(prices)
    """

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self._gateway = None
        self._last_prices: dict[str, dict] = {}
        self._last_fetch: float = 0
        self._funding_rates: dict[str, float] = {}

    def _get_gateway(self):
        """Lazy-init Delta gateway."""
        if not self._gateway:
            try:
                from alchemy.execution.crypto.delta_gateway import DeltaGateway
                self._gateway = DeltaGateway(testnet_mode=self.testnet, paper_trading=True)
                log.info("delta_bridge.gateway_init", testnet=self.testnet)
            except Exception as e:
                log.warning("delta_bridge.gateway_init_failed", error=str(e))
        return self._gateway

    async def fetch_live_prices(self) -> dict[str, dict]:
        """
        Fetch live prices for all tracked symbols.
        Returns dict: {symbol: {bid, ask, last, mark, volume, funding_rate}}
        """
        now = time.time()
        if now - self._last_fetch < 5:  # Cache for 5 seconds
            return self._last_prices

        prices = {}
        gw = self._get_gateway()
        if not gw:
            return await self._fetch_from_binance()

        try:
            for delta_sym in DELTA_SYMBOLS:
                try:
                    ticker = gw.get_ticker(delta_sym)
                    if ticker:
                        alchemy_sym = SYMBOL_MAP.get(delta_sym, delta_sym)
                        prices[alchemy_sym] = {
                            "symbol": alchemy_sym,
                            "bid": float(ticker.get("best_bid", 0) or 0),
                            "ask": float(ticker.get("best_ask", 0) or 0),
                            "last": float(ticker.get("close", 0) or ticker.get("last_price", 0) or 0),
                            "mark": float(ticker.get("mark_price", 0) or 0),
                            "volume_24h": float(ticker.get("turnover_usd", 0) or 0),
                            "source": "delta_testnet" if self.testnet else "delta_mainnet",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        # Funding rate
                        try:
                            fr = gw.get_funding_rate(delta_sym)
                            if fr:
                                rate = float(fr.get("funding_rate", 0) or 0)
                                self._funding_rates[alchemy_sym] = rate
                                prices[alchemy_sym]["funding_rate"] = rate
                        except Exception:
                            pass

                except Exception as e:
                    log.debug("delta_bridge.ticker_error", symbol=delta_sym, error=str(e)[:50])

        except Exception as e:
            log.warning("delta_bridge.fetch_failed", error=str(e))
            return await self._fetch_from_binance()

        self._last_prices = prices
        self._last_fetch = now
        log.info("delta_bridge.prices_fetched", symbols=len(prices))
        return prices

    async def _fetch_from_binance(self) -> dict[str, dict]:
        """Fallback: fetch from Binance public API."""
        prices = {}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get("https://api.binance.com/api/v3/ticker/24hr")
                if r.status_code == 200:
                    for d in r.json():
                        sym = d["symbol"]
                        if sym in SYMBOL_MAP.values():
                            prices[sym] = {
                                "symbol": sym,
                                "bid": float(d.get("bidPrice", 0)),
                                "ask": float(d.get("askPrice", 0)),
                                "last": float(d.get("lastPrice", 0)),
                                "mark": float(d.get("weightedAvgPrice", 0)),
                                "volume_24h": float(d.get("quoteVolume", 0)),
                                "source": "binance_fallback",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
        except Exception as e:
            log.warning("delta_bridge.binance_fallback_failed", error=str(e))
        self._last_prices = prices
        self._last_fetch = time.time()
        return prices

    def update_paper_positions(self, prices: dict[str, dict]) -> int:
        """
        Update paper trading positions with live prices.
        Triggers SL/TP checks.
        Returns number of positions updated.
        """
        try:
            from alchemy.paper_trading.engine import get_paper_engine
            engine = get_paper_engine()
            updated = 0

            for uid, portfolio in engine._portfolios.items():
                price_dict = {}
                for sym, pos in portfolio.positions.items():
                    if sym in prices:
                        price_dict[sym] = prices[sym].get("last", 0) or prices[sym].get("mark", 0)

                if price_dict:
                    engine.update_prices(uid, price_dict)
                    updated += len(price_dict)

            return updated
        except Exception as e:
            log.warning("delta_bridge.update_failed", error=str(e))
            return 0

    async def get_market_state(self) -> dict:
        """Get comprehensive market state for strategy engine."""
        prices = await self.fetch_live_prices()

        btc = prices.get("BTCUSDT", {})
        eth = prices.get("ETHUSDT", {})

        # Simple regime detection
        btc_price = btc.get("last", 0)
        btc_vol = btc.get("volume_24h", 0)
        funding = self._funding_rates.get("BTCUSDT", 0)

        regime = "neutral"
        if funding > 0.01:
            regime = "bullish_overleveraged"  # High funding = too many longs
        elif funding < -0.01:
            regime = "bearish_overleveraged"  # Negative funding = too many shorts
        elif btc_vol > 50_000_000_000:  # >$50B daily
            regime = "high_volume"
        elif btc_vol < 10_000_000_000:
            regime = "low_volume"

        return {
            "prices": {k: {"last": v.get("last", 0), "bid": v.get("bid", 0), "ask": v.get("ask", 0)}
                       for k, v in prices.items()},
            "funding_rates": self._funding_rates,
            "regime": regime,
            "btc_price": btc_price,
            "source": btc.get("source", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_bridge: DeltaBridge | None = None

def get_delta_bridge() -> DeltaBridge:
    global _bridge
    if not _bridge:
        testnet = os.environ.get("DELTA_TESTNET", "true").lower() == "true"
        _bridge = DeltaBridge(testnet=testnet)
    return _bridge
