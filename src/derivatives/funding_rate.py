"""
Funding Rate Monitor for perpetual futures.

Delta Exchange charges funding every 8 hours on perpetual contracts.
Positive funding = longs pay shorts (market is long-biased → potentially bearish signal).
Negative funding = shorts pay longs (market is short-biased → potentially bullish signal).
"""

from dataclasses import dataclass
from collections import deque


@dataclass
class FundingRateData:
    """Current and historical funding rate analysis."""

    current_rate: float  # 8-hour rate (e.g. 0.0001 = 0.01%)
    annualized_rate_pct: float  # current_rate * 3 * 365 * 100
    rate_label: str  # "extreme_positive" | "high_positive" | "neutral" | "high_negative" | "extreme_negative"
    signal: str  # "bearish" | "slightly_bearish" | "neutral" | "slightly_bullish" | "bullish"
    signal_strength: float  # 0.0 – 1.0
    sentiment_score: float  # -1.0 (bearish) to +1.0 (bullish)
    avg_rate_7d: float  # 7-day average 8h rate
    trend: str  # "rising" | "falling" | "stable"
    cumulative_7d_pct: (
        float  # cumulative funding paid over 7d (= avg_rate * 21 payments)
    )
    interpretation: str

    def to_dict(self) -> dict:
        return {
            "current_rate": round(self.current_rate, 6),
            "current_rate_pct": round(self.current_rate * 100, 4),
            "annualized_rate_pct": round(self.annualized_rate_pct, 2),
            "rate_label": self.rate_label,
            "signal": self.signal,
            "signal_strength": round(self.signal_strength, 3),
            "sentiment_score": round(self.sentiment_score, 3),
            "avg_rate_7d": round(self.avg_rate_7d, 6),
            "trend": self.trend,
            "cumulative_7d_pct": round(self.cumulative_7d_pct, 4),
            "interpretation": self.interpretation,
        }


class FundingRateMonitor:
    """
    Monitors and analyses perpetual futures funding rates.
    Uses a contrarian approach: extreme positive funding is bearish (market over-extended long),
    extreme negative funding is bullish (market over-extended short).
    """

    # 8-hour thresholds
    _EXTREME_POS = 0.0010  # > 0.10% per 8h  = 109% annualized
    _HIGH_POS = 0.0003  # > 0.03% per 8h  = 32.8% annualized
    _NEUTRAL_BAND = 0.0001  # ±0.01% per 8h   — near baseline
    _HIGH_NEG = -0.0003
    _EXTREME_NEG = -0.0010

    def __init__(self, history_size: int = 21):  # 21 = 7 days × 3 payments/day
        self._history: deque = deque(maxlen=history_size)

    def update(self, rate: float):
        """Add a new 8-hour funding rate reading."""
        self._history.append(rate)

    def analyze(self, current_rate: float) -> FundingRateData:
        """Compute funding rate signals from the current 8h rate."""
        self.update(current_rate)

        # Annualized: 3 payments/day × 365 days
        annualized = current_rate * 3 * 365 * 100

        # Label
        if current_rate >= self._EXTREME_POS:
            label = "extreme_positive"
        elif current_rate >= self._HIGH_POS:
            label = "high_positive"
        elif current_rate <= self._EXTREME_NEG:
            label = "extreme_negative"
        elif current_rate <= self._HIGH_NEG:
            label = "high_negative"
        else:
            label = "neutral"

        # Contrarian sentiment score
        # Positive funding → shorts favoured → bearish bias
        norm = max(self._EXTREME_POS, abs(current_rate))
        raw_score = -current_rate / norm  # flip sign: positive funding → negative score
        sentiment_score = max(-1.0, min(1.0, raw_score))

        # Signal
        if sentiment_score >= 0.7:
            signal, strength = "bullish", abs(sentiment_score)
        elif sentiment_score >= 0.3:
            signal, strength = "slightly_bullish", abs(sentiment_score)
        elif sentiment_score <= -0.7:
            signal, strength = "bearish", abs(sentiment_score)
        elif sentiment_score <= -0.3:
            signal, strength = "slightly_bearish", abs(sentiment_score)
        else:
            signal, strength = "neutral", 0.1

        # 7d history
        history_list = list(self._history)
        avg_7d = sum(history_list) / len(history_list) if history_list else current_rate
        cum_7d = avg_7d * 21 * 100  # as percentage

        # Trend
        if len(history_list) >= 3:
            recent = sum(history_list[-3:]) / 3
            older = sum(history_list[:3]) / 3 if len(history_list) >= 6 else avg_7d
            if recent > older * 1.1:
                trend = "rising"
            elif recent < older * 0.9:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Interpretation
        rate_pct = current_rate * 100
        if label == "extreme_positive":
            interp = (
                f"Funding extremely high (+{rate_pct:.3f}%/8h). "
                "Market heavily long — contrarian BEARISH. High squeeze risk."
            )
        elif label == "high_positive":
            interp = (
                f"Funding elevated (+{rate_pct:.3f}%/8h). "
                "Longs paying premium — slightly bearish lean."
            )
        elif label == "extreme_negative":
            interp = (
                f"Funding extremely negative ({rate_pct:.3f}%/8h). "
                "Market heavily short — contrarian BULLISH. Short squeeze risk."
            )
        elif label == "high_negative":
            interp = (
                f"Funding negative ({rate_pct:.3f}%/8h). "
                "Shorts paying premium — slightly bullish lean."
            )
        else:
            interp = (
                f"Funding near neutral ({rate_pct:.4f}%/8h). No strong funding signal."
            )

        return FundingRateData(
            current_rate=current_rate,
            annualized_rate_pct=annualized,
            rate_label=label,
            signal=signal,
            signal_strength=round(strength, 3),
            sentiment_score=round(sentiment_score, 4),
            avg_rate_7d=avg_7d,
            trend=trend,
            cumulative_7d_pct=round(cum_7d, 4),
            interpretation=interp,
        )
