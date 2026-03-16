"""
Options Analyzer — Black-Scholes Greeks, IV estimation, put/call ratio.

Pure Python implementation (no scipy/numpy required).
Delta Exchange India offers BTC/ETH options on weekly/monthly expiries.

Greeks:
  Delta  — sensitivity to ±$1 move in underlying
  Gamma  — rate of change of Delta (high near expiry / ATM)
  Theta  — time decay (negative for long options)
  Vega   — sensitivity to ±1% IV change
  Rho    — sensitivity to ±1% interest rate

Put/Call ratio > 1 = more puts than calls open → bearish positioning
Put/Call ratio < 0.7 = more calls → bullish positioning
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict


# ── Normal distribution helpers ──────────────────────────────────────────────


def _phi(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _Phi(x: float) -> float:
    """Standard normal CDF using Abramowitz & Stegun approximation (error < 7.5e-8)."""
    if x < 0:
        return 1.0 - _Phi(-x)
    k = 1.0 / (1.0 + 0.2316419 * x)
    poly = k * (
        0.319381530
        + k * (-0.356563782 + k * (1.781477937 + k * (-1.821255978 + k * 1.330274429)))
    )
    return 1.0 - _phi(x) * poly


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class Greeks:
    """Black-Scholes option Greeks."""

    option_type: str  # "call" or "put"
    spot: float
    strike: float
    days_to_expiry: int
    implied_vol: float  # annualized, decimal (e.g. 0.80 = 80%)
    risk_free_rate: float  # annualized (e.g. 0.05 = 5%)

    # BS outputs
    theoretical_price: float
    intrinsic_value: float
    time_value: float
    delta: float  # 0–1 for calls, -1–0 for puts
    gamma: float
    theta_daily: float  # per calendar day (negative for long)
    vega_1pct: float  # for ±1% IV change
    rho_1pct: float  # for ±1% rate change
    d1: float
    d2: float

    def to_dict(self) -> dict:
        return {
            "option_type": self.option_type,
            "spot": round(self.spot, 2),
            "strike": round(self.strike, 2),
            "days_to_expiry": self.days_to_expiry,
            "implied_vol_pct": round(self.implied_vol * 100, 2),
            "risk_free_rate_pct": round(self.risk_free_rate * 100, 2),
            "theoretical_price": round(self.theoretical_price, 4),
            "intrinsic_value": round(self.intrinsic_value, 4),
            "time_value": round(self.time_value, 4),
            "delta": round(self.delta, 4),
            "gamma": round(self.gamma, 6),
            "theta_daily": round(self.theta_daily, 4),
            "vega_1pct": round(self.vega_1pct, 4),
            "rho_1pct": round(self.rho_1pct, 4),
        }


@dataclass
class OptionsChainSummary:
    """Aggregate statistics from an options chain."""

    put_call_ratio: float
    pc_signal: str  # "bearish" | "neutral" | "bullish"
    pc_sentiment_score: float  # -1.0 to +1.0
    total_call_oi: float
    total_put_oi: float
    max_pain_strike: Optional[float]  # strike with most total OI (calls + puts)
    iv_atm: Optional[float]  # ATM implied vol
    iv_skew: Optional[float]  # put IV - call IV (positive = fear)
    skew_signal: str  # "fear" | "neutral" | "greed"
    gamma_exposure_usd: float  # aggregate gamma (proxy for market maker hedging)
    interpretation: str

    def to_dict(self) -> dict:
        return {
            "put_call_ratio": round(self.put_call_ratio, 3),
            "pc_signal": self.pc_signal,
            "pc_sentiment_score": round(self.pc_sentiment_score, 4),
            "total_call_oi": round(self.total_call_oi, 2),
            "total_put_oi": round(self.total_put_oi, 2),
            "max_pain_strike": round(self.max_pain_strike, 0)
            if self.max_pain_strike
            else None,
            "iv_atm_pct": round(self.iv_atm * 100, 2) if self.iv_atm else None,
            "iv_skew_pct": round(self.iv_skew * 100, 2) if self.iv_skew else None,
            "skew_signal": self.skew_signal,
            "gamma_exposure_usd": round(self.gamma_exposure_usd, 2),
            "interpretation": self.interpretation,
        }


# ── Black-Scholes Engine ──────────────────────────────────────────────────────


class OptionsAnalyzer:
    """
    Black-Scholes options pricer and Greeks calculator.
    Also computes aggregate chain signals (P/C ratio, max pain, IV skew).
    """

    def __init__(self, risk_free_rate: float = 0.065):
        """
        risk_free_rate: annualized (0.065 = 6.5% RBI repo rate).
        """
        self.risk_free_rate = risk_free_rate

    def price_option(
        self,
        option_type: str,  # "call" or "put"
        spot: float,
        strike: float,
        days_to_expiry: int,
        implied_vol: float,  # annualized decimal
    ) -> Greeks:
        """Compute Black-Scholes price and all Greeks."""
        T = max(days_to_expiry, 1) / 365.0
        r = self.risk_free_rate
        S = spot
        K = strike
        σ = max(implied_vol, 0.01)

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * σ * σ) * T) / (σ * sqrt_T)
        d2 = d1 - σ * sqrt_T

        if option_type == "call":
            price = S * _Phi(d1) - K * math.exp(-r * T) * _Phi(d2)
            delta = _Phi(d1)
            intrinsic = max(0.0, S - K)
            rho = K * T * math.exp(-r * T) * _Phi(d2) / 100
        else:  # put
            price = K * math.exp(-r * T) * _Phi(-d2) - S * _Phi(-d1)
            delta = _Phi(d1) - 1.0
            intrinsic = max(0.0, K - S)
            rho = -K * T * math.exp(-r * T) * _Phi(-d2) / 100

        phi_d1 = _phi(d1)
        gamma = phi_d1 / (S * σ * sqrt_T)
        vega = S * sqrt_T * phi_d1 / 100  # per 1% IV move

        # Theta per calendar day
        theta_annual = -(S * phi_d1 * σ) / (2 * sqrt_T) - r * K * math.exp(-r * T) * (
            _Phi(d2) if option_type == "call" else _Phi(-d2)
        )
        theta_daily = theta_annual / 365.0

        time_value = max(0.0, price - intrinsic)

        return Greeks(
            option_type=option_type,
            spot=S,
            strike=K,
            days_to_expiry=days_to_expiry,
            implied_vol=σ,
            risk_free_rate=r,
            theoretical_price=round(price, 6),
            intrinsic_value=round(intrinsic, 6),
            time_value=round(time_value, 6),
            delta=round(delta, 6),
            gamma=round(gamma, 8),
            theta_daily=round(theta_daily, 6),
            vega_1pct=round(vega, 6),
            rho_1pct=round(rho, 6),
            d1=round(d1, 6),
            d2=round(d2, 6),
        )

    def estimate_iv(
        self,
        option_type: str,
        market_price: float,
        spot: float,
        strike: float,
        days_to_expiry: int,
        max_iter: int = 50,
        tol: float = 1e-5,
    ) -> Optional[float]:
        """
        Newton-Raphson IV solver.
        Returns implied vol (annualized decimal) or None if no convergence.
        """
        σ = 0.50  # initial guess: 50% IV
        for _ in range(max_iter):
            g = self.price_option(option_type, spot, strike, days_to_expiry, σ)
            diff = g.theoretical_price - market_price
            if abs(diff) < tol:
                return σ
            vega = g.vega_1pct * 100  # vega per unit IV
            if abs(vega) < 1e-10:
                break
            σ -= diff / vega
            σ = max(0.001, min(σ, 20.0))  # clamp 0.1% – 2000%
        return σ if σ > 0 else None

    def analyze_chain(
        self,
        spot: float,
        chain: List[Dict],
    ) -> OptionsChainSummary:
        """
        Analyze a list of option records.
        Each dict: {type, strike, oi, market_price, days_to_expiry}
        """
        calls = [o for o in chain if o.get("type") == "call"]
        puts = [o for o in chain if o.get("type") == "put"]

        total_call_oi = sum(o.get("oi", 0) for o in calls)
        total_put_oi = sum(o.get("oi", 0) for o in puts)

        pc_ratio = (total_put_oi / total_call_oi) if total_call_oi > 0 else 1.0

        # P/C signal
        if pc_ratio > 1.5:
            pc_signal = "bearish"
            pc_score = -0.8
        elif pc_ratio > 1.1:
            pc_signal = "slightly_bearish"
            pc_score = -0.4
        elif pc_ratio < 0.5:
            pc_signal = "bullish"
            pc_score = 0.8
        elif pc_ratio < 0.8:
            pc_signal = "slightly_bullish"
            pc_score = 0.4
        else:
            pc_signal = "neutral"
            pc_score = 0.0

        # Max pain: strike where total OI (calls above + puts below) is maximised
        all_strikes = sorted(set(o.get("strike", 0) for o in chain))
        max_pain = None
        if all_strikes:
            best = -1e18
            for k in all_strikes:
                call_pain = sum(
                    o.get("oi", 0) * max(0, k - o.get("strike", 0)) for o in calls
                )
                put_pain = sum(
                    o.get("oi", 0) * max(0, o.get("strike", 0) - k) for o in puts
                )
                pain = -(call_pain + put_pain)
                if pain > best:
                    best, max_pain = pain, k

        # ATM IV and skew
        atm_strikes = sorted(all_strikes, key=lambda k: abs(k - spot))
        atm_strike = atm_strikes[0] if atm_strikes else spot

        def _iv_for(type_: str, strike: float) -> Optional[float]:
            matches = [
                o for o in chain if o.get("type") == type_ and o.get("strike") == strike
            ]
            if not matches:
                return None
            o = matches[0]
            mp = o.get("market_price")
            if not mp or mp <= 0:
                return None
            return self.estimate_iv(type_, mp, spot, strike, o.get("days_to_expiry", 7))

        iv_call = _iv_for("call", atm_strike)
        iv_put = _iv_for("put", atm_strike)
        iv_atm = ((iv_call or 0) + (iv_put or 0)) / 2 if (iv_call or iv_put) else None

        iv_skew = None
        skew_signal = "neutral"
        if iv_call and iv_put:
            iv_skew = iv_put - iv_call
            if iv_skew > 0.10:
                skew_signal = "fear"
            elif iv_skew < -0.05:
                skew_signal = "greed"
            else:
                skew_signal = "neutral"

        # Aggregate gamma exposure (notional)
        gamma_exp = 0.0
        for o in chain:
            dte = o.get("days_to_expiry", 7)
            iv = o.get("iv", iv_atm or 0.80)
            if iv and iv > 0:
                g = self.price_option(o["type"], spot, o["strike"], dte, iv)
                gamma_exp += g.gamma * o.get("oi", 0) * spot * spot / 100

        # Interpretation
        parts = [f"P/C ratio: {pc_ratio:.2f} ({pc_signal})."]
        if max_pain:
            parts.append(f"Max pain: ${max_pain:,.0f}.")
        if iv_atm:
            parts.append(f"ATM IV: {iv_atm * 100:.1f}%.")
        if skew_signal == "fear":
            parts.append("Put skew elevated — market hedging downside risk.")
        elif skew_signal == "greed":
            parts.append("Call skew elevated — market pricing upside moves.")
        interp = " ".join(parts)

        return OptionsChainSummary(
            put_call_ratio=round(pc_ratio, 4),
            pc_signal=pc_signal,
            pc_sentiment_score=round(pc_score, 4),
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            max_pain_strike=max_pain,
            iv_atm=iv_atm,
            iv_skew=iv_skew,
            skew_signal=skew_signal,
            gamma_exposure_usd=round(gamma_exp, 2),
            interpretation=interp,
        )
