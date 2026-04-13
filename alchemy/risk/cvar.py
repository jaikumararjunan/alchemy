"""
alchemy.risk.cvar
=================
CVaR (Conditional Value-at-Risk / Expected Shortfall) and
Kelly Criterion calculations for the Alchemy risk engine.

Research references:
  - Basel III/IV: ES at 97.5% confidence replaces VaR at 99%
  - Kelly (1956), Thorp (1962): fractional Kelly for production safety
  - Rockafellar & Uryasev (2000): CVaR as coherent risk measure
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass
class CVaRResult:
    """Output of a CVaR computation."""
    var: float          # Value-at-Risk at given confidence
    cvar: float         # Conditional VaR (Expected Shortfall) — average loss beyond VaR
    confidence: float   # Confidence level used (e.g. 0.95)
    n_observations: int # Number of return observations used
    worst_loss: float   # Single worst return in the sample


def expected_shortfall(
    returns: Sequence[float],
    confidence: float = 0.95,
) -> CVaRResult:
    """
    Compute Expected Shortfall (CVaR) from a list of returns.

    ES is the average loss in the worst (1-confidence)% of scenarios.
    Returns are signed (positive = gain, negative = loss).

    Args:
        returns:    Sequence of period returns (e.g. daily P&L as fractions)
        confidence: Confidence level, default 0.95 (95th percentile CVaR)

    Returns:
        CVaRResult with var, cvar, and metadata.
    """
    if not returns:
        return CVaRResult(var=0.0, cvar=0.0, confidence=confidence,
                          n_observations=0, worst_loss=0.0)

    sorted_returns = sorted(returns)
    n = len(sorted_returns)

    # VaR threshold index
    cutoff_idx = int(math.floor((1.0 - confidence) * n))
    cutoff_idx = max(0, min(cutoff_idx, n - 1))

    var = -sorted_returns[cutoff_idx]  # expressed as a positive loss figure

    # CVaR: mean of returns below the VaR threshold
    tail = sorted_returns[: cutoff_idx + 1]
    if tail:
        cvar = -sum(tail) / len(tail)
    else:
        cvar = var

    return CVaRResult(
        var=round(var, 6),
        cvar=round(cvar, 6),
        confidence=confidence,
        n_observations=n,
        worst_loss=round(-sorted_returns[0], 6),
    )


def kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> float:
    """
    Compute the fractional Kelly position size.

    Uses Quarter-Kelly (fraction=0.25) by default for production safety.
    Full Kelly is mathematically optimal but causes extreme drawdowns
    in practice due to estimation error.

    Args:
        win_rate:  Proportion of winning trades (0–1)
        avg_win:   Average gain per winning trade (positive fraction, e.g. 0.02 = 2%)
        avg_loss:  Average loss per losing trade (positive fraction, e.g. 0.01 = 1%)
        fraction:  Kelly multiplier (default 0.25 = Quarter-Kelly)

    Returns:
        Recommended position size as a fraction of capital (0–1),
        clamped to [0, 1].
    """
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0

    loss_rate = 1.0 - win_rate
    edge = win_rate * avg_win - loss_rate * avg_loss
    if edge <= 0:
        return 0.0

    full_kelly = edge / avg_win
    result = fraction * full_kelly
    return round(max(0.0, min(1.0, result)), 4)


def portfolio_cvar(
    position_returns: dict[str, list[float]],
    weights: dict[str, float] | None = None,
    confidence: float = 0.95,
) -> CVaRResult:
    """
    Compute portfolio-level CVaR by aggregating weighted position returns.

    Args:
        position_returns: Mapping of symbol → list of period returns
        weights:          Mapping of symbol → portfolio weight (0–1).
                          If None, equal weights are assumed.
        confidence:       CVaR confidence level

    Returns:
        CVaRResult for the blended portfolio return series.
    """
    if not position_returns:
        return CVaRResult(var=0.0, cvar=0.0, confidence=confidence,
                          n_observations=0, worst_loss=0.0)

    symbols = list(position_returns.keys())
    if weights is None:
        w = {s: 1.0 / len(symbols) for s in symbols}
    else:
        total = sum(weights.get(s, 0) for s in symbols) or 1.0
        w = {s: weights.get(s, 0) / total for s in symbols}

    # Determine minimum series length
    min_len = min(len(position_returns[s]) for s in symbols)
    if min_len == 0:
        return CVaRResult(var=0.0, cvar=0.0, confidence=confidence,
                          n_observations=0, worst_loss=0.0)

    # Compute weighted portfolio returns per period
    portfolio_returns: list[float] = []
    for i in range(min_len):
        period_ret = sum(w[s] * position_returns[s][i] for s in symbols)
        portfolio_returns.append(period_ret)

    return expected_shortfall(portfolio_returns, confidence=confidence)


def annualise_cvar(cvar_daily: float, trading_days: int = 252) -> float:
    """
    Scale a daily CVaR figure to an annualised number using the square-root-of-time rule.

    Args:
        cvar_daily:   Daily CVaR (positive number representing fractional loss)
        trading_days: Number of trading days per year (252 for equities/crypto)

    Returns:
        Annualised CVaR
    """
    return round(cvar_daily * math.sqrt(trading_days), 6)
