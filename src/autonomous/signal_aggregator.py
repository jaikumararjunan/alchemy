"""
Multi-timeframe signal aggregator.
Combines signals across 1h, 4h, 1d timeframes for higher confidence entries.
"""

from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime, timezone


@dataclass
class TimeframeSignal:
    timeframe: str
    trend: str
    rsi: float
    macd_signal: str  # "bullish", "bearish", "neutral"
    bb_signal: str  # "oversold", "overbought", "neutral"
    volume_signal: str
    score: float  # -1.0 to 1.0
    weight: float  # importance of this timeframe


@dataclass
class AggregatedSignal:
    weighted_score: float
    agreement_pct: float  # % of timeframes in agreement
    primary_trend: str
    confluence_level: str  # "high", "medium", "low"
    recommended_action: str
    timeframe_signals: List[TimeframeSignal] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SignalAggregator:
    """
    Aggregates signals across multiple timeframes.
    Higher timeframe agreement = higher confidence = larger position.
    """

    TIMEFRAME_WEIGHTS = {
        "1m": 0.05,
        "5m": 0.10,
        "15m": 0.15,
        "1h": 0.25,
        "4h": 0.25,
        "1d": 0.20,
    }

    def aggregate(self, tf_signals: Dict[str, dict]) -> AggregatedSignal:
        """
        Aggregate technical indicators from multiple timeframes.

        Args:
            tf_signals: Dict mapping timeframe -> technical indicator dict

        Returns:
            AggregatedSignal with consensus view
        """
        signals = []
        for tf, indicators in tf_signals.items():
            score = self._score_timeframe(indicators)
            weight = self.TIMEFRAME_WEIGHTS.get(tf, 0.1)
            signals.append(
                TimeframeSignal(
                    timeframe=tf,
                    trend=indicators.get("trend", "sideways"),
                    rsi=indicators.get("rsi", 50),
                    macd_signal="bullish"
                    if indicators.get("macd", 0) > 0
                    else "bearish",
                    bb_signal=self._bb_signal(indicators),
                    volume_signal="high"
                    if indicators.get("volume_ratio", 1) > 1.5
                    else "normal",
                    score=score,
                    weight=weight,
                )
            )

        if not signals:
            return AggregatedSignal(
                weighted_score=0,
                agreement_pct=0,
                primary_trend="unknown",
                confluence_level="low",
                recommended_action="hold",
            )

        # Weighted score
        total_weight = sum(s.weight for s in signals)
        weighted_score = (
            sum(s.score * s.weight for s in signals) / total_weight
            if total_weight > 0
            else 0
        )

        # Agreement percentage
        bullish = sum(1 for s in signals if s.score > 0.2)
        bearish = sum(1 for s in signals if s.score < -0.2)
        agreement_pct = max(bullish, bearish) / len(signals) * 100

        # Primary trend from higher timeframes
        ht_signals = [s for s in signals if s.timeframe in ("4h", "1d")]
        if ht_signals:
            ht_avg = sum(s.score for s in ht_signals) / len(ht_signals)
            primary_trend = (
                "bullish"
                if ht_avg > 0.2
                else "bearish"
                if ht_avg < -0.2
                else "sideways"
            )
        else:
            primary_trend = "sideways"

        # Confluence
        if agreement_pct >= 75:
            confluence = "high"
        elif agreement_pct >= 55:
            confluence = "medium"
        else:
            confluence = "low"

        # Action
        if weighted_score >= 0.5 and confluence in ("high", "medium"):
            action = "strong_buy" if weighted_score >= 0.7 else "buy"
        elif weighted_score <= -0.5 and confluence in ("high", "medium"):
            action = "strong_sell" if weighted_score <= -0.7 else "sell"
        else:
            action = "hold"

        return AggregatedSignal(
            weighted_score=round(weighted_score, 4),
            agreement_pct=round(agreement_pct, 1),
            primary_trend=primary_trend,
            confluence_level=confluence,
            recommended_action=action,
            timeframe_signals=signals,
        )

    @staticmethod
    def _score_timeframe(indicators: dict) -> float:
        score = 0.0
        rsi = indicators.get("rsi", 50)
        trend = indicators.get("trend", "sideways")
        macd = indicators.get("macd", 0)
        bb_pos = indicators.get("bb_position", 0.5)
        vol = indicators.get("volume_ratio", 1.0)

        # RSI contribution
        if rsi < 30:
            score += 0.4
        elif rsi < 40:
            score += 0.2
        elif rsi > 70:
            score -= 0.4
        elif rsi > 60:
            score -= 0.2

        # Trend
        trend_map = {
            "strong_uptrend": 0.4,
            "uptrend": 0.2,
            "sideways": 0,
            "downtrend": -0.2,
            "strong_downtrend": -0.4,
        }
        score += trend_map.get(trend, 0)

        # MACD
        if macd > 0:
            score += 0.1
        elif macd < 0:
            score -= 0.1

        # Bollinger position (contrarian)
        score += (0.5 - bb_pos) * 0.2

        # Volume confirmation
        if vol > 1.5 and score > 0:
            score *= 1.15
        elif vol > 1.5 and score < 0:
            score *= 1.15

        return max(-1.0, min(1.0, score))

    @staticmethod
    def _bb_signal(indicators: dict) -> str:
        pos = indicators.get("bb_position", 0.5)
        if pos < 0.1:
            return "oversold"
        elif pos > 0.9:
            return "overbought"
        return "neutral"
