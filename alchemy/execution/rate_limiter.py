"""
alchemy.execution.rate_limiter
================================
Per-exchange API rate limiter using token bucket algorithm.

Prevents getting banned by exchange APIs by enforcing their rate limits:
  - Binance: 1200 requests/min (weight-based)
  - Delta:   100 requests/10s
  - Angel:   10 requests/sec
  - Kite:    3 requests/sec

Usage::

    limiter = ExchangeRateLimiter("binance", max_requests=1200, window_seconds=60)

    # Before every API call:
    await limiter.acquire()  # Blocks if rate limit would be exceeded
    response = await exchange.api_call(...)

    # Or use as context manager:
    async with limiter:
        response = await exchange.api_call(...)
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


# Default rate limits per exchange
EXCHANGE_LIMITS = {
    "binance":  {"max_requests": 1200, "window_seconds": 60},
    "delta":    {"max_requests": 100,  "window_seconds": 10},
    "angel":    {"max_requests": 10,   "window_seconds": 1},
    "kite":     {"max_requests": 3,    "window_seconds": 1},
}


class ExchangeRateLimiter:
    """
    Sliding window rate limiter for exchange API calls.

    Thread-safe and async-compatible. Uses a deque of timestamps
    to track request times within the sliding window.
    """

    def __init__(
        self,
        exchange: str,
        max_requests: Optional[int] = None,
        window_seconds: Optional[float] = None,
        burst_allowance: float = 0.8,  # Use only 80% of limit as safety margin
    ) -> None:
        defaults = EXCHANGE_LIMITS.get(exchange.lower(), {"max_requests": 60, "window_seconds": 60})
        self.exchange = exchange
        self.max_requests = int((max_requests or defaults["max_requests"]) * burst_allowance)
        self.window_seconds = window_seconds or defaults["window_seconds"]
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._total_waits = 0
        self._total_wait_time = 0.0

        log.info("rate_limiter.initialized",
                 exchange=exchange,
                 max_requests=self.max_requests,
                 window_s=self.window_seconds)

    async def acquire(self, weight: int = 1) -> float:
        """
        Acquire permission to make an API call.

        Blocks (async sleep) if the rate limit would be exceeded.
        Returns the time waited in seconds (0 if no wait needed).

        Args:
            weight: Request weight (Binance uses weighted limits).
        """
        async with self._lock:
            now = time.monotonic()
            self._purge_old(now)

            # Check if we have capacity
            current_load = len(self._timestamps)
            if current_load + weight > self.max_requests:
                # Calculate how long to wait
                oldest = self._timestamps[0] if self._timestamps else now
                wait_time = self.window_seconds - (now - oldest) + 0.05  # Small buffer
                wait_time = max(0.01, wait_time)

                self._total_waits += 1
                self._total_wait_time += wait_time

                log.debug("rate_limiter.waiting",
                          exchange=self.exchange,
                          wait_s=round(wait_time, 2),
                          current_load=current_load)

                # Release lock while waiting
                self._lock.release()
                await asyncio.sleep(wait_time)
                await self._lock.acquire()

                # Re-purge after wait
                now = time.monotonic()
                self._purge_old(now)

                # If still over limit after wait, warn but proceed
                if len(self._timestamps) + weight > self.max_requests:
                    log.warning("rate_limiter.still_over_limit",
                                exchange=self.exchange)

                self._record(now, weight)
                return wait_time

            self._record(now, weight)
            return 0.0

    def _purge_old(self, now: float) -> None:
        """Remove timestamps outside the sliding window."""
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def _record(self, now: float, weight: int) -> None:
        """Record request timestamps."""
        for _ in range(weight):
            self._timestamps.append(now)
        self._total_requests += weight

    @property
    def current_usage(self) -> int:
        """Current number of requests in the window."""
        self._purge_old(time.monotonic())
        return len(self._timestamps)

    @property
    def remaining(self) -> int:
        """Remaining requests allowed in the current window."""
        return max(0, self.max_requests - self.current_usage)

    def stats(self) -> dict:
        return {
            "exchange": self.exchange,
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "current_usage": self.current_usage,
            "remaining": self.remaining,
            "total_requests": self._total_requests,
            "total_waits": self._total_waits,
            "total_wait_time_s": round(self._total_wait_time, 2),
        }

    # Context manager support
    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


# ── Registry ──────────────────────────────────────────────────────────────────
_limiters: dict[str, ExchangeRateLimiter] = {}


def get_rate_limiter(exchange: str) -> ExchangeRateLimiter:
    """Get or create a rate limiter for an exchange."""
    key = exchange.lower()
    if key not in _limiters:
        _limiters[key] = ExchangeRateLimiter(key)
    return _limiters[key]


def all_rate_limiter_stats() -> list[dict]:
    """Get stats for all active rate limiters."""
    return [limiter.stats() for limiter in _limiters.values()]
