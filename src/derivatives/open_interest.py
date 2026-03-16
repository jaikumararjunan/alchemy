"""
Open Interest Analyzer.

Open Interest (OI) = total number of open contracts.
Key signals:
  Price ↑ + OI ↑  → trend continuation (new money flowing in) → bullish
  Price ↑ + OI ↓  → short covering rally (weak, may reverse) → cautious
  Price ↓ + OI ↑  → new shorts entering (bearish confirmation)
  Price ↓ + OI ↓  → long liquidation (near exhaustion) → potential reversal
"""

from dataclasses import dataclass
from collections import deque


@dataclass
class OIData:
    """Open interest analysis result."""

    current_oi: float
    oi_change_pct: float  # % change vs previous
    oi_change_1h_pct: float  # % change over last hour
    price_oi_signal: str  # "bullish_confirmation" | "bearish_confirmation" | "short_cover" | "long_liquidation" | "neutral"
    oi_trend: str  # "accumulating" | "distributing" | "stable"
    signal: str  # "bullish" | "bearish" | "cautious" | "neutral"
    sentiment_score: float  # -1.0 to +1.0
    signal_strength: float
    large_oi_change: bool  # > 5% in a single reading
    interpretation: str

    def to_dict(self) -> dict:
        return {
            "current_oi": round(self.current_oi, 2),
            "oi_change_pct": round(self.oi_change_pct, 4),
            "oi_change_1h_pct": round(self.oi_change_1h_pct, 4),
            "price_oi_signal": self.price_oi_signal,
            "oi_trend": self.oi_trend,
            "signal": self.signal,
            "sentiment_score": round(self.sentiment_score, 4),
            "signal_strength": round(self.signal_strength, 3),
            "large_oi_change": self.large_oi_change,
            "interpretation": self.interpretation,
        }


class OpenInterestAnalyzer:
    """
    Analyses open interest changes to identify market conviction.
    Combines OI delta with price delta for directional signals.
    """

    _LARGE_CHANGE_THRESHOLD = 0.05  # 5% OI change = notable
    _ACCUMULATION_THRESHOLD = 0.02  # 2% OI growth = accumulation
    _DISTRIBUTION_THRESHOLD = -0.02

    def __init__(self, history_size: int = 60):
        self._oi_history: deque = deque(maxlen=history_size)
        self._price_history: deque = deque(maxlen=history_size)

    def analyze(self, current_oi: float, current_price: float) -> OIData:
        oi_list = list(self._oi_history)
        prev_oi = oi_list[-1] if oi_list else current_oi
        hour_ago_oi = (
            oi_list[0]
            if len(oi_list) >= 60
            else (oi_list[0] if oi_list else current_oi)
        )

        price_list = list(self._price_history)
        prev_price = price_list[-1] if price_list else current_price

        self._oi_history.append(current_oi)
        self._price_history.append(current_price)

        # Point changes
        oi_chg = ((current_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0.0
        oi_chg_1h = (
            ((current_oi - hour_ago_oi) / hour_ago_oi * 100) if hour_ago_oi > 0 else 0.0
        )
        price_chg = current_price - prev_price

        large = abs(oi_chg) > self._LARGE_CHANGE_THRESHOLD * 100

        # OI trend over history
        if len(oi_list) >= 4:
            avg_oi = sum(oi_list) / len(oi_list)
            _ = (
                (current_oi - avg_oi) / avg_oi if avg_oi > 0 else 0
            )  # oi_pct_vs_avg (reserved)
            if oi_chg_1h > self._ACCUMULATION_THRESHOLD * 100:
                oi_trend = "accumulating"
            elif oi_chg_1h < self._DISTRIBUTION_THRESHOLD * 100:
                oi_trend = "distributing"
            else:
                oi_trend = "stable"
        else:
            oi_trend = "stable"

        # Price + OI matrix
        price_rising = price_chg > 0
        oi_rising = oi_chg > 0

        if price_rising and oi_rising:
            price_oi_signal = "bullish_confirmation"
            base_score = 0.70
        elif not price_rising and oi_rising:
            price_oi_signal = "bearish_confirmation"
            base_score = -0.70
        elif price_rising and not oi_rising:
            price_oi_signal = "short_cover"
            base_score = 0.20  # weak bullish, likely short squeeze
        else:
            price_oi_signal = "long_liquidation"
            base_score = -0.20  # could be near bottom

        # Scale by magnitude of OI change
        scale = min(1.0, abs(oi_chg) / (self._LARGE_CHANGE_THRESHOLD * 100))
        sentiment_score = round(base_score * max(0.3, scale), 4)
        signal_strength = round(abs(sentiment_score), 3)

        if sentiment_score >= 0.5:
            signal = "bullish"
        elif sentiment_score >= 0.15:
            signal = "cautious_bullish"
        elif sentiment_score <= -0.5:
            signal = "bearish"
        elif sentiment_score <= -0.15:
            signal = "cautious_bearish"
        else:
            signal = "neutral"

        # Interpretation
        if price_oi_signal == "bullish_confirmation":
            interp = (
                f"OI +{oi_chg:.2f}% with price rising. New longs entering — "
                "trend continuation signal. Strong bullish conviction."
            )
        elif price_oi_signal == "bearish_confirmation":
            interp = (
                f"OI +{oi_chg:.2f}% with price falling. New shorts entering — "
                "bearish conviction. Trend likely to continue down."
            )
        elif price_oi_signal == "short_cover":
            interp = (
                f"OI {oi_chg:.2f}% with price rising. Short covering — "
                "rally may be temporary. Watch for re-entry of sellers."
            )
        else:
            interp = (
                f"OI {oi_chg:.2f}% with price falling. Long liquidation — "
                "near exhaustion zone, possible reversal ahead."
            )

        return OIData(
            current_oi=current_oi,
            oi_change_pct=round(oi_chg, 4),
            oi_change_1h_pct=round(oi_chg_1h, 4),
            price_oi_signal=price_oi_signal,
            oi_trend=oi_trend,
            signal=signal,
            sentiment_score=sentiment_score,
            signal_strength=signal_strength,
            large_oi_change=large,
            interpretation=interp,
        )
