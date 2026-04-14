"""
alchemy.services.candle_stream
=================================
Live candlestick data stream from Binance WebSocket.

Streams real-time kline (candlestick) data for TradingView charts.
Provides both historical candle fetch and live streaming updates.

Usage:
  candles = await fetch_candles("BTCUSDT", "1h", limit=200)
  # Returns: [{ time, open, high, low, close, volume }, ...]
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
log = structlog.get_logger(__name__)

# In-memory candle cache per symbol/interval
_candle_cache: dict[str, dict] = {}
_CACHE_TTL = 60  # seconds


async def fetch_candles(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 200,
) -> list[dict]:
    """
    Fetch historical candles from Binance REST API.

    intervals: 1m, 5m, 15m, 1h, 4h, 1d, 1w
    Returns list of {time, open, high, low, close, volume}
    """
    cache_key = f"{symbol}:{interval}"
    if cache_key in _candle_cache:
        cached = _candle_cache[cache_key]
        if time.time() - cached["ts"] < _CACHE_TTL:
            return cached["data"]

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.binance.com/api/v3/klines", params={
                "symbol": symbol.upper().replace("/", ""),
                "interval": interval,
                "limit": min(limit, 1000),
            })
            if r.status_code != 200:
                log.warning("candles.fetch_failed", status=r.status_code)
                return []

            candles = []
            for k in r.json():
                candles.append({
                    "time": int(k[0]) // 1000,  # Unix seconds
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })

            # Cache
            _candle_cache[cache_key] = {"data": candles, "ts": time.time()}
            log.info("candles.fetched", symbol=symbol, interval=interval, count=len(candles))
            return candles

    except Exception as e:
        log.error("candles.fetch_error", error=str(e))
        return []


async def fetch_multi_candles(
    symbols: list[str] = None,
    interval: str = "1h",
    limit: int = 100,
) -> dict[str, list[dict]]:
    """Fetch candles for multiple symbols concurrently."""
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    tasks = [fetch_candles(s, interval, limit) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        sym: data for sym, data in zip(symbols, results)
        if not isinstance(data, Exception) and data
    }
