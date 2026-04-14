"""
alchemy.services.options_pricer
==================================
Pure-Python Black-Scholes-Merton options pricer.
No scipy dependency — uses custom normal CDF approximation.

Ported from old branch: src/strategy/options_strategies.py (1,077 lines)
Simplified to core pricing + Greeks for the web UI.

Features:
  - European call/put pricing
  - Full Greeks: delta, gamma, theta, vega, rho
  - Implied volatility solver (Newton-Raphson)
  - P&L scenarios (price, time, IV changes)
  - Strategy payoff diagrams (long call, put, straddle, etc.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import structlog
log = structlog.get_logger(__name__)


def _norm_cdf(x: float) -> float:
    """Approximation of standard normal CDF (Abramowitz & Stegun)."""
    if x < -7:
        return 0.0
    if x > 7:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    t = 1.0 / (1.0 + p * abs(x))
    y = 1.0 - (a1*t + a2*t**2 + a3*t**3 + a4*t**4 + a5*t**5) * math.exp(-x*x/2)
    return y if x >= 0 else 1.0 - y


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-x*x/2) / math.sqrt(2 * math.pi)


@dataclass
class OptionPrice:
    """Result of BSM option pricing."""
    price: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    intrinsic: float = 0.0
    extrinsic: float = 0.0
    d1: float = 0.0
    d2: float = 0.0

    def to_dict(self):
        return {
            "price": round(self.price, 4),
            "delta": round(self.delta, 4),
            "gamma": round(self.gamma, 6),
            "theta": round(self.theta, 4),
            "vega": round(self.vega, 4),
            "rho": round(self.rho, 4),
            "intrinsic": round(self.intrinsic, 4),
            "extrinsic": round(self.extrinsic, 4),
        }


def price_option(
    S: float,           # Spot price
    K: float,           # Strike price
    T: float,           # Time to expiry (years)
    r: float,           # Risk-free rate (decimal, e.g. 0.05)
    sigma: float,       # Volatility (decimal, e.g. 0.60)
    option_type: Literal["call", "put"] = "call",
) -> OptionPrice:
    """
    Price a European option using Black-Scholes-Merton.

    Example:
      result = price_option(S=70000, K=72000, T=30/365, r=0.05, sigma=0.6, option_type="call")
      print(result.price, result.delta, result.gamma)
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return OptionPrice()

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    is_call = option_type == "call"

    # Price
    if is_call:
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        intrinsic = max(S - K, 0)
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        intrinsic = max(K - S, 0)

    # Greeks
    pdf_d1 = _norm_pdf(d1)

    if is_call:
        delta = _norm_cdf(d1)
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2) / 100
    else:
        delta = _norm_cdf(d1) - 1
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100

    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100  # per 1% IV change
    theta_per_day = -(S * pdf_d1 * sigma / (2 * sqrt_T) + r * K * math.exp(-r * T) *
                      (_norm_cdf(d2) if is_call else _norm_cdf(-d2))) / 365

    return OptionPrice(
        price=price, delta=delta, gamma=gamma,
        theta=theta_per_day, vega=vega, rho=rho,
        intrinsic=intrinsic, extrinsic=price - intrinsic,
        d1=d1, d2=d2,
    )


def implied_volatility(
    market_price: float,
    S: float, K: float, T: float, r: float,
    option_type: str = "call",
    max_iter: int = 100,
    tol: float = 1e-6,
) -> float:
    """Solve for implied volatility using Newton-Raphson."""
    sigma = 0.5  # Initial guess

    for _ in range(max_iter):
        result = price_option(S, K, T, r, sigma, option_type)
        diff = result.price - market_price

        if abs(diff) < tol:
            return sigma

        if result.vega == 0:
            break

        # Vega is per 1% change, so adjust
        sigma -= diff / (result.vega * 100)
        sigma = max(0.01, min(5.0, sigma))

    return sigma


def payoff_diagram(
    S_range: tuple[float, float],
    K: float,
    premium: float,
    option_type: str = "call",
    position: str = "long",
    points: int = 50,
) -> list[dict]:
    """Generate payoff diagram data points."""
    low, high = S_range
    step = (high - low) / points
    data = []

    for i in range(points + 1):
        price = low + i * step
        if option_type == "call":
            payoff = max(price - K, 0) - premium
        else:
            payoff = max(K - price, 0) - premium

        if position == "short":
            payoff = -payoff

        data.append({
            "price": round(price, 2),
            "payoff": round(payoff, 2),
            "breakeven": round(K + premium if option_type == "call" else K - premium, 2),
        })

    return data


def scenario_analysis(
    S: float, K: float, T: float, r: float, sigma: float,
    option_type: str = "call",
    price_changes: list[float] = None,
    iv_changes: list[float] = None,
    days_forward: list[int] = None,
) -> dict:
    """Run what-if scenarios on an option position."""
    price_changes = price_changes or [-10, -5, -2, 0, 2, 5, 10]
    iv_changes = iv_changes or [-10, -5, 0, 5, 10]
    days_forward = days_forward or [0, 7, 14, 30]

    base = price_option(S, K, T, r, sigma, option_type)

    # Price change scenarios
    price_scenarios = []
    for pct in price_changes:
        new_S = S * (1 + pct / 100)
        result = price_option(new_S, K, T, r, sigma, option_type)
        price_scenarios.append({
            "price_change_pct": pct,
            "new_spot": round(new_S, 2),
            "option_price": round(result.price, 4),
            "pnl": round(result.price - base.price, 4),
            "delta": round(result.delta, 4),
        })

    # IV change scenarios
    iv_scenarios = []
    for iv_pct in iv_changes:
        new_sigma = sigma * (1 + iv_pct / 100)
        result = price_option(S, K, T, r, new_sigma, option_type)
        iv_scenarios.append({
            "iv_change_pct": iv_pct,
            "new_iv": round(new_sigma * 100, 1),
            "option_price": round(result.price, 4),
            "pnl": round(result.price - base.price, 4),
        })

    # Time decay scenarios
    time_scenarios = []
    for days in days_forward:
        new_T = max(T - days / 365, 0.001)
        result = price_option(S, K, new_T, r, sigma, option_type)
        time_scenarios.append({
            "days_forward": days,
            "remaining_days": round(new_T * 365),
            "option_price": round(result.price, 4),
            "time_decay": round(result.price - base.price, 4),
        })

    return {
        "base_price": round(base.price, 4),
        "base_greeks": base.to_dict(),
        "price_scenarios": price_scenarios,
        "iv_scenarios": iv_scenarios,
        "time_scenarios": time_scenarios,
    }
