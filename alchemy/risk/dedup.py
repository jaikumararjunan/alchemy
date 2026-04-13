"""
alchemy.risk.dedup
===================
Duplicate order prevention.

Prevents the same signal from firing twice within a configurable
cooldown window. Uses an in-memory hash of
(strategy_id, symbol, side, timestamp_bucket).

Replace with Redis for multi-process / distributed deployments.
"""
from __future__ import annotations

import hashlib
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

DEFAULT_COOLDOWN_S = 60   # 1 minute default
MAX_CACHE_SIZE     = 10_000


@dataclass
class DedupEntry:
    key: str
    timestamp: float
    order_details: dict = field(default_factory=dict)


class OrderDeduplicator:
    """
    In-memory order deduplication with configurable cooldown.

    Usage::

        dedup = OrderDeduplicator(cooldown_seconds=60)

        # Before placing an order:
        if dedup.is_duplicate(strategy="sma_cross", symbol="BTCUSDT", side="BUY"):
            log.warning("Duplicate order blocked")
            return

        # After successful order placement:
        dedup.record(strategy="sma_cross", symbol="BTCUSDT", side="BUY")
    """

    def __init__(self, cooldown_seconds: int = DEFAULT_COOLDOWN_S) -> None:
        self._cooldown = cooldown_seconds
        self._cache: dict[str, DedupEntry] = {}
        self._lock = threading.Lock()

    def _make_key(self, strategy: str, symbol: str, side: str) -> str:
        """Create a deterministic dedup key."""
        raw = f"{strategy}:{symbol}:{side}".lower()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_duplicate(
        self,
        strategy: str,
        symbol: str,
        side: str,
        cooldown_override: Optional[int] = None,
    ) -> bool:
        """
        Check if this order was placed recently (within cooldown).

        Returns True if duplicate (should be blocked).
        Returns False if safe to proceed.
        """
        cooldown = cooldown_override if cooldown_override is not None else self._cooldown
        key = self._make_key(strategy, symbol, side)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False

            elapsed = now - entry.timestamp
            if elapsed < cooldown:
                log.warning(
                    "dedup.blocked",
                    strategy=strategy,
                    symbol=symbol,
                    side=side,
                    elapsed_s=round(elapsed, 1),
                    cooldown_s=cooldown,
                )
                return True

            return False

    def record(
        self,
        strategy: str,
        symbol: str,
        side: str,
        order_details: Optional[dict] = None,
    ) -> None:
        """Record that an order was placed (call after successful submission)."""
        key = self._make_key(strategy, symbol, side)

        with self._lock:
            self._cache[key] = DedupEntry(
                key=key,
                timestamp=time.time(),
                order_details=order_details or {},
            )

            # Evict old entries if cache grows too large
            if len(self._cache) > MAX_CACHE_SIZE:
                self._evict_stale()

        log.debug("dedup.recorded", strategy=strategy, symbol=symbol, side=side)

    def clear(self) -> int:
        """Clear all dedup entries. Returns count cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
        log.info("dedup.cleared", count=count)
        return count

    def stats(self) -> dict:
        """Return current dedup cache stats."""
        with self._lock:
            now = time.time()
            active = sum(
                1 for e in self._cache.values()
                if now - e.timestamp < self._cooldown
            )
            return {
                "total_entries": len(self._cache),
                "active_entries": active,
                "cooldown_seconds": self._cooldown,
            }

    def _evict_stale(self) -> None:
        """Remove entries older than 2x cooldown."""
        cutoff = time.time() - (self._cooldown * 2)
        stale_keys = [
            k for k, v in self._cache.items()
            if v.timestamp < cutoff
        ]
        for k in stale_keys:
            del self._cache[k]
        if stale_keys:
            log.debug("dedup.evicted", count=len(stale_keys))


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[OrderDeduplicator] = None


def get_deduplicator(cooldown_seconds: int = DEFAULT_COOLDOWN_S) -> OrderDeduplicator:
    global _instance
    if _instance is None:
        _instance = OrderDeduplicator(cooldown_seconds)
    return _instance
