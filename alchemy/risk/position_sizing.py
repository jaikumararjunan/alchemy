"""
alchemy.risk.position_sizing
==============================
Position sizing calculators.

Methods:
  - Kelly criterion (optimal fraction of capital)
  - Fixed fractional (risk X% per trade)
  - Volatility-based (ATR-scaled)
  - Max drawdown-constrained

Usage::

    from alchemy.risk.position_sizing import calculate_position_size, SizingMethod

    result = calculate_position_size(
        method=SizingMethod.KELLY,
        capital=10000,
        win_rate=0.55,
        avg_win=150,
        avg_loss=100,
        entry_price=62500,
        stop_loss=61000,
    )
    print(result)  # {"quantity": 0.05, "capital_at_risk": 500, ...}
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


class SizingMethod(str, Enum):
    KELLY           = "kelly"
    HALF_KELLY      = "half_kelly"
    FIXED_FRACTIONAL = "fixed_fractional"
    VOLATILITY      = "volatility"
    FIXED_AMOUNT    = "fixed_amount"


@dataclass
class PositionSizeResult:
    method: str
    quantity: float
    position_value: float
    capital_at_risk: float
    risk_pct_of_capital: float
    kelly_fraction: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "quantity": round(self.quantity, 8),
            "position_value": round(self.position_value, 2),
            "capital_at_risk": round(self.capital_at_risk, 2),
            "risk_pct_of_capital": round(self.risk_pct_of_capital, 2),
            "kelly_fraction": round(self.kelly_fraction, 4) if self.kelly_fraction else None,
            "notes": self.notes,
        }


def calculate_position_size(
    method: SizingMethod = SizingMethod.HALF_KELLY,
    capital: float = 10000.0,
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    win_rate: float = 0.5,
    avg_win: float = 100.0,
    avg_loss: float = 100.0,
    risk_per_trade_pct: float = 2.0,
    volatility: float = 0.0,
    target_vol: float = 0.15,
    fixed_amount: float = 0.0,
    max_position_pct: float = 25.0,
) -> PositionSizeResult:
    """
    Calculate position size using the specified method.
    """
    if capital <= 0 or entry_price <= 0:
        return PositionSizeResult(
            method=method.value, quantity=0, position_value=0,
            capital_at_risk=0, risk_pct_of_capital=0,
            notes="Invalid capital or entry price",
        )

    max_position_value = capital * (max_position_pct / 100)

    if method == SizingMethod.KELLY:
        return _kelly(capital, entry_price, stop_loss, win_rate,
                      avg_win, avg_loss, max_position_value, fraction=1.0)

    elif method == SizingMethod.HALF_KELLY:
        return _kelly(capital, entry_price, stop_loss, win_rate,
                      avg_win, avg_loss, max_position_value, fraction=0.5)

    elif method == SizingMethod.FIXED_FRACTIONAL:
        return _fixed_fractional(capital, entry_price, stop_loss,
                                 risk_per_trade_pct, max_position_value)

    elif method == SizingMethod.VOLATILITY:
        return _volatility_based(capital, entry_price, volatility,
                                 target_vol, max_position_value)

    elif method == SizingMethod.FIXED_AMOUNT:
        qty = fixed_amount / entry_price if entry_price > 0 else 0
        risk = abs(entry_price - stop_loss) * qty if stop_loss else 0
        return PositionSizeResult(
            method="fixed_amount", quantity=qty,
            position_value=fixed_amount,
            capital_at_risk=risk,
            risk_pct_of_capital=(risk / capital) * 100 if capital else 0,
        )

    return PositionSizeResult(method=method.value, quantity=0,
                              position_value=0, capital_at_risk=0,
                              risk_pct_of_capital=0, notes="Unknown method")


def _kelly(
    capital, entry_price, stop_loss, win_rate,
    avg_win, avg_loss, max_position_value, fraction=1.0,
) -> PositionSizeResult:
    """Kelly criterion position sizing."""
    if avg_loss == 0:
        avg_loss = 1.0

    # Kelly formula: f* = (p * b - q) / b
    # where p=win_rate, q=1-p, b=avg_win/avg_loss
    b = abs(avg_win / avg_loss)
    p = win_rate
    q = 1 - p
    kelly_f = (p * b - q) / b if b > 0 else 0

    # Apply fraction (half-Kelly is common for safety)
    kelly_f = max(0, kelly_f * fraction)

    # Capital to allocate
    position_value = min(capital * kelly_f, max_position_value)
    quantity = position_value / entry_price if entry_price > 0 else 0

    # Risk calculation
    risk_per_unit = abs(entry_price - stop_loss) if stop_loss else entry_price * 0.05
    capital_at_risk = risk_per_unit * quantity

    label = "kelly" if fraction == 1.0 else f"half_kelly"
    return PositionSizeResult(
        method=label,
        quantity=quantity,
        position_value=position_value,
        capital_at_risk=capital_at_risk,
        risk_pct_of_capital=(capital_at_risk / capital) * 100,
        kelly_fraction=kelly_f,
        notes=f"Kelly f*={kelly_f:.4f}, b={b:.2f}, p={p:.2f}",
    )


def _fixed_fractional(
    capital, entry_price, stop_loss, risk_pct, max_position_value,
) -> PositionSizeResult:
    """Fixed fractional: risk X% of capital per trade."""
    risk_amount = capital * (risk_pct / 100)

    if stop_loss and stop_loss != entry_price:
        risk_per_unit = abs(entry_price - stop_loss)
        quantity = risk_amount / risk_per_unit
    else:
        # Default 5% stop if no stop_loss provided
        risk_per_unit = entry_price * 0.05
        quantity = risk_amount / risk_per_unit

    position_value = min(quantity * entry_price, max_position_value)
    quantity = position_value / entry_price

    return PositionSizeResult(
        method="fixed_fractional",
        quantity=quantity,
        position_value=position_value,
        capital_at_risk=risk_amount,
        risk_pct_of_capital=risk_pct,
        notes=f"Risk {risk_pct}% = ${risk_amount:.2f}, stop distance=${risk_per_unit:.2f}",
    )


def _volatility_based(
    capital, entry_price, volatility, target_vol, max_position_value,
) -> PositionSizeResult:
    """Volatility-scaled: target X% annualized vol."""
    if volatility <= 0:
        volatility = 0.20  # Default 20% if unknown

    # Scale = target_vol / asset_vol
    scale = target_vol / volatility
    position_value = min(capital * scale, max_position_value)
    quantity = position_value / entry_price

    # Estimated risk (1 daily std move)
    daily_vol = volatility / (252 ** 0.5)
    daily_risk = position_value * daily_vol

    return PositionSizeResult(
        method="volatility",
        quantity=quantity,
        position_value=position_value,
        capital_at_risk=daily_risk,
        risk_pct_of_capital=(daily_risk / capital) * 100,
        notes=f"Asset vol={volatility*100:.1f}%, target={target_vol*100:.1f}%, scale={scale:.2f}",
    )
