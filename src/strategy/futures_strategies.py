"""
Crypto Futures Trading Strategies for Alchemy.

Covers both perpetual (no-expiry, funding-rate) and dated/quarterly futures.

Strategies
----------
  1. TrendFollowingFutures    — leveraged momentum on perps (ADX + EMA)
  2. FundingRateArbitrage     — exploit +/- funding via spot-hedge
  3. BasisTrade               — trade spot ↔ dated futures convergence
  4. PerpetualScalp           — tight RSI + volume scalp on perps
  5. LiquidationCascade       — detect OI clusters; ride forced-close wave
  6. CalendarSpread           — long near-dated / short far-dated (or vice-versa)

Selector
--------
  FuturesStrategySelector     — auto-picks best strategy from market state

Dataclasses
-----------
  FuturesContract             — describes a perp or dated contract
  FuturesSignal               — unified signal returned by all strategies
  FundingSnapshot             — funding rate + OI data for a perp
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Shared data types ─────────────────────────────────────────────────────────


@dataclass
class FuturesContract:
    """
    Describes a single futures instrument.

    For perpetuals: set `expiry_days=None` and populate `funding_rate_8h`.
    For dated contracts: set `expiry_days` and `annualised_basis_pct`.
    """

    symbol: str              # e.g. "BTCUSDT-PERP", "BTC-250328"
    contract_type: str       # "perpetual" | "dated"
    mark_price: float        # current mark price (USD)
    index_price: float       # spot index price (USD)
    funding_rate_8h: float   # 8-hour funding rate as decimal (perps only)
    open_interest_usd: float # total OI in USD
    volume_24h_usd: float    # 24h volume in USD
    leverage: float = 5.0    # default leverage for signals
    expiry_days: Optional[int] = None         # None for perps
    annualised_basis_pct: Optional[float] = None  # (futures_px - spot) / spot * (365/dte) * 100

    @property
    def basis_usd(self) -> float:
        """Absolute price difference between mark and index (futures premium/discount)."""
        return self.mark_price - self.index_price

    @property
    def basis_pct(self) -> float:
        """Basis as % of index price."""
        return (self.basis_usd / self.index_price * 100) if self.index_price > 0 else 0.0

    @property
    def funding_daily_pct(self) -> float:
        """Daily funding cost/income (3× 8-hour rates)."""
        return self.funding_rate_8h * 3 * 100   # as %

    @property
    def funding_annual_pct(self) -> float:
        return self.funding_daily_pct * 365


@dataclass
class FundingSnapshot:
    """Funding + OI data snapshot for decision logic."""
    symbol: str
    funding_rate_8h: float          # current 8h rate (decimal)
    predicted_funding_8h: float     # predicted next period funding
    oi_usd: float                   # open interest
    oi_change_pct_1h: float         # OI % change over last hour
    long_ratio: float               # long accounts / total (0–1)
    short_ratio: float              # short accounts / total (0–1)
    liquidations_1h_long_usd: float   # USD liquidated on long side past hour
    liquidations_1h_short_usd: float  # USD liquidated on short side past hour


@dataclass
class FuturesSignal:
    """Unified signal for any futures strategy."""

    strategy_name: str
    symbol: str
    action: str           # "long" | "short" | "close_long" | "close_short" | "hold"
    contract_type: str    # "perpetual" | "dated" | "spread"
    entry_price: float
    stop_loss: float
    take_profit: float
    leverage: float       # recommended leverage (1–20)
    position_size_pct: float   # fraction of trading capital (0–1)
    confidence: float          # 0–1
    expected_hold_hours: float # expected holding period
    reasoning: str
    funding_cost_daily_pct: float = 0.0  # ongoing carry cost (negative = paid, positive = received)
    annualised_yield_pct: float = 0.0    # annualised return for arb / basis trades
    signal_sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def risk_reward_ratio(self) -> float:
        risk   = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0.0

    @property
    def is_valid(self) -> bool:
        return (
            self.action not in ("hold",)
            and self.confidence >= 0.55
            and self.risk_reward_ratio >= 1.5
        )

    def to_dict(self) -> Dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "action": self.action,
            "contract_type": self.contract_type,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "leverage": self.leverage,
            "position_size_pct": self.position_size_pct,
            "confidence": self.confidence,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "expected_hold_hours": self.expected_hold_hours,
            "funding_cost_daily_pct": self.funding_cost_daily_pct,
            "annualised_yield_pct": self.annualised_yield_pct,
            "reasoning": self.reasoning,
            "signal_sources": self.signal_sources,
            "timestamp": self.timestamp,
        }


def _hold_fut(strategy_name: str, symbol: str, reason: str) -> FuturesSignal:
    return FuturesSignal(
        strategy_name=strategy_name, symbol=symbol, action="hold",
        contract_type="perpetual", entry_price=0.0, stop_loss=0.0, take_profit=0.0,
        leverage=1.0, position_size_pct=0.0, confidence=0.0,
        expected_hold_hours=0.0, reasoning=reason,
    )


# ── Technical helpers (reused from intraday_strategies where possible) ─────────


def _closes(candles: List[Dict]) -> List[float]:
    return [float(c.get("close", c.get("c", 0))) for c in candles]

def _highs(candles: List[Dict]) -> List[float]:
    return [float(c.get("high", c.get("h", 0))) for c in candles]

def _lows(candles: List[Dict]) -> List[float]:
    return [float(c.get("low", c.get("l", 0))) for c in candles]

def _volumes(candles: List[Dict]) -> List[float]:
    return [float(c.get("volume", c.get("v", 0))) for c in candles]

def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    emas = [values[0]]
    for v in values[1:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas

def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = [max(closes[i] - closes[i-1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag = statistics.mean(gains[-period:])
    al = statistics.mean(losses[-period:])
    return 100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))

def _adx(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        h, l, pc = highs[i], lows[i], closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up = highs[i] - highs[i-1]
        dn = lows[i-1] - lows[i]
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
        tr_list.append(tr)

    def smooth(vals, n):
        if len(vals) < n:
            return vals
        res = [sum(vals[:n])]
        for v in vals[n:]:
            res.append(res[-1] - res[-1] / n + v)
        return res

    atr = smooth(tr_list, period)
    sp = smooth(plus_dm, period)
    sm = smooth(minus_dm, period)
    if not atr:
        return 0.0
    dx = []
    for a, p, m in zip(atr, sp, sm):
        if a == 0:
            continue
        pdi, mdi = 100 * p / a, 100 * m / a
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0)
    return statistics.mean(dx[-period:]) if dx else 0.0


# ── Strategy 1: Trend Following Futures ───────────────────────────────────────


class TrendFollowingFutures:
    """
    Leveraged momentum trade on perpetual futures.

    Entry logic:
      LONG  — EMA20 > EMA50, ADX ≥ 25, price > EMA20, RSI 50–70 (not overbought)
      SHORT — EMA20 < EMA50, ADX ≥ 25, price < EMA20, RSI 30–50

    Position management:
      - Leverage: 3–5× depending on ADX strength
      - SL: 1.5× ATR below/above entry
      - TP: 3× ATR above/below entry (2:1 RR after leverage)
      - Reduce size to 50% if funding cost > 0.1% daily (carry headwind)
    """

    NAME = "Trend Following"
    MIN_ADX = 25.0
    EMA_FAST = 20
    EMA_SLOW = 50
    SL_ATR_MULT = 1.5
    TP_ATR_MULT = 3.0
    BASE_LEVERAGE = 5.0
    MAX_LEVERAGE = 10.0

    def __init__(self, symbol: str = "BTCUSDT-PERP"):
        self.symbol = symbol

    def generate(
        self, candles: List[Dict], contract: FuturesContract
    ) -> FuturesSignal:
        if len(candles) < self.EMA_SLOW + 5:
            return _hold_fut(self.NAME, self.symbol, f"Need ≥ {self.EMA_SLOW+5} candles")

        closes = _closes(candles)
        ema_fast = _ema(closes, self.EMA_FAST)
        ema_slow = _ema(closes, self.EMA_SLOW)
        rsi = _rsi(closes)
        adx = _adx(candles)

        price = contract.mark_price

        if rsi is None:
            return _hold_fut(self.NAME, self.symbol, "RSI unavailable")
        if adx < self.MIN_ADX:
            return _hold_fut(self.NAME, self.symbol, f"ADX {adx:.1f} < {self.MIN_ADX} — no trend")

        # ATR for SL/TP sizing
        highs = _highs(candles[-20:])
        lows = _lows(candles[-20:])
        cls = closes[-20:]
        atr = statistics.mean([
            max(highs[i] - lows[i], abs(highs[i] - cls[i-1]), abs(lows[i] - cls[i-1]))
            for i in range(1, len(highs))
        ])

        # Funding carry adjustment
        funding_daily = contract.funding_daily_pct
        size_factor = 0.5 if abs(funding_daily) > 0.1 else 1.0

        ema_f = ema_fast[-1]
        ema_s = ema_slow[-1]
        leverage = min(self.BASE_LEVERAGE + (adx - self.MIN_ADX) / 20, self.MAX_LEVERAGE)

        # LONG signal
        if ema_f > ema_s and price > ema_f and 50 <= rsi <= 72:
            confidence = min(0.60 + (adx - self.MIN_ADX) / 80 + (rsi - 50) / 100, 0.90)
            sl = round(price - self.SL_ATR_MULT * atr, 2)
            tp = round(price + self.TP_ATR_MULT * atr, 2)
            if funding_daily < -0.1:   # funding headwind for longs
                size_factor = 0.5
                confidence *= 0.9
            logger.info(
                "%s LONG | mark=%.0f ema_fast=%.0f ema_slow=%.0f ADX=%.1f RSI=%.1f lev=%.1fx",
                self.NAME, price, ema_f, ema_s, adx, rsi, leverage,
            )
            return FuturesSignal(
                strategy_name=self.NAME, symbol=self.symbol, action="long",
                contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
                leverage=round(leverage, 1), position_size_pct=round(0.10 * size_factor, 3),
                confidence=confidence, expected_hold_hours=8.0,
                funding_cost_daily_pct=funding_daily,
                reasoning=(
                    f"Trend Long: EMA{self.EMA_FAST}={ema_f:.0f} > EMA{self.EMA_SLOW}={ema_s:.0f}, "
                    f"ADX={adx:.1f}, RSI={rsi:.1f}, ATR={atr:.0f}. "
                    f"Funding {funding_daily:+.3f}%/day."
                ),
                signal_sources=[
                    f"EMA{self.EMA_FAST} > EMA{self.EMA_SLOW}",
                    f"ADX {adx:.1f}",
                    f"RSI {rsi:.1f}",
                    f"Leverage {leverage:.1f}×",
                ],
            )

        # SHORT signal
        if ema_f < ema_s and price < ema_f and 28 <= rsi <= 50:
            confidence = min(0.60 + (adx - self.MIN_ADX) / 80 + (50 - rsi) / 100, 0.90)
            sl = round(price + self.SL_ATR_MULT * atr, 2)
            tp = round(price - self.TP_ATR_MULT * atr, 2)
            if funding_daily > 0.1:   # positive funding = longs pay shorts (tailwind)
                confidence = min(confidence + 0.05, 0.92)
            logger.info(
                "%s SHORT | mark=%.0f ema_fast=%.0f ema_slow=%.0f ADX=%.1f lev=%.1fx",
                self.NAME, price, ema_f, ema_s, adx, leverage,
            )
            return FuturesSignal(
                strategy_name=self.NAME, symbol=self.symbol, action="short",
                contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
                leverage=round(leverage, 1), position_size_pct=round(0.10 * size_factor, 3),
                confidence=confidence, expected_hold_hours=8.0,
                funding_cost_daily_pct=-funding_daily,  # shorts receive positive funding
                reasoning=(
                    f"Trend Short: EMA{self.EMA_FAST}={ema_f:.0f} < EMA{self.EMA_SLOW}={ema_s:.0f}, "
                    f"ADX={adx:.1f}, RSI={rsi:.1f}. Funding {funding_daily:+.3f}%/day."
                ),
                signal_sources=[
                    f"EMA{self.EMA_FAST} < EMA{self.EMA_SLOW}",
                    f"ADX {adx:.1f}",
                    f"RSI {rsi:.1f}",
                    f"Leverage {leverage:.1f}×",
                ],
            )

        return _hold_fut(self.NAME, self.symbol, f"No trend setup | ADX={adx:.1f} RSI={rsi:.1f}")


# ── Strategy 2: Funding Rate Arbitrage ───────────────────────────────────────


class FundingRateArbitrage:
    """
    Exploit perpetual funding when it is anomalously high or low.

    When longs heavily dominate (funding > threshold):
      → Go SHORT perp + BUY spot (or long another correlated asset).
        Collect funding from longs every 8 hours.
        Hedge away directional risk via spot position.

    When shorts dominate (funding < -threshold):
      → Go LONG perp + SELL spot short / hedge.
        Collect funding from shorts.

    The trade is roughly delta-neutral; P&L comes from funding payments.
    Close when funding normalises toward zero.

    Parameters:
      funding_threshold_8h : minimum 8h rate to enter (default 0.05% = 5 bps)
      min_annual_yield_pct : minimum annualised carry to enter (default 15%)
    """

    NAME = "Funding Rate Arb"
    FUNDING_THRESHOLD_8H = 0.0005    # 0.05% per 8h
    MIN_ANNUAL_YIELD_PCT = 15.0

    def __init__(self, symbol: str = "BTCUSDT-PERP"):
        self.symbol = symbol

    def generate(
        self, contract: FuturesContract, funding: FundingSnapshot
    ) -> FuturesSignal:
        rate = funding.funding_rate_8h
        annual = rate * 3 * 365 * 100   # annualise the 8h rate

        if abs(rate) < self.FUNDING_THRESHOLD_8H:
            return _hold_fut(
                self.NAME, self.symbol,
                f"Funding {rate*100:.4f}% per 8h below {self.FUNDING_THRESHOLD_8H*100:.4f}% threshold",
            )
        if abs(annual) < self.MIN_ANNUAL_YIELD_PCT:
            return _hold_fut(
                self.NAME, self.symbol,
                f"Annualised yield {annual:.1f}% < {self.MIN_ANNUAL_YIELD_PCT}% minimum",
            )

        price = contract.mark_price
        # Delta-neutral: SL based on unexpected funding flip
        # Keep SL tight (2%) — directional risk is hedged via spot
        sl_pct = 0.02
        tp_pct = 0.005   # TP is small — we earn via funding carry not price move

        confidence = min(0.65 + abs(rate) / 0.01 * 0.05 + (abs(annual) - self.MIN_ANNUAL_YIELD_PCT) / 100, 0.92)

        if rate > 0:
            # Longs pay — SHORT the perp, BUY spot
            action = "short"
            sl = round(price * (1 + sl_pct), 2)
            tp = round(price * (1 - tp_pct), 2)
            funding_income = annual
        else:
            # Shorts pay — LONG the perp, SELL spot
            action = "long"
            sl = round(price * (1 - sl_pct), 2)
            tp = round(price * (1 + tp_pct), 2)
            funding_income = -annual  # receiving this as income

        logger.info(
            "%s %s | rate=%.4f%%/8h annual=%.1f%% mark=%.0f",
            self.NAME, action.upper(), rate * 100, annual, price,
        )
        return FuturesSignal(
            strategy_name=self.NAME, symbol=self.symbol, action=action,
            contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
            leverage=1.0,   # delta-neutral arb uses minimal leverage
            position_size_pct=0.15,   # 15% per leg (spot + perp)
            confidence=confidence, expected_hold_hours=8.0,
            funding_cost_daily_pct=funding.funding_rate_8h * 3 * 100,
            annualised_yield_pct=round(funding_income, 2),
            reasoning=(
                f"Funding arb: rate={rate*100:.4f}%/8h ({annual:.1f}% annual). "
                f"{action.upper()} perp + hedge spot. "
                f"Close when funding < {self.FUNDING_THRESHOLD_8H*100:.4f}%/8h."
            ),
            signal_sources=[
                f"8h funding rate {rate*100:.4f}%",
                f"Annualised yield {annual:.1f}%",
                f"Long/short ratio {funding.long_ratio:.0%}/{funding.short_ratio:.0%}",
                "Delta-neutral hedge required",
            ],
        )


# ── Strategy 3: Basis Trade ───────────────────────────────────────────────────


class BasisTrade:
    """
    Trade the convergence of dated futures basis back to zero at expiry.

    When futures trade at premium (contango):
      → SELL futures + BUY spot. Collect the basis as it decays to zero.

    When futures trade at discount (backwardation):
      → BUY futures + SELL spot. Capture basis widening or wait for expiry flip.

    The annualised basis (carry) is the key metric.
    Minimum 7% annualised carry required to trade.

    Parameters:
      min_annualised_basis_pct : minimum annualised carry to enter (default 7%)
      max_expiry_days          : don't trade with > 90 days to expiry (illiquid)
    """

    NAME = "Basis Trade"
    MIN_ANNUALISED_BASIS_PCT = 7.0
    MAX_EXPIRY_DAYS = 90
    MIN_EXPIRY_DAYS = 3     # too close to expiry = slippage risk

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self, spot: float, contract: FuturesContract
    ) -> FuturesSignal:
        if contract.contract_type != "dated":
            return _hold_fut(self.NAME, self.symbol, "Basis trade requires a dated futures contract")

        dte = contract.expiry_days or 0
        if dte < self.MIN_EXPIRY_DAYS or dte > self.MAX_EXPIRY_DAYS:
            return _hold_fut(
                self.NAME, self.symbol,
                f"DTE={dte} outside [{self.MIN_EXPIRY_DAYS}, {self.MAX_EXPIRY_DAYS}] range",
            )

        # Annualise the basis
        basis_pct = contract.basis_pct                              # % of spot
        annualised = basis_pct * (365.0 / dte)                     # annualised %
        if abs(annualised) < self.MIN_ANNUALISED_BASIS_PCT:
            return _hold_fut(
                self.NAME, self.symbol,
                f"Annualised basis {annualised:.1f}% < {self.MIN_ANNUALISED_BASIS_PCT}% minimum",
            )

        price = contract.mark_price
        # SL: basis unexpectedly widens 50% beyond current level
        sl_basis_move = abs(contract.basis_usd) * 0.5

        confidence = min(0.65 + (abs(annualised) - self.MIN_ANNUALISED_BASIS_PCT) / 50, 0.90)

        if basis_pct > 0:
            # Contango: sell futures, buy spot
            action = "short"
            sl = round(price + sl_basis_move, 2)
            tp = round(spot, 2)   # futures converge to spot at expiry
        else:
            # Backwardation: buy futures, sell spot
            action = "long"
            sl = round(price - sl_basis_move, 2)
            tp = round(spot, 2)

        logger.info(
            "%s %s | basis=%.2f%% annual=%.1f%% dte=%d",
            self.NAME, action.upper(), basis_pct, annualised, dte,
        )
        return FuturesSignal(
            strategy_name=self.NAME, symbol=self.symbol, action=action,
            contract_type="dated", entry_price=price, stop_loss=sl, take_profit=tp,
            leverage=1.0,   # basis trades use no/minimal leverage
            position_size_pct=0.20,
            confidence=confidence, expected_hold_hours=float(dte * 24),
            annualised_yield_pct=round(annualised, 2),
            reasoning=(
                f"Basis trade: {contract.symbol} at {basis_pct:+.2f}% basis ({annualised:+.1f}% annualised). "
                f"{action.upper()} futures + {'BUY' if action == 'short' else 'SELL'} spot. "
                f"Converges to zero at expiry in {dte} days."
            ),
            signal_sources=[
                f"Basis {basis_pct:+.2f}% of spot",
                f"Annualised carry {annualised:.1f}%",
                f"DTE {dte} days",
                "Cash-and-carry: delta neutral",
            ],
        )


# ── Strategy 4: Perpetual Scalp ───────────────────────────────────────────────


class PerpetualScalp:
    """
    High-frequency scalp on perpetual futures using RSI + volume + funding filter.

    Tighter than spot scalping because:
      - Funding is an ongoing cost → only scalp against expensive funding direction
      - Liquidation risk → use lower leverage (2–3×)
      - Mark price can deviate from index during volatility → use mark price for entry

    Entry:
      LONG  — RSI < 33, volume surge ≥ 1.2×, funding < 0.02%/8h (cheap to be long)
      SHORT — RSI > 67, volume surge ≥ 1.2×, funding > 0.02%/8h (expensive to be long)

    Exits:
      SL: 0.6% | TP: 1.0%
    """

    NAME = "Perpetual Scalp"
    SL_PCT = 0.006
    TP_PCT = 0.010
    RSI_OVERSOLD = 33
    RSI_OVERBOUGHT = 67
    VOL_SURGE = 1.2
    FUNDING_LONG_MAX = 0.0002    # max 8h funding to go long (don't fight expensive carry)
    LEVERAGE = 3.0

    def __init__(self, symbol: str = "BTCUSDT-PERP"):
        self.symbol = symbol

    def generate(
        self, candles: List[Dict], contract: FuturesContract
    ) -> FuturesSignal:
        if len(candles) < 22:
            return _hold_fut(self.NAME, self.symbol, "Need ≥ 22 candles")

        closes = _closes(candles)
        volumes = _volumes(candles)
        rsi = _rsi(closes)
        if rsi is None:
            return _hold_fut(self.NAME, self.symbol, "RSI unavailable")

        avg_vol = statistics.mean(volumes[-20:])
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0
        price = contract.mark_price
        funding = contract.funding_rate_8h

        if vol_ratio < self.VOL_SURGE:
            return _hold_fut(self.NAME, self.symbol, f"Volume {vol_ratio:.1f}× insufficient for scalp")

        # LONG
        if rsi < self.RSI_OVERSOLD and funding <= self.FUNDING_LONG_MAX:
            confidence = min(0.55 + (self.RSI_OVERSOLD - rsi) / 30 + (self.FUNDING_LONG_MAX - funding) * 100, 0.88)
            sl = round(price * (1 - self.SL_PCT), 2)
            tp = round(price * (1 + self.TP_PCT), 2)
            logger.info(
                "%s LONG | mark=%.0f RSI=%.1f vol=%.1fx funding=%.4f%%",
                self.NAME, price, rsi, vol_ratio, funding * 100,
            )
            return FuturesSignal(
                strategy_name=self.NAME, symbol=self.symbol, action="long",
                contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
                leverage=self.LEVERAGE, position_size_pct=0.05,
                confidence=confidence, expected_hold_hours=0.5,
                funding_cost_daily_pct=contract.funding_daily_pct,
                reasoning=(
                    f"Perp Scalp LONG: RSI={rsi:.1f} oversold, vol={vol_ratio:.1f}×, "
                    f"funding={funding*100:.4f}%/8h (manageable)."
                ),
                signal_sources=[
                    f"RSI oversold ({rsi:.1f})",
                    f"Volume {vol_ratio:.1f}× avg",
                    f"Funding {funding*100:.4f}%/8h",
                ],
            )

        # SHORT
        if rsi > self.RSI_OVERBOUGHT:
            # Positive funding is a tailwind for shorts
            funding_boost = max(funding - self.FUNDING_LONG_MAX, 0) * 50
            confidence = min(0.55 + (rsi - self.RSI_OVERBOUGHT) / 30 + funding_boost, 0.88)
            sl = round(price * (1 + self.SL_PCT), 2)
            tp = round(price * (1 - self.TP_PCT), 2)
            logger.info(
                "%s SHORT | mark=%.0f RSI=%.1f vol=%.1fx",
                self.NAME, price, rsi, vol_ratio,
            )
            return FuturesSignal(
                strategy_name=self.NAME, symbol=self.symbol, action="short",
                contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
                leverage=self.LEVERAGE, position_size_pct=0.05,
                confidence=confidence, expected_hold_hours=0.5,
                funding_cost_daily_pct=-contract.funding_daily_pct,  # receive funding
                reasoning=(
                    f"Perp Scalp SHORT: RSI={rsi:.1f} overbought, vol={vol_ratio:.1f}×, "
                    f"funding={funding*100:.4f}%/8h (collecting)."
                ),
                signal_sources=[
                    f"RSI overbought ({rsi:.1f})",
                    f"Volume {vol_ratio:.1f}× avg",
                    f"Collect funding {funding*100:.4f}%/8h",
                ],
            )

        return _hold_fut(self.NAME, self.symbol, f"No scalp setup | RSI={rsi:.1f} vol={vol_ratio:.1f}×")


# ── Strategy 5: Liquidation Cascade ──────────────────────────────────────────


class LiquidationCascadeStrategy:
    """
    Detect conditions that lead to liquidation cascades and ride the forced-close wave.

    Cascade conditions:
      LONG squeeze  — price below major OI cluster + large long liquidations last hour
                      + long/short ratio was heavily skewed to longs
      SHORT squeeze — price above major OI cluster + large short liquidations last hour
                      + long/short ratio was skewed to shorts

    After a cascade begins the move is usually fast and violent — use high leverage
    but very short hold time (30 min max), tight SL.

    Minimum thresholds:
      - Liq threshold: $5M+ liquidated in 1 hour on one side
      - OI drop > 5% in 1 hour (OI destroyed = liquidations happening)
    """

    NAME = "Liquidation Cascade"
    MIN_LIQ_USD = 5_000_000    # $5M liq threshold
    MIN_OI_DROP_PCT = 5.0      # OI must drop ≥ 5% in 1h
    SL_PCT = 0.008             # 0.8% stop (tight — fast moves)
    TP_PCT = 0.025             # 2.5% target
    LEVERAGE = 5.0

    def __init__(self, symbol: str = "BTCUSDT-PERP"):
        self.symbol = symbol

    def generate(
        self, contract: FuturesContract, funding: FundingSnapshot
    ) -> FuturesSignal:
        price = contract.mark_price
        oi_drop = funding.oi_change_pct_1h  # negative = OI declining (liq happening)
        long_liq = funding.liquidations_1h_long_usd
        short_liq = funding.liquidations_1h_short_usd

        # Need meaningful OI destruction
        if oi_drop > -self.MIN_OI_DROP_PCT and max(long_liq, short_liq) < self.MIN_LIQ_USD:
            return _hold_fut(
                self.NAME, self.symbol,
                f"OI drop {oi_drop:.1f}% and liq ${max(long_liq, short_liq)/1e6:.1f}M insufficient",
            )

        long_squeeze = (
            short_liq > self.MIN_LIQ_USD                    # shorts getting squeezed UP
            and funding.long_ratio < 0.35                    # market was short-heavy
            and contract.basis_usd > 0                       # perp at premium (longs pushing)
        )
        short_squeeze = (
            long_liq > self.MIN_LIQ_USD                     # longs getting liquidated DOWN
            and funding.long_ratio > 0.65                    # market was long-heavy
            and contract.basis_usd < 0                       # perp at discount (sells dominating)
        )

        if not long_squeeze and not short_squeeze:
            return _hold_fut(
                self.NAME, self.symbol,
                "OI/liq data present but squeeze conditions not met",
            )

        if long_squeeze:
            action = "long"
            sl = round(price * (1 - self.SL_PCT), 2)
            tp = round(price * (1 + self.TP_PCT), 2)
            liq_usd = short_liq
            confidence = min(0.65 + short_liq / self.MIN_LIQ_USD / 20 + abs(oi_drop) / 50, 0.92)
            desc = f"Short squeeze: ${short_liq/1e6:.1f}M shorts liquidated, OI -{abs(oi_drop):.1f}%"
        else:
            action = "short"
            sl = round(price * (1 + self.SL_PCT), 2)
            tp = round(price * (1 - self.TP_PCT), 2)
            liq_usd = long_liq
            confidence = min(0.65 + long_liq / self.MIN_LIQ_USD / 20 + abs(oi_drop) / 50, 0.92)
            desc = f"Long cascade: ${long_liq/1e6:.1f}M longs liquidated, OI -{abs(oi_drop):.1f}%"

        logger.info(
            "%s %s | mark=%.0f liq=$%.1fM OI_chg=%.1f%%",
            self.NAME, action.upper(), price, liq_usd/1e6, oi_drop,
        )
        return FuturesSignal(
            strategy_name=self.NAME, symbol=self.symbol, action=action,
            contract_type="perpetual", entry_price=price, stop_loss=sl, take_profit=tp,
            leverage=self.LEVERAGE, position_size_pct=0.08,
            confidence=confidence, expected_hold_hours=0.5,
            reasoning=desc + f" | Price={price:.0f} SL={sl:.0f} TP={tp:.0f}",
            signal_sources=[
                desc,
                f"Long/short ratio {funding.long_ratio:.0%}/{funding.short_ratio:.0%}",
                f"OI change {oi_drop:.1f}%/1h",
            ],
        )


# ── Strategy 6: Calendar Spread ───────────────────────────────────────────────


class CalendarSpreadStrategy:
    """
    Trade the spread between two dated futures contracts with different expiries.

    Structure:
      BULL CALENDAR — buy near-dated, sell far-dated (expect near < far to widen)
      BEAR CALENDAR — sell near-dated, buy far-dated (expect spread to narrow/flip)

    Edge:
      When the curve is in steep backwardation (near premium > far) and you expect
      normalisation, a bear calendar earns the roll-down.
      When the curve is in steep contango (far premium > near) and you expect carry
      to compress, a bull calendar earns the compression.

    Risk: Spread can widen further before converging. Both legs must be liquid.
    """

    NAME = "Calendar Spread"
    MIN_SPREAD_PCT = 1.5        # min absolute annualised spread between contracts (%)
    SL_SPREAD_WIDEN_PCT = 0.5  # SL if spread widens 0.5% more than entry

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol

    def generate(
        self,
        near_contract: FuturesContract,
        far_contract: FuturesContract,
        spot: float,
    ) -> FuturesSignal:
        if near_contract.contract_type != "dated" or far_contract.contract_type != "dated":
            return _hold_fut(self.NAME, self.symbol, "Both contracts must be dated")

        near_dte = near_contract.expiry_days or 1
        far_dte  = far_contract.expiry_days  or 1
        if near_dte >= far_dte:
            return _hold_fut(self.NAME, self.symbol, "Near DTE must be < far DTE")

        near_basis_ann = near_contract.basis_pct * (365.0 / near_dte)
        far_basis_ann  = far_contract.basis_pct  * (365.0 / far_dte)
        spread_ann = near_basis_ann - far_basis_ann   # positive = near at bigger premium

        if abs(spread_ann) < self.MIN_SPREAD_PCT:
            return _hold_fut(
                self.NAME, self.symbol,
                f"Ann. spread {spread_ann:.2f}% < {self.MIN_SPREAD_PCT}% minimum",
            )

        near_px = near_contract.mark_price
        far_px  = far_contract.mark_price
        spread_usd = near_px - far_px   # current spread in USD

        confidence = min(0.60 + (abs(spread_ann) - self.MIN_SPREAD_PCT) / 20, 0.88)

        # SL / TP in spread terms
        sl_spread = spread_usd + (self.SL_SPREAD_WIDEN_PCT / 100 * spot) * (1 if spread_usd > 0 else -1)
        tp_spread = 0.0   # target: spread collapses to zero (basis convergence)

        if spread_ann > 0:
            # Near is expensive vs far → BEAR calendar (sell near, buy far)
            action = "short"
            reasoning = (
                f"Bear calendar: near {near_contract.symbol} at {near_basis_ann:.1f}% ann. "
                f"vs far {far_contract.symbol} at {far_basis_ann:.1f}% ann. "
                f"Spread={spread_ann:.1f}% — expect compression."
            )
        else:
            # Far is expensive vs near → BULL calendar (buy near, sell far)
            action = "long"
            reasoning = (
                f"Bull calendar: near {near_contract.symbol} at {near_basis_ann:.1f}% ann. "
                f"vs far {far_contract.symbol} at {far_basis_ann:.1f}% ann. "
                f"Spread={spread_ann:.1f}% — expect near to catch up."
            )

        logger.info(
            "%s %s | near=%s far=%s spread_ann=%.1f%%",
            self.NAME, action.upper(), near_contract.symbol, far_contract.symbol, spread_ann,
        )
        return FuturesSignal(
            strategy_name=self.NAME, symbol=self.symbol, action=action,
            contract_type="spread",
            entry_price=near_px,     # reference: near leg price
            stop_loss=near_px + (sl_spread - spread_usd),
            take_profit=near_px - spread_usd,   # near converges toward far
            leverage=1.0, position_size_pct=0.12,
            confidence=confidence,
            expected_hold_hours=float(min(near_dte, 14) * 24),
            annualised_yield_pct=round(abs(spread_ann), 2),
            reasoning=reasoning,
            signal_sources=[
                f"Near ann. basis {near_basis_ann:.1f}%",
                f"Far ann. basis {far_basis_ann:.1f}%",
                f"Spread {spread_ann:+.1f}% annualised",
            ],
        )


# ── Selector ──────────────────────────────────────────────────────────────────


class FuturesStrategySelector:
    """
    Picks the best futures strategy given current market conditions.

    Priority ranking (highest to lowest):
      1. LiquidationCascade  — if cascade is detected (rare, high conviction)
      2. FundingRateArbitrage — when funding is extreme (delta-neutral, low risk)
      3. BasisTrade           — when dated futures basis is attractive
      4. CalendarSpread       — when spread between tenors is wide
      5. TrendFollowingFutures — default directional strategy
      6. PerpetualScalp       — fallback short-term

    All strategies are scored by confidence; the highest-confidence valid
    signal wins.

    Args:
        symbol          : base asset e.g. "BTC"
        candles         : recent OHLCV candle list
        perp_contract   : perpetual futures contract data
        funding         : current funding + OI snapshot
        near_contract   : near-dated contract (optional, for basis/calendar)
        far_contract    : far-dated contract (optional, for calendar)
        spot            : current spot price
    """

    def __init__(self, symbol: str = "BTC"):
        self.symbol = symbol
        self._trend    = TrendFollowingFutures(f"{symbol}USDT-PERP")
        self._funding  = FundingRateArbitrage(f"{symbol}USDT-PERP")
        self._basis    = BasisTrade(symbol)
        self._scalp    = PerpetualScalp(f"{symbol}USDT-PERP")
        self._cascade  = LiquidationCascadeStrategy(f"{symbol}USDT-PERP")
        self._calendar = CalendarSpreadStrategy(symbol)

    def select_best(
        self,
        candles: List[Dict],
        perp_contract: FuturesContract,
        funding: FundingSnapshot,
        spot: float = 0.0,
        near_contract: Optional[FuturesContract] = None,
        far_contract:  Optional[FuturesContract] = None,
    ) -> FuturesSignal:
        candidates: List[FuturesSignal] = []

        # Cascade (highest priority if present)
        sig = self._cascade.generate(perp_contract, funding)
        if sig.is_valid:
            candidates.append(sig)

        # Funding arb
        sig = self._funding.generate(perp_contract, funding)
        if sig.is_valid:
            candidates.append(sig)

        # Basis trade (needs near-dated contract)
        if near_contract and spot > 0:
            sig = self._basis.generate(spot, near_contract)
            if sig.is_valid:
                candidates.append(sig)

        # Calendar spread (needs both contracts)
        if near_contract and far_contract and spot > 0:
            sig = self._calendar.generate(near_contract, far_contract, spot)
            if sig.is_valid:
                candidates.append(sig)

        # Trend following
        sig = self._trend.generate(candles, perp_contract)
        if sig.is_valid:
            candidates.append(sig)

        # Scalp (lowest priority — fallback)
        sig = self._scalp.generate(candles, perp_contract)
        if sig.is_valid:
            candidates.append(sig)

        if not candidates:
            return _hold_fut("FuturesSelector", f"{self.symbol}USDT-PERP", "No valid futures setup")

        candidates.sort(key=lambda s: s.confidence, reverse=True)
        best = candidates[0]
        logger.info(
            "FuturesSelector: best=%s action=%s conf=%.2f",
            best.strategy_name, best.action, best.confidence,
        )
        return best

    def run_all(
        self,
        candles: List[Dict],
        perp_contract: FuturesContract,
        funding: FundingSnapshot,
        spot: float = 0.0,
        near_contract: Optional[FuturesContract] = None,
        far_contract:  Optional[FuturesContract] = None,
    ) -> List[FuturesSignal]:
        sigs = [
            self._cascade.generate(perp_contract, funding),
            self._funding.generate(perp_contract, funding),
            self._trend.generate(candles, perp_contract),
            self._scalp.generate(candles, perp_contract),
        ]
        if near_contract and spot > 0:
            sigs.append(self._basis.generate(spot, near_contract))
        if near_contract and far_contract and spot > 0:
            sigs.append(self._calendar.generate(near_contract, far_contract, spot))
        return sigs
