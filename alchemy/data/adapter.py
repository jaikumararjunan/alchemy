"""
alchemy.data.adapter
====================
Market data adapter wrapping quantrautil (QuantInsti).
Source: https://github.com/QuantInsti/quantrautil

Provides a unified interface for fetching OHLCV data from
NSE, BSE, and US markets with Redis caching.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Optional

import pandas as pd
import structlog

log = structlog.get_logger(__name__)


class MarketDataAdapter:
    """
    Unified market data fetcher with Redis caching.

    Supports:
        - NSE India (via quantrautil.get_nse_data)
        - BSE India (via quantrautil.get_bse_data)
        - US Equities (via yfinance fallback)

    Usage::

        adapter = MarketDataAdapter()
        df = adapter.fetch_ohlcv("RELIANCE", "2023-01-01", "2024-01-01", market="NSE")
        returns = adapter.fetch_returns("RELIANCE", "2023-01-01", "2024-01-01", market="NSE")
    """

    def __init__(self, redis_url: Optional[str] = None, cache_ttl_s: int = 1800) -> None:
        self._cache_ttl = cache_ttl_s
        self._redis = None
        if redis_url:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                log.info("data.redis_connected", url=redis_url)
            except Exception as e:
                log.warning("data.redis_unavailable", error=str(e))

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_ohlcv(
        self,
        symbol: str,
        start: str,
        end: str,
        market: str = "NSE",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for symbol from the appropriate market.

        Returns:
            pd.DataFrame with columns: open, high, low, close, volume
            Index: pd.DatetimeIndex (daily frequency)
        """
        cache_key = self._cache_key(symbol, start, end, market)
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.debug("data.cache_hit", symbol=symbol, market=market)
            return cached

        log.info("data.fetch", symbol=symbol, market=market, start=start, end=end)
        df = self._fetch_raw(symbol, start, end, market)
        df = self._normalise(df)

        self._cache_set(cache_key, df)
        return df

    def fetch_returns(
        self,
        symbol: str,
        start: str,
        end: str,
        market: str = "NSE",
    ) -> pd.Series:
        """Fetch daily log returns for the symbol."""
        df = self.fetch_ohlcv(symbol, start, end, market)
        return df["close"].pct_change().dropna().rename(symbol)

    def fetch_multi(
        self,
        symbols: list[str],
        start: str,
        end: str,
        market: str = "NSE",
    ) -> pd.DataFrame:
        """
        Fetch closing prices for multiple symbols.

        Returns:
            pd.DataFrame with symbols as columns.
        """
        frames = {}
        for sym in symbols:
            try:
                df = self.fetch_ohlcv(sym, start, end, market)
                frames[sym] = df["close"]
            except Exception as e:
                log.warning("data.fetch_failed", symbol=sym, error=str(e))
        return pd.DataFrame(frames).dropna(how="all")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_raw(self, symbol: str, start: str, end: str, market: str) -> pd.DataFrame:
        """Fetch from quantrautil or yfinance fallback."""
        if market in ("NSE", "BSE"):
            return self._fetch_india(symbol, start, end, market)
        return self._fetch_us(symbol, start, end)

    def _fetch_india(self, symbol: str, start: str, end: str, market: str) -> pd.DataFrame:
        try:
            from quantrautil import get_nse_data, get_bse_data
            fn = get_nse_data if market == "NSE" else get_bse_data
            df = fn(symbol, start, end)
            if df is None or df.empty:
                raise ValueError(f"No data returned from quantrautil for {symbol}")
            return df
        except ImportError:
            log.warning("data.quantrautil_missing", fallback="yfinance")
            return self._fetch_us(f"{symbol}.NS" if market == "NSE" else f"{symbol}.BO",
                                   start, end)

    def _fetch_us(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            raise ValueError(f"yfinance returned no data for {symbol}")
        return df

    def _normalise(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardise column names and index."""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        rename = {"adj close": "close", "adj_close": "close"}
        df = df.rename(columns=rename)
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                log.warning("data.missing_column", col=col)
        df.index = pd.to_datetime(df.index)
        df = df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        return df.sort_index()

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _cache_key(self, symbol: str, start: str, end: str, market: str) -> str:
        raw = f"{symbol}:{start}:{end}:{market}"
        return "alchemy:data:" + hashlib.md5(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[pd.DataFrame]:
        if self._redis is None:
            return None
        try:
            val = self._redis.get(key)
            if val:
                records = json.loads(val)
                df = pd.DataFrame(records)
                df.index = pd.to_datetime(df.index)
                return df
        except Exception:
            pass
        return None

    def _cache_set(self, key: str, df: pd.DataFrame) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(key, self._cache_ttl,
                              df.to_json(date_format="iso"))
        except Exception:
            pass
