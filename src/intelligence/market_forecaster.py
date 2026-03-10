"""
Market Forecaster
=================
Analyses OHLCV candle data to produce:

  - ADX trend strength (Wilder smoothing)
  - Market regime detection  (trending / ranging / volatile)
  - Price forecast via linear-regression channel (1, 3, 5 periods ahead)
  - VWAP relative position
  - Pivot-point support / resistance levels (R1–R3, S1–S3)
  - Brokerage break-even distance (round-trip fee as % of margin)

All algorithms are pure-Python — no extra ML dependencies.
"""
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class ForecastResult:
    """Structured output of one MarketForecaster.forecast() call."""

    # Trend strength (ADX)
    adx: float = 0.0                     # 0–100; higher = stronger trend
    plus_di: float = 0.0                 # Positive Directional Indicator
    minus_di: float = 0.0                # Negative Directional Indicator
    trend_direction: str = "neutral"     # "bullish" | "bearish" | "neutral"
    trend_strength_label: str = "none"   # "very_strong"|"strong"|"moderate"|"weak"|"none"

    # Market regime
    market_regime: str = "ranging"       # "trending" | "ranging" | "volatile"
    regime_confidence: float = 0.0       # 0.0–1.0

    # Linear-regression price forecast
    forecast_price_1: Optional[float] = None   # 1 period ahead
    forecast_price_3: Optional[float] = None   # 3 periods ahead
    forecast_price_5: Optional[float] = None   # 5 periods ahead
    forecast_bias: str = "neutral"             # "bullish" | "bearish" | "neutral"
    forecast_slope_pct: float = 0.0            # Slope as % of price per period
    regression_r2: float = 0.0                 # Fit quality (0–1); trust score

    # VWAP
    vwap: Optional[float] = None
    vwap_position: str = "at"           # "above" | "below" | "at"
    vwap_distance_pct: float = 0.0      # % distance from VWAP (signed)

    # Support / resistance (pivot points)
    pivot_point: Optional[float] = None
    resistance_levels: List[float] = field(default_factory=list)   # [R1, R2, R3]
    support_levels: List[float] = field(default_factory=list)       # [S1, S2, S3]

    # Brokerage
    breakeven_move_pct: float = 0.0     # Min price move (% of margin) to net-profit after fees

    # Composite normalised score for strategy weighting (-1 = bearish, +1 = bullish)
    forecast_score: float = 0.0

    @property
    def is_trending(self) -> bool:
        return self.adx >= 25

    @property
    def is_strong_trend(self) -> bool:
        return self.adx >= 40


# ── Forecaster ────────────────────────────────────────────────────────────────

class MarketForecaster:
    """
    Computes trend strength, market regime, and forward price projection
    from a list of OHLCV candle dicts.

    Candle dict keys accepted (tries long form, then short form):
        close / c, high / h, low / l, open / o, volume / v
    """

    def __init__(self, config):
        tc = config.trading
        self.taker_fee = getattr(tc, "taker_fee_rate", 0.0005)
        self.leverage  = getattr(tc, "leverage", 5)
        logger.info("MarketForecaster initialised")

    # ── Public API ────────────────────────────────────────────────────────────

    def forecast(self, candles: List[Dict], current_price: float) -> ForecastResult:
        """
        Run full analysis on *candles* (oldest first) at *current_price*.
        Returns a populated ForecastResult.
        """
        result = ForecastResult()

        if len(candles) < 20:
            logger.warning("MarketForecaster: need ≥ 20 candles; returning empty result")
            return result

        closes = self._extract(candles, "close",  current_price)
        highs  = self._extract(candles, "high",   current_price)
        lows   = self._extract(candles, "low",    current_price)
        vols   = self._extract(candles, "volume", 1.0)

        # ── 1. ADX ────────────────────────────────────────────────────────────
        adx, plus_di, minus_di = self._adx(highs, lows, closes)
        result.adx       = round(adx, 2)
        result.plus_di   = round(plus_di, 2)
        result.minus_di  = round(minus_di, 2)

        if plus_di > minus_di:
            result.trend_direction = "bullish"
        elif minus_di > plus_di:
            result.trend_direction = "bearish"
        else:
            result.trend_direction = "neutral"

        if adx >= 50:
            result.trend_strength_label = "very_strong"
        elif adx >= 35:
            result.trend_strength_label = "strong"
        elif adx >= 25:
            result.trend_strength_label = "moderate"
        elif adx >= 15:
            result.trend_strength_label = "weak"
        else:
            result.trend_strength_label = "none"

        # ── 2. Market regime ──────────────────────────────────────────────────
        volatility = self._volatility(closes)
        if adx >= 25:
            result.market_regime      = "trending"
            result.regime_confidence  = min(adx / 60, 1.0)
        elif volatility > 0.04:          # daily std-dev > 4 %
            result.market_regime      = "volatile"
            result.regime_confidence  = min(volatility / 0.10, 1.0)
        else:
            result.market_regime      = "ranging"
            result.regime_confidence  = max(1.0 - adx / 25, 0.2)

        # ── 3. Linear-regression price forecast ───────────────────────────────
        sample = closes[-50:] if len(closes) >= 50 else closes
        slope, intercept, r2 = self._linreg(sample)
        n = len(sample)

        result.forecast_price_1  = round(slope * (n + 1) + intercept, 2)
        result.forecast_price_3  = round(slope * (n + 3) + intercept, 2)
        result.forecast_price_5  = round(slope * (n + 5) + intercept, 2)
        result.regression_r2     = round(r2, 4)
        result.forecast_slope_pct = round(slope / current_price * 100, 6) if current_price else 0.0

        if result.forecast_price_3 and result.forecast_price_3 > current_price * 1.001:
            result.forecast_bias = "bullish"
        elif result.forecast_price_3 and result.forecast_price_3 < current_price * 0.999:
            result.forecast_bias = "bearish"
        else:
            result.forecast_bias = "neutral"

        # ── 4. VWAP ───────────────────────────────────────────────────────────
        vwap = self._vwap(highs, lows, closes, vols)
        if vwap and vwap > 0:
            result.vwap = round(vwap, 2)
            dist = (current_price - vwap) / vwap * 100
            result.vwap_distance_pct = round(dist, 3)
            if current_price > vwap * 1.001:
                result.vwap_position = "above"
            elif current_price < vwap * 0.999:
                result.vwap_position = "below"
            else:
                result.vwap_position = "at"

        # ── 5. Pivot-point support / resistance ───────────────────────────────
        if highs and lows and closes:
            pp, r1, r2_lvl, r3, s1, s2, s3 = self._pivots(highs[-1], lows[-1], closes[-1])
            result.pivot_point       = round(pp, 2)
            result.resistance_levels = [round(r1, 2), round(r2_lvl, 2), round(r3, 2)]
            result.support_levels    = [round(s1, 2), round(s2, 2), round(s3, 2)]

        # ── 6. Brokerage break-even ───────────────────────────────────────────
        # Round-trip taker fee on notional, expressed as % of margin
        result.breakeven_move_pct = round(self.taker_fee * 2 * self.leverage * 100, 4)

        # ── 7. Composite score (-1 → +1) ──────────────────────────────────────
        result.forecast_score = self._composite(result, current_price)

        logger.debug(
            "Forecast: ADX=%.1f (%s) | regime=%s | bias=%s | score=%.3f | R²=%.3f",
            result.adx, result.trend_strength_label,
            result.market_regime, result.forecast_bias,
            result.forecast_score, r2,
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract(candles: List[Dict], key: str, default: float) -> List[float]:
        short = key[0]  # c, h, l, o, v
        return [
            float(c.get(key, c.get(short, c.get(f"{key}_price", default))))
            for c in candles
        ]

    @staticmethod
    def _adx(highs: List[float], lows: List[float],
              closes: List[float], period: int = 14) -> Tuple[float, float, float]:
        """Wilder-smoothed ADX; returns (adx, +DI, -DI)."""
        if len(closes) < period * 2 + 2:
            return 0.0, 0.0, 0.0

        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(1, len(closes)):
            h, l, pc = highs[i], lows[i], closes[i - 1]
            tr  = max(h - l, abs(h - pc), abs(l - pc))
            up  = highs[i] - highs[i - 1]
            dn  = lows[i - 1] - lows[i]
            pdm = up if up > dn and up > 0 else 0.0
            ndm = dn if dn > up and dn > 0 else 0.0
            tr_list.append(tr)
            pdm_list.append(pdm)
            ndm_list.append(ndm)

        def wilder_smooth(data: List[float], p: int) -> List[float]:
            out = [sum(data[:p])]
            for v in data[p:]:
                out.append(out[-1] - out[-1] / p + v)
            return out

        atr_s  = wilder_smooth(tr_list,  period)
        pdm_s  = wilder_smooth(pdm_list, period)
        ndm_s  = wilder_smooth(ndm_list, period)

        dx_vals, pdi_last, ndi_last = [], 0.0, 0.0
        for a, p, n in zip(atr_s, pdm_s, ndm_s):
            if a == 0:
                continue
            pdi = 100 * p / a
            ndi = 100 * n / a
            dsum = pdi + ndi
            dx_vals.append(100 * abs(pdi - ndi) / dsum if dsum else 0.0)
            pdi_last, ndi_last = pdi, ndi

        if len(dx_vals) < period:
            return 0.0, 0.0, 0.0

        adx_val = sum(dx_vals[-period:]) / period
        return adx_val, pdi_last, ndi_last

    @staticmethod
    def _linreg(closes: List[float]) -> Tuple[float, float, float]:
        """OLS linear regression; returns (slope, intercept, r²)."""
        n = len(closes)
        if n < 3:
            return 0.0, closes[-1] if closes else 0.0, 0.0

        xs = list(range(n))
        xm = sum(xs) / n
        ym = sum(closes) / n

        ssxy = sum((x - xm) * (y - ym) for x, y in zip(xs, closes))
        ssxx = sum((x - xm) ** 2 for x in xs)
        ssyy = sum((y - ym) ** 2 for y in closes)

        if ssxx == 0:
            return 0.0, ym, 0.0

        slope     = ssxy / ssxx
        intercept = ym - slope * xm
        r2        = (ssxy ** 2) / (ssxx * ssyy) if ssyy > 0 else 0.0
        return slope, intercept, r2

    @staticmethod
    def _vwap(highs: List[float], lows: List[float],
              closes: List[float], vols: List[float]) -> Optional[float]:
        """Volume-Weighted Average Price using typical price."""
        total_vol = sum(vols)
        if total_vol == 0:
            return None
        pv = sum((h + l + c) / 3 * v for h, l, c, v in zip(highs, lows, closes, vols))
        return pv / total_vol

    @staticmethod
    def _pivots(high: float, low: float, close: float) -> Tuple[float, ...]:
        """Standard pivot points: PP, R1, R2, R3, S1, S2, S3."""
        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        r3 = high + 2 * (pp - low)
        s3 = low  - 2 * (high - pp)
        return pp, r1, r2, r3, s1, s2, s3

    @staticmethod
    def _volatility(closes: List[float]) -> float:
        if len(closes) < 5:
            return 0.0
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
                   for i in range(1, len(closes)) if closes[i - 1] != 0]
        return statistics.stdev(returns) if len(returns) >= 2 else 0.0

    @staticmethod
    def _composite(result: "ForecastResult", price: float) -> float:
        """Blend ADX direction, regression bias, and VWAP into −1 → +1."""
        score, weight = 0.0, 0.0

        # 1. ADX directional component (+DI vs −DI)
        if result.adx > 15:
            di_sum = result.plus_di + result.minus_di
            di_diff = (result.plus_di - result.minus_di) / di_sum if di_sum else 0.0
            adx_w   = min(result.adx / 50, 1.0)
            score  += di_diff * adx_w * 0.40
            weight += 0.40

        # 2. Linear-regression forecast bias (trust only decent R²)
        if result.regression_r2 > 0.25:
            bias_map = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
            score  += bias_map.get(result.forecast_bias, 0.0) * result.regression_r2 * 0.35
            weight += 0.35

        # 3. VWAP position (capped at 2 % distance)
        if result.vwap and price:
            vwap_sig = max(-1.0, min(result.vwap_distance_pct / 2.0, 1.0))
            score  += vwap_sig * 0.25
            weight += 0.25

        return round(score / max(weight, 1.0), 4) if weight > 0 else 0.0
