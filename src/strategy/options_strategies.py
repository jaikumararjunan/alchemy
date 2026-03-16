"""
Crypto Options Trading Strategies for Alchemy.

Implements a pure-Python Black-Scholes-Merton pricer (no scipy dependency)
plus eight distinct options strategies suited to crypto markets (Deribit-style
BTC/ETH options, USDC-settled or coin-margined).

Pricer
------
  BSMPricer         — European vanilla call/put price + full Greeks

Strategies
----------
  1. LongCallStrategy       — directional bullish, limited downside
  2. LongPutStrategy        — directional bearish, limited downside
  3. CoveredCallStrategy    — hold spot + sell OTM call for income
  4. ProtectivePutStrategy  — hold spot + buy ATM put as insurance
  5. LongStraddleStrategy   — ATM call + put; bet on large move either way
  6. IronCondorStrategy     — range-bound: sell OTM strangle, buy wings
  7. BullCallSpreadStrategy — limited-risk bullish vertical spread
  8. BearPutSpreadStrategy  — limited-risk bearish vertical spread

Selector
--------
  OptionsStrategySelector   — picks the best strategy given market regime,
                              IV percentile, and sentiment score
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Normal distribution helpers (no scipy) ────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Cumulative standard normal distribution (Zelen & Severo approximation, error < 7.5e-8)."""
    if x < 0:
        return 1.0 - _norm_cdf(-x)
    p  = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    t = 1.0 / (1.0 + p * x)
    poly = t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))))
    return 1.0 - _norm_pdf(x) * poly


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


# ── BSM Pricer ────────────────────────────────────────────────────────────────


@dataclass
class Greeks:
    """Option sensitivity measures."""
    delta: float   # rate of change of price with respect to underlying
    gamma: float   # rate of change of delta
    theta: float   # daily time decay (USD per day)
    vega: float    # sensitivity to 1% change in IV (USD)
    rho: float     # sensitivity to 1% change in risk-free rate (USD)


@dataclass
class OptionPrice:
    """BSM pricing result."""
    theoretical: float  # fair value
    intrinsic: float    # max(0, S-K) for call, max(0, K-S) for put
    time_value: float   # theoretical - intrinsic
    greeks: Greeks
    d1: float
    d2: float


class BSMPricer:
    """
    Black-Scholes-Merton pricer for European crypto options.

    Crypto-specific notes:
      - `q` (continuous dividend yield) is zero for coin-settled options
        but can represent the borrow cost for USDC-settled structures.
      - IV for BTC/ETH typically ranges 60-150% annualised.
      - Use `dte` (days to expiry) for convenience; internally converted to T.

    Args:
        S    : current spot price (USD)
        K    : strike price (USD)
        dte  : days to expiry
        iv   : implied volatility as decimal (e.g. 0.80 for 80%)
        r    : risk-free rate (decimal, default 0.05)
        q    : continuous yield / borrow rate (decimal, default 0.0)
    """

    def __init__(
        self,
        S: float,
        K: float,
        dte: float,
        iv: float,
        r: float = 0.05,
        q: float = 0.0,
    ):
        self.S = S
        self.K = K
        self.T = max(dte / 365.0, 1e-6)   # avoid division by zero at expiry
        self.iv = max(iv, 0.001)
        self.r = r
        self.q = q

    def _d1_d2(self) -> Tuple[float, float]:
        vol_sqrt_T = self.iv * math.sqrt(self.T)
        d1 = (
            math.log(self.S / self.K)
            + (self.r - self.q + 0.5 * self.iv ** 2) * self.T
        ) / vol_sqrt_T
        d2 = d1 - vol_sqrt_T
        return d1, d2

    def call(self) -> OptionPrice:
        d1, d2 = self._d1_d2()
        disc_r = math.exp(-self.r * self.T)
        disc_q = math.exp(-self.q * self.T)
        price = (
            self.S * disc_q * _norm_cdf(d1)
            - self.K * disc_r * _norm_cdf(d2)
        )
        intrinsic = max(self.S - self.K, 0.0)
        return OptionPrice(
            theoretical=round(max(price, 0.0), 4),
            intrinsic=round(intrinsic, 4),
            time_value=round(max(price - intrinsic, 0.0), 4),
            greeks=self._greeks_call(d1, d2),
            d1=d1, d2=d2,
        )

    def put(self) -> OptionPrice:
        d1, d2 = self._d1_d2()
        disc_r = math.exp(-self.r * self.T)
        disc_q = math.exp(-self.q * self.T)
        price = (
            self.K * disc_r * _norm_cdf(-d2)
            - self.S * disc_q * _norm_cdf(-d1)
        )
        intrinsic = max(self.K - self.S, 0.0)
        return OptionPrice(
            theoretical=round(max(price, 0.0), 4),
            intrinsic=round(intrinsic, 4),
            time_value=round(max(price - intrinsic, 0.0), 4),
            greeks=self._greeks_put(d1, d2),
            d1=d1, d2=d2,
        )

    def _greeks_call(self, d1: float, d2: float) -> Greeks:
        disc_r = math.exp(-self.r * self.T)
        disc_q = math.exp(-self.q * self.T)
        sqrt_T = math.sqrt(self.T)
        pdf_d1 = _norm_pdf(d1)
        delta = disc_q * _norm_cdf(d1)
        gamma = disc_q * pdf_d1 / (self.S * self.iv * sqrt_T)
        # Theta: daily decay (divide annual by 365)
        theta = (
            -(self.S * disc_q * pdf_d1 * self.iv) / (2 * sqrt_T)
            - self.r * self.K * disc_r * _norm_cdf(d2)
            + self.q * self.S * disc_q * _norm_cdf(d1)
        ) / 365.0
        vega = self.S * disc_q * pdf_d1 * sqrt_T / 100  # per 1% IV move
        rho = self.K * self.T * disc_r * _norm_cdf(d2) / 100
        return Greeks(
            delta=round(delta, 4), gamma=round(gamma, 6),
            theta=round(theta, 4), vega=round(vega, 4), rho=round(rho, 4),
        )

    def _greeks_put(self, d1: float, d2: float) -> Greeks:
        disc_r = math.exp(-self.r * self.T)
        disc_q = math.exp(-self.q * self.T)
        sqrt_T = math.sqrt(self.T)
        pdf_d1 = _norm_pdf(d1)
        delta = disc_q * (_norm_cdf(d1) - 1)
        gamma = disc_q * pdf_d1 / (self.S * self.iv * sqrt_T)
        theta = (
            -(self.S * disc_q * pdf_d1 * self.iv) / (2 * sqrt_T)
            + self.r * self.K * disc_r * _norm_cdf(-d2)
            - self.q * self.S * disc_q * _norm_cdf(-d1)
        ) / 365.0
        vega = self.S * disc_q * pdf_d1 * sqrt_T / 100
        rho = -self.K * self.T * disc_r * _norm_cdf(-d2) / 100
        return Greeks(
            delta=round(delta, 4), gamma=round(gamma, 6),
            theta=round(theta, 4), vega=round(vega, 4), rho=round(rho, 4),
        )

    def implied_volatility(
        self, market_price: float, option_type: str = "call", tol: float = 1e-6, max_iter: int = 200
    ) -> Optional[float]:
        """Newton-Raphson IV solver from market price."""
        iv = self.iv  # initial guess
        for _ in range(max_iter):
            self.iv = iv
            if option_type == "call":
                p = self.call()
            else:
                p = self.put()
            vega = p.greeks.vega * 100   # vega per unit IV (not per 1%)
            diff = p.theoretical - market_price
            if abs(diff) < tol:
                return round(iv, 6)
            if abs(vega) < 1e-10:
                break
            iv -= diff / vega
            iv = max(iv, 0.001)
        return None


# ── Shared result type ────────────────────────────────────────────────────────


@dataclass
class OptionLeg:
    """A single leg within an options position."""
    option_type: str          # "call" | "put"
    strike: float
    dte: int                  # days to expiry
    direction: str            # "long" | "short"
    contracts: float          # number of contracts (1 contract = 0.1 BTC on Deribit)
    premium: float            # estimated premium per contract (USD or coin)
    delta: float
    theta: float              # daily decay
    vega: float


@dataclass
class OptionsSignal:
    """Complete trade signal for an options strategy."""
    strategy_name: str
    symbol: str               # e.g. "BTC"
    action: str               # "enter" | "hold" | "close"
    legs: List[OptionLeg]
    max_loss: float           # worst-case USD loss (negative = loss)
    max_profit: float         # best-case USD gain (positive = profit)
    breakeven_prices: List[float]
    net_premium: float        # positive = credit received, negative = debit paid
    net_delta: float          # total position delta
    net_theta: float          # total daily theta
    net_vega: float           # total vega (positive = long vol)
    confidence: float         # 0–1
    reasoning: str
    signal_sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def risk_reward_ratio(self) -> float:
        if self.max_loss == 0:
            return 0.0
        return abs(self.max_profit / self.max_loss)

    @property
    def is_valid(self) -> bool:
        return (
            self.action == "enter"
            and self.confidence >= 0.55
            and self.risk_reward_ratio >= 1.0
        )

    def to_dict(self) -> Dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "action": self.action,
            "legs": [
                {
                    "option_type": l.option_type,
                    "strike": l.strike,
                    "dte": l.dte,
                    "direction": l.direction,
                    "contracts": l.contracts,
                    "premium": l.premium,
                    "delta": l.delta,
                    "theta": l.theta,
                    "vega": l.vega,
                }
                for l in self.legs
            ],
            "max_loss": self.max_loss,
            "max_profit": self.max_profit,
            "breakeven_prices": self.breakeven_prices,
            "net_premium": self.net_premium,
            "net_delta": self.net_delta,
            "net_theta": self.net_theta,
            "net_vega": self.net_vega,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "signal_sources": self.signal_sources,
            "risk_reward_ratio": self.risk_reward_ratio,
            "timestamp": self.timestamp,
        }


def _hold(strategy_name: str, symbol: str, reason: str) -> OptionsSignal:
    return OptionsSignal(
        strategy_name=strategy_name, symbol=symbol, action="hold", legs=[],
        max_loss=0.0, max_profit=0.0, breakeven_prices=[],
        net_premium=0.0, net_delta=0.0, net_theta=0.0, net_vega=0.0,
        confidence=0.0, reasoning=reason,
    )


# ── Strategy 1: Long Call ─────────────────────────────────────────────────────


class LongCallStrategy:
    """
    Buy a slightly OTM call.

    Best when: bullish bias, IV is low-to-moderate (buy cheap vol),
    sentiment score >= 0.2, DTE 14-30 days.

    Risk:   Premium paid (debit)
    Reward: Unlimited above breakeven
    Delta:  +0.4 to +0.5 (OTM)
    """

    NAME = "Long Call"
    OTM_PCT = 0.03      # strike 3% above spot
    DTE = 21

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if sentiment_score < 0.2:
            return _hold(self.NAME, self.symbol, f"Sentiment {sentiment_score:.2f} < 0.20 — not bullish enough")
        if iv_percentile > 70:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% too high — premium expensive")

        strike = round(spot * (1 + self.OTM_PCT), -2)   # round to nearest $100
        pricer = BSMPricer(S=spot, K=strike, dte=self.DTE, iv=iv)
        priced = pricer.call()
        premium = priced.theoretical

        confidence = min(0.55 + sentiment_score * 0.3 + (70 - iv_percentile) / 200, 0.90)
        breakeven = round(strike + premium, 2)
        max_loss = -premium
        # Theoretical max profit: 3× premium is a common practical target
        max_profit = premium * 3

        leg = OptionLeg(
            option_type="call", strike=strike, dte=self.DTE, direction="long",
            contracts=1, premium=premium,
            delta=priced.greeks.delta, theta=priced.greeks.theta, vega=priced.greeks.vega,
        )
        logger.info(
            "%s ENTER | spot=%.0f strike=%.0f iv=%.0f%% premium=%.2f delta=%.2f",
            self.NAME, spot, strike, iv * 100, premium, priced.greeks.delta,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=[leg], max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[breakeven], net_premium=-premium,
            net_delta=priced.greeks.delta, net_theta=priced.greeks.theta,
            net_vega=priced.greeks.vega, confidence=confidence,
            reasoning=(
                f"Bullish sentiment ({sentiment_score:.2f}), IV={iv*100:.0f}% at {iv_percentile:.0f}th pct. "
                f"Buy {self.DTE}d {strike:.0f} call @ ${premium:.2f}. "
                f"Breakeven: ${breakeven:.0f}. Max loss: ${abs(max_loss):.2f}."
            ),
            signal_sources=[
                f"Sentiment score {sentiment_score:.2f}",
                f"IV percentile {iv_percentile:.0f}%",
                f"Strike {strike:.0f} ({self.OTM_PCT*100:.0f}% OTM)",
                f"Delta {priced.greeks.delta:.2f}",
            ],
        )


# ── Strategy 2: Long Put ──────────────────────────────────────────────────────


class LongPutStrategy:
    """
    Buy a slightly OTM put.

    Best when: bearish bias, IV low-to-moderate, sentiment score <= -0.2,
    DTE 14-30 days.

    Risk:   Premium paid
    Reward: Large gain as underlying falls toward zero
    Delta:  -0.4 to -0.5 (OTM)
    """

    NAME = "Long Put"
    OTM_PCT = 0.03
    DTE = 21

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if sentiment_score > -0.2:
            return _hold(self.NAME, self.symbol, f"Sentiment {sentiment_score:.2f} > -0.20 — not bearish enough")
        if iv_percentile > 70:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% too high — premium expensive")

        strike = round(spot * (1 - self.OTM_PCT), -2)
        pricer = BSMPricer(S=spot, K=strike, dte=self.DTE, iv=iv)
        priced = pricer.put()
        premium = priced.theoretical

        confidence = min(0.55 + abs(sentiment_score) * 0.3 + (70 - iv_percentile) / 200, 0.90)
        breakeven = round(strike - premium, 2)
        max_loss = -premium
        max_profit = strike - max(breakeven, 0)

        leg = OptionLeg(
            option_type="put", strike=strike, dte=self.DTE, direction="long",
            contracts=1, premium=premium,
            delta=priced.greeks.delta, theta=priced.greeks.theta, vega=priced.greeks.vega,
        )
        logger.info(
            "%s ENTER | spot=%.0f strike=%.0f iv=%.0f%% premium=%.2f delta=%.2f",
            self.NAME, spot, strike, iv * 100, premium, priced.greeks.delta,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=[leg], max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[breakeven], net_premium=-premium,
            net_delta=priced.greeks.delta, net_theta=priced.greeks.theta,
            net_vega=priced.greeks.vega, confidence=confidence,
            reasoning=(
                f"Bearish sentiment ({sentiment_score:.2f}), IV={iv*100:.0f}% at {iv_percentile:.0f}th pct. "
                f"Buy {self.DTE}d {strike:.0f} put @ ${premium:.2f}. "
                f"Breakeven: ${breakeven:.0f}."
            ),
            signal_sources=[
                f"Sentiment score {sentiment_score:.2f}",
                f"IV percentile {iv_percentile:.0f}%",
                f"Strike {strike:.0f} ({self.OTM_PCT*100:.0f}% OTM)",
                f"Delta {priced.greeks.delta:.2f}",
            ],
        )


# ── Strategy 3: Covered Call ──────────────────────────────────────────────────


class CoveredCallStrategy:
    """
    Sell an OTM call against an existing spot holding.

    Best when: mildly bullish or neutral; IV is elevated; you hold spot
    and want to collect premium income.

    Risk:   Opportunity cost if spot rallies above strike; spot downside
    Reward: Premium collected (capped upside above strike)
    Delta:  Long spot delta minus short call delta ≈ 0.5
    """

    NAME = "Covered Call"
    OTM_PCT = 0.08    # sell 8% OTM
    DTE = 14

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if sentiment_score < -0.1:
            return _hold(self.NAME, self.symbol, "Too bearish — covered call caps upside but spot may fall")
        if iv_percentile < 40:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% too low — not enough premium")

        strike = round(spot * (1 + self.OTM_PCT), -2)
        pricer = BSMPricer(S=spot, K=strike, dte=self.DTE, iv=iv)
        priced = pricer.call()
        premium = priced.theoretical

        confidence = min(0.60 + (iv_percentile - 40) / 150 + max(sentiment_score, 0) * 0.2, 0.88)
        breakeven = round(spot - premium, 2)
        max_profit = round((strike - spot) + premium, 2)  # if called away at strike
        # Risk: spot falls to zero (spot loss minus premium collected)
        max_loss = -(spot - premium)  # simplified to spot cost

        short_call_leg = OptionLeg(
            option_type="call", strike=strike, dte=self.DTE, direction="short",
            contracts=1, premium=premium,
            delta=-priced.greeks.delta, theta=-priced.greeks.theta, vega=-priced.greeks.vega,
        )
        net_delta = round(1.0 - priced.greeks.delta, 4)   # long spot + short call
        logger.info(
            "%s ENTER | spot=%.0f strike=%.0f premium=%.2f iv=%.0f%% iv_pct=%.0f",
            self.NAME, spot, strike, premium, iv * 100, iv_percentile,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=[short_call_leg], max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[breakeven], net_premium=premium,
            net_delta=net_delta, net_theta=-priced.greeks.theta,
            net_vega=-priced.greeks.vega, confidence=confidence,
            reasoning=(
                f"Neutral-to-bullish sentiment ({sentiment_score:.2f}), IV={iv*100:.0f}% at {iv_percentile:.0f}th pct. "
                f"Sell {self.DTE}d {strike:.0f} call @ ${premium:.2f} against spot. "
                f"Breakeven: ${breakeven:.0f}. Max gain: ${max_profit:.2f}."
            ),
            signal_sources=[
                f"IV percentile {iv_percentile:.0f}% (elevated)",
                f"OTM strike {strike:.0f} ({self.OTM_PCT*100:.0f}% above spot)",
                f"Premium collected ${premium:.2f}",
            ],
        )


# ── Strategy 4: Protective Put ────────────────────────────────────────────────


class ProtectivePutStrategy:
    """
    Buy an ATM or slightly OTM put as portfolio insurance.

    Best when: long spot; elevated downside risk; IV not too high.
    Acts as a hard floor on losses below the put strike.

    Risk:   Premium paid (insurance cost)
    Reward: Unlimited from spot upside; losses floored at strike
    Delta:  ≈ +0.5 (long spot + long put nearly cancel at ATM)
    """

    NAME = "Protective Put"
    OTM_PCT = 0.02    # 2% OTM (near-ATM)
    DTE = 30

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
        geopolitical_risk: str = "low",
    ) -> OptionsSignal:
        high_risk = geopolitical_risk in ("high", "critical")
        if iv_percentile > 80 and not high_risk:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% — insurance too expensive")

        strike = round(spot * (1 - self.OTM_PCT), -2)
        pricer = BSMPricer(S=spot, K=strike, dte=self.DTE, iv=iv)
        priced = pricer.put()
        premium = priced.theoretical

        risk_boost = 0.10 if high_risk else 0.0
        confidence = min(0.60 + risk_boost + max(-sentiment_score, 0) * 0.2, 0.90)
        breakeven_upside = round(spot + premium, 2)  # need spot to rise to cover cost
        max_loss = -premium                            # limited to premium if spot rises
        max_profit_downside = round(strike - premium, 2)  # gain if spot → 0

        leg = OptionLeg(
            option_type="put", strike=strike, dte=self.DTE, direction="long",
            contracts=1, premium=premium,
            delta=priced.greeks.delta, theta=priced.greeks.theta, vega=priced.greeks.vega,
        )
        net_delta = round(1.0 + priced.greeks.delta, 4)  # long spot + long put delta (negative)
        logger.info(
            "%s ENTER | spot=%.0f strike=%.0f premium=%.2f geo_risk=%s",
            self.NAME, spot, strike, premium, geopolitical_risk,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=[leg], max_loss=max_loss, max_profit=spot * 10,  # effectively unlimited up
            breakeven_prices=[breakeven_upside], net_premium=-premium,
            net_delta=net_delta, net_theta=priced.greeks.theta,
            net_vega=priced.greeks.vega, confidence=confidence,
            reasoning=(
                f"Geopolitical risk={geopolitical_risk}, sentiment={sentiment_score:.2f}. "
                f"Buy {self.DTE}d {strike:.0f} put @ ${premium:.2f} as insurance. "
                f"Floor on losses below ${strike:.0f}."
            ),
            signal_sources=[
                f"Geopolitical risk: {geopolitical_risk}",
                f"Sentiment {sentiment_score:.2f}",
                f"Put floor at ${strike:.0f}",
                f"Cost: ${premium:.2f}",
            ],
        )


# ── Strategy 5: Long Straddle ─────────────────────────────────────────────────


class LongStraddleStrategy:
    """
    Buy an ATM call AND ATM put with the same strike/expiry.

    Best when: expecting a large move but uncertain of direction
    (earnings analogue, macro catalyst, protocol upgrade).
    Profitable if spot moves more than the combined premium in either direction.

    Risk:   Combined premiums if spot stays flat (theta burns daily)
    Reward: Unlimited in either direction past breakevens
    Delta:  ≈ 0 at inception (delta-neutral)
    Vega:   Very long (profits from IV expansion)
    """

    NAME = "Long Straddle"
    DTE = 14    # shorter DTE = cheaper; but theta burns faster

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
        expected_move_pct: float = 0.0,
    ) -> OptionsSignal:
        if iv_percentile > 65:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% too high — straddle overpriced")
        if abs(sentiment_score) > 0.5:
            return _hold(self.NAME, self.symbol, "Strong directional bias — prefer outright call/put")

        strike = round(spot, -2)   # ATM (nearest $100)
        pricer = BSMPricer(S=spot, K=strike, dte=self.DTE, iv=iv)
        call_p = pricer.call()
        put_p = pricer.put()
        total_premium = call_p.theoretical + put_p.theoretical

        be_up = round(strike + total_premium, 2)
        be_dn = round(strike - total_premium, 2)
        max_loss = -total_premium
        # Practical max profit target: 2× premium (implied move ≫ premium)
        required_move_pct = total_premium / spot * 100

        # Fire when expected move > required move or when IV is cheap
        confidence = min(
            0.55
            + max(expected_move_pct - required_move_pct, 0) / 20
            + (65 - iv_percentile) / 100,
            0.88,
        )
        if confidence < 0.55:
            return _hold(self.NAME, self.symbol, f"Expected move {expected_move_pct:.1f}% ≤ required {required_move_pct:.1f}%")

        net_theta = call_p.greeks.theta + put_p.greeks.theta
        net_vega = call_p.greeks.vega + put_p.greeks.vega

        call_leg = OptionLeg(
            option_type="call", strike=strike, dte=self.DTE, direction="long",
            contracts=1, premium=call_p.theoretical,
            delta=call_p.greeks.delta, theta=call_p.greeks.theta, vega=call_p.greeks.vega,
        )
        put_leg = OptionLeg(
            option_type="put", strike=strike, dte=self.DTE, direction="long",
            contracts=1, premium=put_p.theoretical,
            delta=put_p.greeks.delta, theta=put_p.greeks.theta, vega=put_p.greeks.vega,
        )
        logger.info(
            "%s ENTER | spot=%.0f strike=%.0f total_prem=%.2f req_move=%.1f%%",
            self.NAME, spot, strike, total_premium, required_move_pct,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=[call_leg, put_leg], max_loss=max_loss, max_profit=total_premium * 5,
            breakeven_prices=[be_dn, be_up], net_premium=-total_premium,
            net_delta=round(call_p.greeks.delta + put_p.greeks.delta, 4),
            net_theta=net_theta, net_vega=net_vega, confidence=confidence,
            reasoning=(
                f"Neutral sentiment ({sentiment_score:.2f}), expecting big move. "
                f"ATM straddle at {strike:.0f} costs ${total_premium:.2f} ({required_move_pct:.1f}% move needed). "
                f"Breakevens: ${be_dn:.0f} / ${be_up:.0f}."
            ),
            signal_sources=[
                f"IV percentile {iv_percentile:.0f}% (cheap straddle)",
                f"Required move: {required_move_pct:.1f}%",
                f"Net theta: ${net_theta:.2f}/day",
                f"Net vega: ${net_vega:.2f}/1% IV",
            ],
        )


# ── Strategy 6: Iron Condor ───────────────────────────────────────────────────


class IronCondorStrategy:
    """
    Sell an OTM strangle (short call + short put) and buy further OTM wings.

    Best when: expecting range-bound price action; IV is elevated (sell premium).
    Defined-risk, defined-reward position.

    Structure:
      Sell OTM put  @ K_ps  (5% below spot)
      Buy  OTM put  @ K_pb  (8% below spot)  ← wing
      Sell OTM call @ K_cs  (5% above spot)
      Buy  OTM call @ K_cb  (8% above spot)  ← wing

    Risk:   Width of spread minus net credit collected
    Reward: Net credit collected
    Delta:  ≈ 0 at inception
    """

    NAME = "Iron Condor"
    CALL_SELL_PCT = 0.05
    CALL_BUY_PCT  = 0.08
    PUT_SELL_PCT  = 0.05
    PUT_BUY_PCT   = 0.08
    DTE = 21

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if iv_percentile < 55:
            return _hold(self.NAME, self.symbol, f"IV pct {iv_percentile:.0f}% too low — condor not juicy")
        if abs(sentiment_score) > 0.4:
            return _hold(self.NAME, self.symbol, "Directional sentiment too strong for range-bound condor")

        K_cs = round(spot * (1 + self.CALL_SELL_PCT), -2)
        K_cb = round(spot * (1 + self.CALL_BUY_PCT), -2)
        K_ps = round(spot * (1 - self.PUT_SELL_PCT), -2)
        K_pb = round(spot * (1 - self.PUT_BUY_PCT), -2)

        def price_leg(K, opt_type):
            return BSMPricer(S=spot, K=K, dte=self.DTE, iv=iv).__getattribute__(opt_type)()

        sc = price_leg(K_cs, "call")   # short call (sell)
        bc = price_leg(K_cb, "call")   # buy call wing
        sp = price_leg(K_ps, "put")    # short put (sell)
        bp = price_leg(K_pb, "put")    # buy put wing

        net_credit = (sc.theoretical - bc.theoretical) + (sp.theoretical - bp.theoretical)
        spread_width = K_cb - K_cs  # = K_ps - K_pb (symmetric)
        max_loss = -(spread_width - net_credit)
        max_profit = net_credit
        be_up = round(K_cs + net_credit, 2)
        be_dn = round(K_ps - net_credit, 2)

        if net_credit <= 0:
            return _hold(self.NAME, self.symbol, "Net credit is zero — condor not executable")

        confidence = min(0.60 + (iv_percentile - 55) / 100 + (0.4 - abs(sentiment_score)) * 0.3, 0.88)

        legs = [
            OptionLeg("call", K_cs, self.DTE, "short", 1, sc.theoretical, -sc.greeks.delta, -sc.greeks.theta, -sc.greeks.vega),
            OptionLeg("call", K_cb, self.DTE, "long",  1, bc.theoretical,  bc.greeks.delta,  bc.greeks.theta,  bc.greeks.vega),
            OptionLeg("put",  K_ps, self.DTE, "short", 1, sp.theoretical, -sp.greeks.delta, -sp.greeks.theta, -sp.greeks.vega),
            OptionLeg("put",  K_pb, self.DTE, "long",  1, bp.theoretical,  bp.greeks.delta,  bp.greeks.theta,  bp.greeks.vega),
        ]
        net_delta = sum(l.delta for l in legs)
        net_theta = sum(l.theta for l in legs)
        net_vega  = sum(l.vega  for l in legs)

        logger.info(
            "%s ENTER | spot=%.0f credit=%.2f max_loss=%.2f BEs=[%.0f,%.0f]",
            self.NAME, spot, net_credit, max_loss, be_dn, be_up,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=legs, max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[be_dn, be_up], net_premium=net_credit,
            net_delta=round(net_delta, 4), net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4), confidence=confidence,
            reasoning=(
                f"Range-bound view: sentiment={sentiment_score:.2f}, IV={iv*100:.0f}% @ {iv_percentile:.0f}th pct. "
                f"Iron condor credit=${net_credit:.2f} | max loss=${abs(max_loss):.2f} | "
                f"profit zone [{be_dn:.0f}, {be_up:.0f}]."
            ),
            signal_sources=[
                f"IV percentile {iv_percentile:.0f}% (elevated — good to sell)",
                f"Net credit ${net_credit:.2f}",
                f"Max loss ${abs(max_loss):.2f}",
                f"Profit zone ${be_dn:.0f}–${be_up:.0f}",
            ],
        )


# ── Strategy 7: Bull Call Spread ──────────────────────────────────────────────


class BullCallSpreadStrategy:
    """
    Buy an ATM call and sell a higher-strike OTM call.

    Reduces cost vs outright long call; caps upside at short strike.
    Best when: moderately bullish; IV elevated (offset premium with short leg).

    Risk:   Net debit (lower than outright call)
    Reward: Spread width minus net debit
    """

    NAME = "Bull Call Spread"
    LONG_OTM_PCT  = 0.0    # buy ATM
    SHORT_OTM_PCT = 0.05   # sell 5% OTM
    DTE = 21

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if sentiment_score < 0.15:
            return _hold(self.NAME, self.symbol, "Insufficient bullish sentiment for bull spread")

        K_long  = round(spot * (1 + self.LONG_OTM_PCT), -2)
        K_short = round(spot * (1 + self.SHORT_OTM_PCT), -2)

        lc = BSMPricer(S=spot, K=K_long,  dte=self.DTE, iv=iv).call()
        sc = BSMPricer(S=spot, K=K_short, dte=self.DTE, iv=iv).call()
        net_debit = lc.theoretical - sc.theoretical
        spread_width = K_short - K_long
        max_profit = spread_width - net_debit
        max_loss = -net_debit
        breakeven = round(K_long + net_debit, 2)

        if net_debit <= 0 or max_profit <= 0:
            return _hold(self.NAME, self.symbol, "Spread math invalid")

        rr = max_profit / abs(max_loss)
        confidence = min(0.55 + sentiment_score * 0.3 + (rr - 1) * 0.05, 0.88)

        legs = [
            OptionLeg("call", K_long,  self.DTE, "long",  1, lc.theoretical,  lc.greeks.delta,  lc.greeks.theta,  lc.greeks.vega),
            OptionLeg("call", K_short, self.DTE, "short", 1, sc.theoretical, -sc.greeks.delta, -sc.greeks.theta, -sc.greeks.vega),
        ]
        logger.info(
            "%s ENTER | spot=%.0f debit=%.2f max_profit=%.2f rr=%.1f",
            self.NAME, spot, net_debit, max_profit, rr,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=legs, max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[breakeven], net_premium=-net_debit,
            net_delta=round(lc.greeks.delta - sc.greeks.delta, 4),
            net_theta=round(lc.greeks.theta - sc.greeks.theta, 4),
            net_vega=round(lc.greeks.vega - sc.greeks.vega, 4),
            confidence=confidence,
            reasoning=(
                f"Bullish sentiment {sentiment_score:.2f}. Bull call spread {K_long:.0f}/{K_short:.0f}. "
                f"Net debit ${net_debit:.2f}, max profit ${max_profit:.2f} (RR {rr:.1f}x). "
                f"Breakeven: ${breakeven:.0f}."
            ),
            signal_sources=[
                f"Sentiment {sentiment_score:.2f}",
                f"Spread {K_long:.0f}/{K_short:.0f} call",
                f"R/R {rr:.1f}x",
                f"Net debit ${net_debit:.2f}",
            ],
        )


# ── Strategy 8: Bear Put Spread ───────────────────────────────────────────────


class BearPutSpreadStrategy:
    """
    Buy an ATM put and sell a lower-strike OTM put.

    Mirror image of bull call spread — defined risk, defined reward bearish play.
    Best when: moderately bearish; IV elevated.

    Risk:   Net debit
    Reward: Spread width minus net debit
    """

    NAME = "Bear Put Spread"
    LONG_OTM_PCT  = 0.0
    SHORT_OTM_PCT = 0.05
    DTE = 21

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
    ) -> OptionsSignal:
        if sentiment_score > -0.15:
            return _hold(self.NAME, self.symbol, "Insufficient bearish sentiment for bear spread")

        K_long  = round(spot * (1 - self.LONG_OTM_PCT), -2)   # ATM put (buy)
        K_short = round(spot * (1 - self.SHORT_OTM_PCT), -2)  # OTM put (sell)

        lp = BSMPricer(S=spot, K=K_long,  dte=self.DTE, iv=iv).put()
        sp = BSMPricer(S=spot, K=K_short, dte=self.DTE, iv=iv).put()
        net_debit = lp.theoretical - sp.theoretical
        spread_width = K_long - K_short
        max_profit = spread_width - net_debit
        max_loss = -net_debit
        breakeven = round(K_long - net_debit, 2)

        if net_debit <= 0 or max_profit <= 0:
            return _hold(self.NAME, self.symbol, "Spread math invalid")

        rr = max_profit / abs(max_loss)
        confidence = min(0.55 + abs(sentiment_score) * 0.3 + (rr - 1) * 0.05, 0.88)

        legs = [
            OptionLeg("put", K_long,  self.DTE, "long",  1, lp.theoretical,  lp.greeks.delta,  lp.greeks.theta,  lp.greeks.vega),
            OptionLeg("put", K_short, self.DTE, "short", 1, sp.theoretical, -sp.greeks.delta, -sp.greeks.theta, -sp.greeks.vega),
        ]
        logger.info(
            "%s ENTER | spot=%.0f debit=%.2f max_profit=%.2f rr=%.1f",
            self.NAME, spot, net_debit, max_profit, rr,
        )
        return OptionsSignal(
            strategy_name=self.NAME, symbol=self.symbol, action="enter",
            legs=legs, max_loss=max_loss, max_profit=max_profit,
            breakeven_prices=[breakeven], net_premium=-net_debit,
            net_delta=round(lp.greeks.delta - sp.greeks.delta, 4),
            net_theta=round(lp.greeks.theta - sp.greeks.theta, 4),
            net_vega=round(lp.greeks.vega - sp.greeks.vega, 4),
            confidence=confidence,
            reasoning=(
                f"Bearish sentiment {sentiment_score:.2f}. Bear put spread {K_long:.0f}/{K_short:.0f}. "
                f"Net debit ${net_debit:.2f}, max profit ${max_profit:.2f} (RR {rr:.1f}x). "
                f"Breakeven: ${breakeven:.0f}."
            ),
            signal_sources=[
                f"Sentiment {sentiment_score:.2f}",
                f"Spread {K_long:.0f}/{K_short:.0f} put",
                f"R/R {rr:.1f}x",
                f"Net debit ${net_debit:.2f}",
            ],
        )


# ── Selector ──────────────────────────────────────────────────────────────────


class OptionsStrategySelector:
    """
    Selects the most appropriate options strategy given current market conditions.

    Decision logic:
      sentiment >= +0.3 AND iv_pct < 50  → Long Call or Bull Call Spread
      sentiment >= +0.15                 → Bull Call Spread or Covered Call
      sentiment <= -0.3 AND iv_pct < 50  → Long Put or Bear Put Spread
      sentiment <= -0.15                 → Bear Put Spread
      abs(sentiment) < 0.15 AND iv_pct > 55 → Iron Condor
      abs(sentiment) < 0.15              → Long Straddle (expecting catalyst)
      geopolitical_risk in high/critical → Protective Put (always on)

    Args:
        symbol         : underlying asset (e.g. "BTC", "ETH")
        iv             : current implied volatility (decimal)
        spot           : current spot price
        sentiment_score: AI sentiment (-1 to +1)
        iv_percentile  : IV rank 0–100
        geopolitical_risk: "low" | "medium" | "high" | "critical"
        expected_move_pct: expected % move (for straddle sizing)
    """

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol
        self._strategies = {
            "long_call":       LongCallStrategy(symbol),
            "long_put":        LongPutStrategy(symbol),
            "covered_call":    CoveredCallStrategy(symbol),
            "protective_put":  ProtectivePutStrategy(symbol),
            "straddle":        LongStraddleStrategy(symbol),
            "iron_condor":     IronCondorStrategy(symbol),
            "bull_spread":     BullCallSpreadStrategy(symbol),
            "bear_spread":     BearPutSpreadStrategy(symbol),
        }

    def select_best(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
        geopolitical_risk: str = "low",
        expected_move_pct: float = 0.0,
    ) -> OptionsSignal:
        """Return the single highest-confidence actionable options signal."""
        candidates: List[OptionsSignal] = []

        g = self._strategies

        # Always check protective put when risk is elevated
        if geopolitical_risk in ("high", "critical"):
            sig = g["protective_put"].generate(spot, iv, sentiment_score, iv_percentile, geopolitical_risk)
            if sig.action == "enter":
                candidates.append(sig)

        if sentiment_score >= 0.2:
            candidates.append(g["long_call"].generate(spot, iv, sentiment_score, iv_percentile))
            candidates.append(g["bull_spread"].generate(spot, iv, sentiment_score, iv_percentile))
        elif sentiment_score >= 0.1:
            candidates.append(g["bull_spread"].generate(spot, iv, sentiment_score, iv_percentile))
            candidates.append(g["covered_call"].generate(spot, iv, sentiment_score, iv_percentile))

        if sentiment_score <= -0.2:
            candidates.append(g["long_put"].generate(spot, iv, sentiment_score, iv_percentile))
            candidates.append(g["bear_spread"].generate(spot, iv, sentiment_score, iv_percentile))
        elif sentiment_score <= -0.1:
            candidates.append(g["bear_spread"].generate(spot, iv, sentiment_score, iv_percentile))

        if abs(sentiment_score) < 0.15:
            candidates.append(g["iron_condor"].generate(spot, iv, sentiment_score, iv_percentile))
            candidates.append(g["straddle"].generate(spot, iv, sentiment_score, iv_percentile, expected_move_pct))

        actionable = [s for s in candidates if s.action == "enter" and s.confidence >= 0.55]
        if not actionable:
            return _hold("OptionsSelector", self.symbol, "No actionable options setup in current conditions")

        actionable.sort(key=lambda s: s.confidence, reverse=True)
        best = actionable[0]
        logger.info(
            "OptionsSelector: best=%s conf=%.2f legs=%d credit/debit=%.2f",
            best.strategy_name, best.confidence, len(best.legs), best.net_premium,
        )
        return best

    def run_all(
        self,
        spot: float,
        iv: float,
        sentiment_score: float,
        iv_percentile: float = 50.0,
        geopolitical_risk: str = "low",
        expected_move_pct: float = 0.0,
    ) -> List[OptionsSignal]:
        """Run every strategy and return all signals (actionable or not)."""
        g = self._strategies
        return [
            g["long_call"].generate(spot, iv, sentiment_score, iv_percentile),
            g["long_put"].generate(spot, iv, sentiment_score, iv_percentile),
            g["covered_call"].generate(spot, iv, sentiment_score, iv_percentile),
            g["protective_put"].generate(spot, iv, sentiment_score, iv_percentile, geopolitical_risk),
            g["straddle"].generate(spot, iv, sentiment_score, iv_percentile, expected_move_pct),
            g["iron_condor"].generate(spot, iv, sentiment_score, iv_percentile),
            g["bull_spread"].generate(spot, iv, sentiment_score, iv_percentile),
            g["bear_spread"].generate(spot, iv, sentiment_score, iv_percentile),
        ]
