"""
Real-time price feed for the Alchemy dashboard.

Fetches OHLCV data from CoinGecko (free, no API key) and broadcasts
candlestick + ticker updates to all WebSocket clients every 5 seconds.

Broadcast message types
-----------------------
  candle_history  : Initial bulk load of hourly candles on connect
  ticker          : Current price + 24h change (every 5 s)
  candle_closed   : A new 1-minute candle just closed
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from src.api.ws import manager

logger = logging.getLogger(__name__)

# CoinGecko IDs mapped from our symbol names
_SYMBOL_TO_CG: Dict[str, str] = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
    "SOLUSD": "solana",
    "BNBUSD": "binancecoin",
    "XRPUSD": "ripple",
    "AVAXUSD": "avalanche-2",
    "DOGEUSD": "dogecoin",
    "LINKUSD": "chainlink",
}

_TICK_INTERVAL = 5        # seconds between price polls
_CANDLE_SECONDS = 60      # 1-minute candles assembled from ticks


class _CandleBuilder:
    """Assembles 1-min OHLCV candles from streaming ticks."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._open: Optional[float] = None
        self._high: float = 0.0
        self._low: float = float("inf")
        self._close: float = 0.0
        self._volume: float = 0.0
        self._candle_start: int = 0   # unix timestamp of current candle start

    def tick(self, price: float, volume: float = 0.0) -> Optional[Dict]:
        """Feed a price tick; returns a closed candle dict if the minute rolled."""
        now = int(time.time())
        bucket = (now // _CANDLE_SECONDS) * _CANDLE_SECONDS

        closed: Optional[Dict] = None

        if bucket != self._candle_start:
            # Close the previous candle (if we have one)
            if self._open is not None:
                closed = {
                    "time": self._candle_start,
                    "open": self._open,
                    "high": self._high,
                    "low": self._low,
                    "close": self._close,
                    "volume": self._volume,
                }
            # Start a new candle
            self._candle_start = bucket
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._volume = volume
        else:
            if self._open is None:
                self._open = price
            self._high = max(self._high, price)
            self._low = min(self._low, price)
            self._close = price
            self._volume += volume

        return closed

    def current(self) -> Optional[Dict]:
        """Return the in-progress (live) candle without closing it."""
        if self._open is None:
            return None
        return {
            "time": self._candle_start,
            "open": self._open,
            "high": self._high,
            "low": self._low,
            "close": self._close,
            "volume": self._volume,
        }


class PriceFeed:
    """Background task that polls CoinGecko and broadcasts to WS clients."""

    def __init__(self, symbols: List[str] | None = None) -> None:
        self.symbols: List[str] = symbols or list(_SYMBOL_TO_CG.keys())
        self._builders: Dict[str, _CandleBuilder] = {
            sym: _CandleBuilder(sym) for sym in self.symbols
        }
        # Cache last prices for new WS connections
        self._last_price: Dict[str, float] = {}
        self._last_change: Dict[str, float] = {}
        # Hourly candle history cache (for initial chart load)
        self._history: Dict[str, List[Dict]] = defaultdict(list)
        self._running = False

    async def fetch_history(self, symbol: str) -> List[Dict]:
        """Fetch last 24 h of hourly OHLC from CoinGecko."""
        cg_id = _SYMBOL_TO_CG.get(symbol)
        if not cg_id:
            return []
        url = (
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
            f"?vs_currency=usd&days=1"
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url)
                r.raise_for_status()
                raw = r.json()  # [[ts_ms, o, h, l, c], ...]
                candles = [
                    {
                        "time": int(row[0] / 1000),
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": 0,
                    }
                    for row in raw
                ]
                self._history[symbol] = candles
                logger.info("Loaded %d OHLC candles for %s", len(candles), symbol)
                return candles
        except Exception as exc:
            logger.warning("Failed to fetch OHLC for %s: %s", symbol, exc)
            return []

    async def fetch_prices(self) -> Dict[str, Dict]:
        """Fetch current prices + 24 h change for all tracked symbols."""
        cg_ids = ",".join(
            _SYMBOL_TO_CG[s] for s in self.symbols if s in _SYMBOL_TO_CG
        )
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={cg_ids}&vs_currencies=usd"
            f"&include_24hr_change=true&include_24hr_vol=true"
        )
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.warning("Price fetch error: %s", exc)
            return {}

    async def run(self) -> None:
        """Main loop — poll prices and broadcast every TICK_INTERVAL seconds."""
        self._running = True
        logger.info("PriceFeed started for %s", self.symbols)

        # Load initial history for BTC on startup
        await self.fetch_history("BTCUSD")

        while self._running:
            try:
                if manager.count == 0:
                    await asyncio.sleep(_TICK_INTERVAL)
                    continue

                raw = await self.fetch_prices()

                for symbol in self.symbols:
                    cg_id = _SYMBOL_TO_CG.get(symbol)
                    if not cg_id or cg_id not in raw:
                        continue

                    data = raw[cg_id]
                    price: float = data.get("usd", 0.0)
                    change: float = data.get("usd_24h_change", 0.0)
                    vol24: float = data.get("usd_24h_vol", 0.0)

                    self._last_price[symbol] = price
                    self._last_change[symbol] = change

                    # Tick the candle builder
                    closed_candle = self._builders[symbol].tick(price, vol24 / 86400)
                    live_candle = self._builders[symbol].current()

                    # Broadcast ticker
                    await manager.broadcast({
                        "type": "ticker",
                        "symbol": symbol,
                        "price": price,
                        "change_24h": round(change, 2),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })

                    # Broadcast live candle update
                    if live_candle:
                        await manager.broadcast({
                            "type": "candle_live",
                            "symbol": symbol,
                            "candle": live_candle,
                        })

                    # Broadcast closed candle
                    if closed_candle:
                        await manager.broadcast({
                            "type": "candle_closed",
                            "symbol": symbol,
                            "candle": closed_candle,
                        })

            except Exception as exc:
                logger.error("PriceFeed loop error: %s", exc, exc_info=True)

            await asyncio.sleep(_TICK_INTERVAL)

    def stop(self) -> None:
        self._running = False

    def cached_history(self, symbol: str) -> List[Dict]:
        return self._history.get(symbol, [])

    def last_prices(self) -> Dict[str, float]:
        return dict(self._last_price)


# Singleton
feed = PriceFeed()
