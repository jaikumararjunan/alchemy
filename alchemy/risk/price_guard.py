"""
alchemy.risk.price_guard
=========================
Order price validation — rejects orders with prices that deviate
beyond a configurable threshold from the last traded price.

Prevents:
  - Fat-finger errors (e.g., buying BTC at $620,000 instead of $62,000)
  - Strategy bugs producing absurd prices
  - Stale price references after network outages

Usage::

    guard = PriceGuard(max_deviation_pct=5.0)

    # Update reference price from market data feed
    guard.update_price("BTCUSDT", 62500.0)

    # Validate before order submission
    result = guard.validate("BTCUSDT", order_price=62800.0)
    if not result.valid:
        reject_order(result.reason)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

DEFAULT_MAX_DEVIATION_PCT = 5.0   # 5% default
PRICE_STALE_SECONDS       = 300   # 5 minutes — reject if reference price is older


@dataclass
class PriceRef:
    """Reference price for a symbol."""
    symbol: str
    price: float
    updated_at: float  # time.time()
    source: str = "market_data"


@dataclass
class ValidationResult:
    """Result of price validation."""
    valid: bool
    symbol: str
    order_price: float
    reference_price: Optional[float] = None
    deviation_pct: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "symbol": self.symbol,
            "order_price": self.order_price,
            "reference_price": self.reference_price,
            "deviation_pct": round(self.deviation_pct, 4) if self.deviation_pct else None,
            "reason": self.reason,
        }


class PriceGuard:
    """
    Validates order prices against last known market price.

    Thread-safe. Call update_price() from your market data feed,
    then validate() before every order submission.
    """

    def __init__(
        self,
        max_deviation_pct: float = DEFAULT_MAX_DEVIATION_PCT,
        stale_seconds: float = PRICE_STALE_SECONDS,
    ) -> None:
        self._max_deviation = max_deviation_pct / 100.0  # Convert to fraction
        self._stale_seconds = stale_seconds
        self._prices: dict[str, PriceRef] = {}
        self._lock = threading.Lock()

    def update_price(
        self,
        symbol: str,
        price: float,
        source: str = "market_data",
    ) -> None:
        """Update reference price for a symbol (call from market data feed)."""
        if price <= 0:
            log.warning("price_guard.invalid_price", symbol=symbol, price=price)
            return

        with self._lock:
            self._prices[symbol.upper()] = PriceRef(
                symbol=symbol.upper(),
                price=price,
                updated_at=time.time(),
                source=source,
            )

    def validate(
        self,
        symbol: str,
        order_price: float,
        max_deviation_override: Optional[float] = None,
    ) -> ValidationResult:
        """
        Validate an order price against the reference.

        Returns ValidationResult with valid=True if OK, valid=False if rejected.
        """
        symbol = symbol.upper()

        if order_price <= 0:
            return ValidationResult(
                valid=False,
                symbol=symbol,
                order_price=order_price,
                reason="Order price must be positive",
            )

        with self._lock:
            ref = self._prices.get(symbol)

        # No reference price — allow but warn
        if ref is None:
            log.warning("price_guard.no_reference", symbol=symbol)
            return ValidationResult(
                valid=True,
                symbol=symbol,
                order_price=order_price,
                reason="No reference price available — order allowed with warning",
            )

        # Check staleness
        age = time.time() - ref.updated_at
        if age > self._stale_seconds:
            log.warning("price_guard.stale_reference",
                        symbol=symbol, age_s=round(age, 1))
            return ValidationResult(
                valid=False,
                symbol=symbol,
                order_price=order_price,
                reference_price=ref.price,
                reason=f"Reference price is stale ({age:.0f}s old, max {self._stale_seconds}s). "
                       "Refresh market data before trading.",
            )

        # Calculate deviation
        max_dev = (max_deviation_override / 100.0) if max_deviation_override else self._max_deviation
        deviation = abs(order_price - ref.price) / ref.price

        if deviation > max_dev:
            log.warning(
                "price_guard.rejected",
                symbol=symbol,
                order_price=order_price,
                ref_price=ref.price,
                deviation_pct=round(deviation * 100, 2),
                max_pct=round(max_dev * 100, 2),
            )
            return ValidationResult(
                valid=False,
                symbol=symbol,
                order_price=order_price,
                reference_price=ref.price,
                deviation_pct=deviation * 100,
                reason=f"Price deviation {deviation*100:.2f}% exceeds max {max_dev*100:.1f}%. "
                       f"Order: {order_price}, Market: {ref.price}",
            )

        log.debug(
            "price_guard.approved",
            symbol=symbol,
            deviation_pct=round(deviation * 100, 2),
        )
        return ValidationResult(
            valid=True,
            symbol=symbol,
            order_price=order_price,
            reference_price=ref.price,
            deviation_pct=deviation * 100,
            reason="OK",
        )

    def get_reference(self, symbol: str) -> Optional[dict]:
        """Get current reference price for a symbol."""
        with self._lock:
            ref = self._prices.get(symbol.upper())
            if ref:
                return {
                    "symbol": ref.symbol,
                    "price": ref.price,
                    "age_seconds": round(time.time() - ref.updated_at, 1),
                    "source": ref.source,
                }
        return None

    def stats(self) -> dict:
        """Return guard stats."""
        with self._lock:
            now = time.time()
            active = sum(
                1 for r in self._prices.values()
                if now - r.updated_at < self._stale_seconds
            )
            return {
                "total_symbols": len(self._prices),
                "active_symbols": active,
                "max_deviation_pct": round(self._max_deviation * 100, 2),
                "stale_threshold_s": self._stale_seconds,
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[PriceGuard] = None


def get_price_guard(
    max_deviation_pct: float = DEFAULT_MAX_DEVIATION_PCT,
) -> PriceGuard:
    global _instance
    if _instance is None:
        _instance = PriceGuard(max_deviation_pct)
    return _instance
