"""
Intraday Trading Strategies for Alchemy.

Five distinct strategies that generate TradeSignal objects:

  1. ScalpingStrategy       — 1-3 min, tight RSI + BB squeeze, 0.5% SL / 1.0% TP
  2. MomentumBreakoutStrategy — Breakout above/below key level with volume surge (ADX ≥ 25)
  3. MeanReversionStrategy  — RSI extreme + BB touch in ranging market (ADX < 20)
  4. VWAPBounceStrategy     — Price bounces off VWAP deviation band with RSI confirmation
  5. OpeningRangeBreakout   — Breakout of first N-candle range with volume confirmation

All strategies return TradeSignal compatible with the existing RiskManager and
TradingStrategy interface.  Use IntradayStrategySelector to auto-pick the best
strategy for the current market regime.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Shared result type (mirrors TradeSignal to remain compatible) ─────────────


@dataclass
class IntradaySignal:
    """Trade signal produced by an intraday strategy."""

    strategy_name: str
    action: str          # "buy" | "sell" | "hold" | "close_long" | "close_short"
    symbol: str
    confidence: float    # 0.0 – 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_multiplier: float  # 0.0 – 1.0
    reasoning: str
    signal_sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Fee fields (populated by caller / RiskManager)
    net_rr_after_fees: float = 0.0
    breakeven_move_pct: float = 0.0

    @property
    def risk_reward_ratio(self) -> float:
        if self.action == "buy":
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit - self.entry_price)
        elif self.action == "sell":
            risk = abs(self.stop_loss - self.entry_price)
            reward = abs(self.entry_price - self.take_profit)
        else:
            return 0.0
        return reward / risk if risk > 0 else 0.0

    @property
    def is_valid(self) -> bool:
        min_rr = self.net_rr_after_fees if self.net_rr_after_fees > 0 else self.risk_reward_ratio
        return (
            self.action in ("buy", "sell", "close_long", "close_short")
            and self.confidence >= 0.50
            and min_rr >= 1.5
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _closes(candles: List[Dict]) -> List[float]:
    return [float(c.get("close", c.get("c", 0))) for c in candles]


def _highs(candles: List[Dict]) -> List[float]:
    return [float(c.get("high", c.get("h", 0))) for c in candles]


def _lows(candles: List[Dict]) -> List[float]:
    return [float(c.get("low", c.get("l", 0))) for c in candles]


def _volumes(candles: List[Dict]) -> List[float]:
    return [float(c.get("volume", c.get("v", 0))) for c in candles]


def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_g = statistics.mean(gains[-period:])
    avg_l = statistics.mean(losses[-period:])
    if avg_l == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_g / avg_l))


def _bollinger(closes: List[float], period: int = 20) -> Tuple[float, float, float]:
    """Returns (upper, middle, lower)."""
    if len(closes) < period:
        m = closes[-1]
        return m, m, m
    window = closes[-period:]
    m = statistics.mean(window)
    s = statistics.stdev(window) if len(window) > 1 else 0.0
    return m + 2 * s, m, m - 2 * s


def _adx(candles: List[Dict], period: int = 14) -> float:
    """Simplified ADX calculation from OHLC candles."""
    if len(candles) < period + 1:
        return 0.0
    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr_list.append(tr)

    def _smooth(vals: List[float], n: int) -> List[float]:
        if len(vals) < n:
            return vals
        result = [sum(vals[:n])]
        for v in vals[n:]:
            result.append(result[-1] - result[-1] / n + v)
        return result

    atr = _smooth(tr_list, period)
    sp = _smooth(plus_dm, period)
    sm = _smooth(minus_dm, period)
    if not atr:
        return 0.0

    dx_vals = []
    for a, p, m in zip(atr, sp, sm):
        if a == 0:
            continue
        pdi = 100 * p / a
        mdi = 100 * m / a
        dx_vals.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0)

    return statistics.mean(dx_vals[-period:]) if dx_vals else 0.0


def _vwap(candles: List[Dict]) -> Optional[float]:
    """Session VWAP from candle list."""
    total_pv = total_v = 0.0
    for c in candles:
        h = float(c.get("high", c.get("h", 0)))
        l = float(c.get("low", c.get("l", 0)))
        cl = float(c.get("close", c.get("c", 0)))
        v = float(c.get("volume", c.get("v", 0)))
        tp = (h + l + cl) / 3.0
        total_pv += tp * v
        total_v += v
    return total_pv / total_v if total_v > 0 else None


# ── Strategy 1: Scalping ──────────────────────────────────────────────────────


class ScalpingStrategy:
    """
    Very short-term scalping strategy.

    Entry conditions:
      BUY  — RSI < 35 AND price at / below lower Bollinger Band
      SELL — RSI > 65 AND price at / above upper Bollinger Band

    Parameters:
      sl_pct  : 0.5% stop-loss
      tp_pct  : 1.0% take-profit (2:1 gross R:R)
      max_adx : reject if ADX > 30 (too trending — risk of runaway move)
    """

    NAME = "Scalping"
    SL_PCT = 0.005
    TP_PCT = 0.010
    MAX_ADX = 30.0
    RSI_OVERSOLD = 35.0
    RSI_OVERBOUGHT = 65.0

    def __init__(self, symbol: str):
        self.symbol = symbol

    def generate(self, candles: List[Dict], price: float) -> IntradaySignal:
        if len(candles) < 21:
            return self._hold(price, "Insufficient candles for scalping")

        closes = _closes(candles)
        rsi = _rsi(closes)
        bb_upper, bb_mid, bb_lower = _bollinger(closes)
        adx = _adx(candles)
        vols = _volumes(candles)
        avg_vol = statistics.mean(vols[-20:]) if len(vols) >= 20 else vols[-1]
        vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else 1.0

        sources: List[str] = []

        # Reject trending markets
        if adx > self.MAX_ADX:
            return self._hold(price, f"ADX {adx:.1f} too high for scalping")

        if rsi is None:
            return self._hold(price, "RSI unavailable")

        bb_range = bb_upper - bb_lower
        bb_pos = (price - bb_lower) / bb_range if bb_range > 0 else 0.5

        # BUY signal
        if rsi < self.RSI_OVERSOLD and bb_pos <= 0.15:
            sources = [f"RSI oversold ({rsi:.1f})", f"BB lower touch ({bb_pos:.2f})"]
            if vol_ratio >= 0.8:
                sources.append(f"Volume OK ({vol_ratio:.1f}x)")
            confidence = min(
                0.55 + (self.RSI_OVERSOLD - rsi) / 50.0 + (0.15 - bb_pos), 0.90
            )
            sl = round(price * (1 - self.SL_PCT), 2)
            tp = round(price * (1 + self.TP_PCT), 2)
            logger.info("Scalping BUY signal | price=%.2f RSI=%.1f ADX=%.1f", price, rsi, adx)
            return IntradaySignal(
                strategy_name=self.NAME,
                action="buy",
                symbol=self.symbol,
                confidence=confidence,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                position_size_multiplier=min(confidence * 0.8, 0.6),
                reasoning=f"Scalp BUY: RSI={rsi:.1f} BB_pos={bb_pos:.2f} ADX={adx:.1f} vol={vol_ratio:.1f}x",
                signal_sources=sources,
            )

        # SELL signal
        if rsi > self.RSI_OVERBOUGHT and bb_pos >= 0.85:
            sources = [f"RSI overbought ({rsi:.1f})", f"BB upper touch ({bb_pos:.2f})"]
            confidence = min(
                0.55 + (rsi - self.RSI_OVERBOUGHT) / 50.0 + (bb_pos - 0.85), 0.90
            )
            sl = round(price * (1 + self.SL_PCT), 2)
            tp = round(price * (1 - self.TP_PCT), 2)
            logger.info("Scalping SELL signal | price=%.2f RSI=%.1f ADX=%.1f", price, rsi, adx)
            return IntradaySignal(
                strategy_name=self.NAME,
                action="sell",
                symbol=self.symbol,
                confidence=confidence,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                position_size_multiplier=min(confidence * 0.8, 0.6),
                reasoning=f"Scalp SELL: RSI={rsi:.1f} BB_pos={bb_pos:.2f} ADX={adx:.1f}",
                signal_sources=sources,
            )

        return self._hold(price, f"No scalp setup | RSI={rsi:.1f} BB_pos={bb_pos:.2f}")

    def _hold(self, price: float, reason: str) -> IntradaySignal:
        return IntradaySignal(
            strategy_name=self.NAME, action="hold", symbol=self.symbol,
            confidence=0.0, entry_price=price, stop_loss=price, take_profit=price,
            position_size_multiplier=0.0, reasoning=reason,
        )


# ── Strategy 2: Momentum Breakout ─────────────────────────────────────────────


class MomentumBreakoutStrategy:
    """
    Trades breakouts above resistance / below support with volume confirmation.

    Entry conditions:
      BUY  — price breaks above N-candle high AND volume > 1.5x avg AND ADX ≥ 25
      SELL — price breaks below N-candle low  AND volume > 1.5x avg AND ADX ≥ 25

    Parameters:
      lookback   : candles used to define the breakout level (default 20)
      sl_pct     : 1.2% stop-loss (below/above breakout candle)
      rr_ratio   : minimum gross R:R 2.0 → TP at 2.4%
      min_adx    : require ADX ≥ 25 (trending market)
      vol_factor : volume must be ≥ 1.5x average
    """

    NAME = "Momentum Breakout"
    LOOKBACK = 20
    SL_PCT = 0.012
    TP_RATIO = 2.0       # TP = entry ± SL_PCT * TP_RATIO
    MIN_ADX = 25.0
    VOL_FACTOR = 1.5

    def __init__(self, symbol: str):
        self.symbol = symbol

    def generate(self, candles: List[Dict], price: float) -> IntradaySignal:
        if len(candles) < self.LOOKBACK + 2:
            return self._hold(price, "Insufficient candles for breakout")

        highs = _highs(candles)
        lows = _lows(candles)
        vols = _volumes(candles)
        adx = _adx(candles)

        # Use candles excluding the last one as the reference window
        ref_high = max(highs[-(self.LOOKBACK + 1):-1])
        ref_low = min(lows[-(self.LOOKBACK + 1):-1])
        avg_vol = statistics.mean(vols[-self.LOOKBACK:])
        cur_vol = vols[-1]
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

        if adx < self.MIN_ADX:
            return self._hold(price, f"ADX {adx:.1f} < {self.MIN_ADX} (not trending)")

        if vol_ratio < self.VOL_FACTOR:
            return self._hold(price, f"Volume {vol_ratio:.1f}x insufficient for breakout")

        tp_pct = self.SL_PCT * self.TP_RATIO

        # Bullish breakout
        if price > ref_high:
            breakout_pct = (price - ref_high) / ref_high
            confidence = min(0.60 + breakout_pct * 10 + (adx - self.MIN_ADX) / 100, 0.92)
            sl = round(price * (1 - self.SL_PCT), 2)
            tp = round(price * (1 + tp_pct), 2)
            logger.info(
                "Breakout BUY | price=%.2f ref_high=%.2f ADX=%.1f vol=%.1fx",
                price, ref_high, adx, vol_ratio,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="buy", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.9, 0.85),
                reasoning=(
                    f"Breakout BUY: price {price:.2f} > {self.LOOKBACK}-bar high {ref_high:.2f} "
                    f"| ADX={adx:.1f} vol={vol_ratio:.1f}x"
                ),
                signal_sources=[
                    f"Price breakout above {ref_high:.2f}",
                    f"ADX {adx:.1f}",
                    f"Volume {vol_ratio:.1f}x avg",
                ],
            )

        # Bearish breakout
        if price < ref_low:
            breakout_pct = (ref_low - price) / ref_low
            confidence = min(0.60 + breakout_pct * 10 + (adx - self.MIN_ADX) / 100, 0.92)
            sl = round(price * (1 + self.SL_PCT), 2)
            tp = round(price * (1 - tp_pct), 2)
            logger.info(
                "Breakout SELL | price=%.2f ref_low=%.2f ADX=%.1f vol=%.1fx",
                price, ref_low, adx, vol_ratio,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="sell", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.9, 0.85),
                reasoning=(
                    f"Breakout SELL: price {price:.2f} < {self.LOOKBACK}-bar low {ref_low:.2f} "
                    f"| ADX={adx:.1f} vol={vol_ratio:.1f}x"
                ),
                signal_sources=[
                    f"Price breakdown below {ref_low:.2f}",
                    f"ADX {adx:.1f}",
                    f"Volume {vol_ratio:.1f}x avg",
                ],
            )

        return self._hold(price, f"No breakout | range [{ref_low:.2f}, {ref_high:.2f}]")

    def _hold(self, price: float, reason: str) -> IntradaySignal:
        return IntradaySignal(
            strategy_name=self.NAME, action="hold", symbol=self.symbol,
            confidence=0.0, entry_price=price, stop_loss=price, take_profit=price,
            position_size_multiplier=0.0, reasoning=reason,
        )


# ── Strategy 3: Mean Reversion ────────────────────────────────────────────────


class MeanReversionStrategy:
    """
    Mean-reversion strategy for ranging / sideways markets.

    Entry conditions:
      BUY  — RSI < 30 AND price ≤ lower BB AND ADX < 20
      SELL — RSI > 70 AND price ≥ upper BB AND ADX < 20

    Target: reversion to BB mid-band (SMA-20).
    Stop: 1.5% beyond the BB extreme.

    Only fires in low-ADX (ranging) markets to avoid fighting a strong trend.
    """

    NAME = "Mean Reversion"
    MAX_ADX = 20.0
    RSI_OVERSOLD = 30.0
    RSI_OVERBOUGHT = 70.0
    SL_BUFFER = 0.015   # 1.5% beyond BB band

    def __init__(self, symbol: str):
        self.symbol = symbol

    def generate(self, candles: List[Dict], price: float) -> IntradaySignal:
        if len(candles) < 21:
            return self._hold(price, "Insufficient candles")

        closes = _closes(candles)
        rsi = _rsi(closes)
        bb_upper, bb_mid, bb_lower = _bollinger(closes)
        adx = _adx(candles)

        if adx > self.MAX_ADX:
            return self._hold(price, f"ADX {adx:.1f} > {self.MAX_ADX} — market trending")

        if rsi is None:
            return self._hold(price, "RSI unavailable")

        # BUY: oversold at lower band — expect reversion to mean
        if rsi < self.RSI_OVERSOLD and price <= bb_lower * 1.005:
            distance_to_mean = abs(bb_mid - price)
            confidence = min(
                0.55 + (self.RSI_OVERSOLD - rsi) / 30.0 + distance_to_mean / price * 5,
                0.88,
            )
            sl = round(bb_lower * (1 - self.SL_BUFFER), 2)
            tp = round(bb_mid, 2)
            logger.info(
                "MeanReversion BUY | price=%.2f RSI=%.1f BB_lower=%.2f ADX=%.1f",
                price, rsi, bb_lower, adx,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="buy", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.75, 0.70),
                reasoning=(
                    f"MeanRevert BUY: RSI={rsi:.1f} at BB_lower={bb_lower:.2f} "
                    f"target BB_mid={bb_mid:.2f} ADX={adx:.1f}"
                ),
                signal_sources=[
                    f"RSI oversold ({rsi:.1f})",
                    f"BB lower band ({bb_lower:.2f})",
                    f"ADX ranging ({adx:.1f})",
                ],
            )

        # SELL: overbought at upper band
        if rsi > self.RSI_OVERBOUGHT and price >= bb_upper * 0.995:
            distance_to_mean = abs(price - bb_mid)
            confidence = min(
                0.55 + (rsi - self.RSI_OVERBOUGHT) / 30.0 + distance_to_mean / price * 5,
                0.88,
            )
            sl = round(bb_upper * (1 + self.SL_BUFFER), 2)
            tp = round(bb_mid, 2)
            logger.info(
                "MeanReversion SELL | price=%.2f RSI=%.1f BB_upper=%.2f ADX=%.1f",
                price, rsi, bb_upper, adx,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="sell", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.75, 0.70),
                reasoning=(
                    f"MeanRevert SELL: RSI={rsi:.1f} at BB_upper={bb_upper:.2f} "
                    f"target BB_mid={bb_mid:.2f} ADX={adx:.1f}"
                ),
                signal_sources=[
                    f"RSI overbought ({rsi:.1f})",
                    f"BB upper band ({bb_upper:.2f})",
                    f"ADX ranging ({adx:.1f})",
                ],
            )

        return self._hold(
            price, f"No MR setup | RSI={rsi:.1f} ADX={adx:.1f} "
                   f"BB=[{bb_lower:.2f},{bb_upper:.2f}]"
        )

    def _hold(self, price: float, reason: str) -> IntradaySignal:
        return IntradaySignal(
            strategy_name=self.NAME, action="hold", symbol=self.symbol,
            confidence=0.0, entry_price=price, stop_loss=price, take_profit=price,
            position_size_multiplier=0.0, reasoning=reason,
        )


# ── Strategy 4: VWAP Bounce ───────────────────────────────────────────────────


class VWAPBounceStrategy:
    """
    Trades mean-reversion bounces around VWAP.

    Entry conditions:
      BUY  — price deviated ≥ vwap_band_pct BELOW VWAP AND RSI turns up (< 45)
      SELL — price deviated ≥ vwap_band_pct ABOVE VWAP AND RSI turns down (> 55)

    Target: reversion back to VWAP.
    Stop:   1.0% beyond deviation point.

    Best in moderate-trend or ranging sessions where VWAP acts as a magnet.
    """

    NAME = "VWAP Bounce"
    VWAP_BAND_PCT = 0.003   # 0.3% deviation triggers entry
    SL_PCT = 0.010
    RSI_UPPER = 55.0
    RSI_LOWER = 45.0

    def __init__(self, symbol: str):
        self.symbol = symbol

    def generate(self, candles: List[Dict], price: float) -> IntradaySignal:
        if len(candles) < 15:
            return self._hold(price, "Insufficient candles for VWAP")

        closes = _closes(candles)
        rsi = _rsi(closes)
        vwap = _vwap(candles)

        if vwap is None:
            return self._hold(price, "VWAP unavailable (zero volume?)")

        if rsi is None:
            return self._hold(price, "RSI unavailable")

        deviation = (price - vwap) / vwap  # positive = above, negative = below

        # BUY: price meaningfully below VWAP and RSI not yet overbought
        if deviation <= -self.VWAP_BAND_PCT and rsi < self.RSI_LOWER:
            dev_pct = abs(deviation) * 100
            confidence = min(0.55 + dev_pct * 2 + (self.RSI_LOWER - rsi) / 30, 0.88)
            sl = round(price * (1 - self.SL_PCT), 2)
            tp = round(vwap, 2)
            logger.info(
                "VWAP Bounce BUY | price=%.2f VWAP=%.2f dev=%.2f%% RSI=%.1f",
                price, vwap, deviation * 100, rsi,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="buy", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.80, 0.75),
                reasoning=(
                    f"VWAP Bounce BUY: price {deviation*100:.2f}% below VWAP={vwap:.2f} "
                    f"RSI={rsi:.1f}"
                ),
                signal_sources=[
                    f"Price below VWAP ({deviation*100:.2f}%)",
                    f"RSI={rsi:.1f}",
                    f"Target VWAP={vwap:.2f}",
                ],
            )

        # SELL: price meaningfully above VWAP and RSI not yet oversold
        if deviation >= self.VWAP_BAND_PCT and rsi > self.RSI_UPPER:
            dev_pct = abs(deviation) * 100
            confidence = min(0.55 + dev_pct * 2 + (rsi - self.RSI_UPPER) / 30, 0.88)
            sl = round(price * (1 + self.SL_PCT), 2)
            tp = round(vwap, 2)
            logger.info(
                "VWAP Bounce SELL | price=%.2f VWAP=%.2f dev=%.2f%% RSI=%.1f",
                price, vwap, deviation * 100, rsi,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="sell", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.80, 0.75),
                reasoning=(
                    f"VWAP Bounce SELL: price {deviation*100:.2f}% above VWAP={vwap:.2f} "
                    f"RSI={rsi:.1f}"
                ),
                signal_sources=[
                    f"Price above VWAP ({deviation*100:.2f}%)",
                    f"RSI={rsi:.1f}",
                    f"Target VWAP={vwap:.2f}",
                ],
            )

        return self._hold(
            price,
            f"No VWAP setup | dev={deviation*100:.2f}% RSI={rsi:.1f} VWAP={vwap:.2f}",
        )

    def _hold(self, price: float, reason: str) -> IntradaySignal:
        return IntradaySignal(
            strategy_name=self.NAME, action="hold", symbol=self.symbol,
            confidence=0.0, entry_price=price, stop_loss=price, take_profit=price,
            position_size_multiplier=0.0, reasoning=reason,
        )


# ── Strategy 5: Opening Range Breakout (ORB) ──────────────────────────────────


class OpeningRangeBreakout:
    """
    Trades the breakout of the opening range (first N candles of the session).

    Logic:
      1. Define opening range high/low from the first `opening_candles` bars.
      2. On the first candle that closes ABOVE range_high (with volume surge) → BUY.
      3. On the first candle that closes BELOW range_low  (with volume surge) → SELL.
      4. SL = opposite side of the opening range.
      5. TP = entry + 1× range size (1:1 minimum; actual RR typically 1.5–2.0 after fees).

    Parameters:
      opening_candles : number of candles forming the opening range (default 6 ≈ 30 min on 5-min bars)
      vol_factor      : required volume multiple vs. average (default 1.3)
    """

    NAME = "Opening Range Breakout"
    OPENING_CANDLES = 6
    VOL_FACTOR = 1.3
    SL_BUFFER = 0.001   # 0.1% beyond the range extreme

    def __init__(self, symbol: str, opening_candles: int = 6):
        self.symbol = symbol
        self.opening_candles = opening_candles

    def generate(self, candles: List[Dict], price: float) -> IntradaySignal:
        n = self.opening_candles
        if len(candles) < n + 2:
            return self._hold(price, f"Need ≥ {n+2} candles for ORB")

        opening = candles[:n]
        or_high = max(_highs(opening))
        or_low = min(_lows(opening))
        or_range = or_high - or_low

        if or_range <= 0:
            return self._hold(price, "Opening range is zero")

        vols = _volumes(candles)
        avg_vol = statistics.mean(vols[:n]) if n > 0 else 1.0
        cur_vol = vols[-1]
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

        closes = _closes(candles)
        last_close = closes[-1]

        # BUY breakout
        if last_close > or_high and vol_ratio >= self.VOL_FACTOR:
            confidence = min(
                0.60
                + (last_close - or_high) / or_range * 0.5
                + (vol_ratio - self.VOL_FACTOR) * 0.1,
                0.90,
            )
            sl = round(or_low * (1 - self.SL_BUFFER), 2)
            tp = round(or_high + or_range, 2)  # project 1× range above breakout
            logger.info(
                "ORB BUY | price=%.2f OR=[%.2f, %.2f] vol=%.1fx",
                price, or_low, or_high, vol_ratio,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="buy", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.85, 0.80),
                reasoning=(
                    f"ORB BUY: close {last_close:.2f} > OR_high {or_high:.2f} "
                    f"(range={or_range:.2f}) vol={vol_ratio:.1f}x"
                ),
                signal_sources=[
                    f"ORB breakout above {or_high:.2f}",
                    f"Volume {vol_ratio:.1f}x",
                    f"TP target {or_high + or_range:.2f}",
                ],
            )

        # SELL breakout
        if last_close < or_low and vol_ratio >= self.VOL_FACTOR:
            confidence = min(
                0.60
                + (or_low - last_close) / or_range * 0.5
                + (vol_ratio - self.VOL_FACTOR) * 0.1,
                0.90,
            )
            sl = round(or_high * (1 + self.SL_BUFFER), 2)
            tp = round(or_low - or_range, 2)  # project 1× range below breakdown
            logger.info(
                "ORB SELL | price=%.2f OR=[%.2f, %.2f] vol=%.1fx",
                price, or_low, or_high, vol_ratio,
            )
            return IntradaySignal(
                strategy_name=self.NAME, action="sell", symbol=self.symbol,
                confidence=confidence, entry_price=price, stop_loss=sl, take_profit=tp,
                position_size_multiplier=min(confidence * 0.85, 0.80),
                reasoning=(
                    f"ORB SELL: close {last_close:.2f} < OR_low {or_low:.2f} "
                    f"(range={or_range:.2f}) vol={vol_ratio:.1f}x"
                ),
                signal_sources=[
                    f"ORB breakdown below {or_low:.2f}",
                    f"Volume {vol_ratio:.1f}x",
                    f"TP target {or_low - or_range:.2f}",
                ],
            )

        return self._hold(
            price,
            f"Price inside OR [{or_low:.2f}, {or_high:.2f}] or vol too low ({vol_ratio:.1f}x)",
        )

    def _hold(self, price: float, reason: str) -> IntradaySignal:
        return IntradaySignal(
            strategy_name=self.NAME, action="hold", symbol=self.symbol,
            confidence=0.0, entry_price=price, stop_loss=price, take_profit=price,
            position_size_multiplier=0.0, reasoning=reason,
        )


# ── Strategy Selector ─────────────────────────────────────────────────────────


class IntradayStrategySelector:
    """
    Auto-selects the best intraday strategy based on current market regime.

    Regime detection (via ADX):
      ADX ≥ 30 and price > N-bar high → Momentum Breakout or ORB
      ADX ≥ 25                        → Momentum Breakout
      ADX < 20                        → Mean Reversion or VWAP Bounce
      Otherwise                       → VWAP Bounce or Scalping

    Returns a ranked list of (strategy_name, IntradaySignal) tuples sorted by
    confidence so the caller can pick the best actionable signal.
    """

    def __init__(self, symbol: str, opening_candles: int = 6):
        self.scalping = ScalpingStrategy(symbol)
        self.breakout = MomentumBreakoutStrategy(symbol)
        self.mean_reversion = MeanReversionStrategy(symbol)
        self.vwap_bounce = VWAPBounceStrategy(symbol)
        self.orb = OpeningRangeBreakout(symbol, opening_candles)

    def select_best(
        self, candles: List[Dict], price: float, session_start: bool = False
    ) -> IntradaySignal:
        """
        Run all strategies and return the highest-confidence actionable signal.

        Args:
            candles       : OHLCV candle list (newest last)
            price         : current market price
            session_start : True during the first `opening_candles` bars of the session
                            (enables ORB priority)
        """
        signals: List[IntradaySignal] = []

        # Always run all strategies
        signals.append(self.scalping.generate(candles, price))
        signals.append(self.breakout.generate(candles, price))
        signals.append(self.mean_reversion.generate(candles, price))
        signals.append(self.vwap_bounce.generate(candles, price))
        signals.append(self.orb.generate(candles, price))

        # Filter to actionable signals
        actionable = [s for s in signals if s.action not in ("hold",) and s.confidence >= 0.50]

        if not actionable:
            # Return the hold with most detail (from scalping as default)
            return signals[0]

        # Sort by confidence descending; give ORB a slight boost early in session
        def _rank(sig: IntradaySignal) -> float:
            boost = 0.05 if (session_start and sig.strategy_name == self.orb.NAME) else 0.0
            return sig.confidence + boost

        actionable.sort(key=_rank, reverse=True)
        best = actionable[0]
        logger.info(
            "IntradaySelector: best=%s action=%s conf=%.2f (from %d candidates)",
            best.strategy_name, best.action, best.confidence, len(actionable),
        )
        return best

    def run_all(
        self, candles: List[Dict], price: float
    ) -> List[Tuple[str, IntradaySignal]]:
        """Return all signals from all strategies as (name, signal) pairs."""
        return [
            (self.scalping.NAME, self.scalping.generate(candles, price)),
            (self.breakout.NAME, self.breakout.generate(candles, price)),
            (self.mean_reversion.NAME, self.mean_reversion.generate(candles, price)),
            (self.vwap_bounce.NAME, self.vwap_bounce.generate(candles, price)),
            (self.orb.NAME, self.orb.generate(candles, price)),
        ]
