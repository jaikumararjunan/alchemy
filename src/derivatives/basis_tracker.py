"""
Basis Tracker — spot vs perpetual / futures price premium.

For Delta Exchange perps:
  basis = (perp_price - spot_price) / spot_price
  Positive basis (perp > spot) = contango  → market pays to be long → slight bearish lean
  Negative basis (perp < spot) = backwardation → market pays to be short → slight bullish lean

For calendar futures:
  annualized_basis = (futures - spot) / spot / days_to_expiry * 365
"""

from dataclasses import dataclass
from typing import Optional
from collections import deque


@dataclass
class BasisData:
    """Spot-perp and spot-futures basis metrics."""

    spot_price: float
    perp_price: float
    basis_usd: float  # perp - spot
    basis_pct: float  # (perp - spot) / spot × 100
    basis_label: str  # "strong_contango" | "contango" | "fair_value" | "backwardation" | "strong_backwardation"
    signal: str  # "bearish" | "slightly_bearish" | "neutral" | "slightly_bullish" | "bullish"
    sentiment_score: float  # -1.0 to +1.0

    futures_price: Optional[float]
    futures_days: Optional[int]
    annualized_basis_pct: Optional[float]

    # Rolling stats
    avg_basis_pct_1h: float
    basis_trend: str  # "widening" | "narrowing" | "stable"
    interpretation: str

    def to_dict(self) -> dict:
        return {
            "spot_price": round(self.spot_price, 2),
            "perp_price": round(self.perp_price, 2),
            "basis_usd": round(self.basis_usd, 2),
            "basis_pct": round(self.basis_pct, 4),
            "basis_label": self.basis_label,
            "signal": self.signal,
            "sentiment_score": round(self.sentiment_score, 4),
            "futures_price": round(self.futures_price, 2)
            if self.futures_price
            else None,
            "futures_days": self.futures_days,
            "annualized_basis_pct": round(self.annualized_basis_pct, 2)
            if self.annualized_basis_pct
            else None,
            "avg_basis_pct_1h": round(self.avg_basis_pct_1h, 4),
            "basis_trend": self.basis_trend,
            "interpretation": self.interpretation,
        }


class BasisTracker:
    """
    Tracks the basis between spot, perpetual, and fixed-expiry futures.
    Generates trading signals from basis extremes and trends.
    """

    # Thresholds (as % of spot)
    _STRONG_CONTANGO = 0.30  # > +0.30%
    _CONTANGO = 0.10  # > +0.10%
    _FAIR_VALUE_BAND = 0.05  # ±0.05%
    _BACKWARDATION = -0.10  # < -0.10%
    _STRONG_BACK = -0.30  # < -0.30%

    def __init__(self, history_size: int = 60):  # 60 × 1-min readings = 1 hour
        self._history: deque = deque(maxlen=history_size)

    def analyze(
        self,
        spot_price: float,
        perp_price: float,
        futures_price: Optional[float] = None,
        futures_days_to_expiry: Optional[int] = None,
    ) -> BasisData:
        if spot_price <= 0:
            spot_price = perp_price  # fallback

        basis_usd = perp_price - spot_price
        basis_pct = (basis_usd / spot_price) * 100 if spot_price > 0 else 0.0

        self._history.append(basis_pct)
        history_list = list(self._history)
        avg_1h = sum(history_list) / len(history_list) if history_list else basis_pct

        # Trend
        if len(history_list) >= 4:
            recent = sum(history_list[-2:]) / 2
            older = sum(history_list[-4:-2]) / 2
            if recent > older + 0.02:
                trend = "widening"
            elif recent < older - 0.02:
                trend = "narrowing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Label
        if basis_pct >= self._STRONG_CONTANGO:
            label = "strong_contango"
        elif basis_pct >= self._CONTANGO:
            label = "contango"
        elif basis_pct <= self._STRONG_BACK:
            label = "strong_backwardation"
        elif basis_pct <= self._BACKWARDATION:
            label = "backwardation"
        else:
            label = "fair_value"

        # Sentiment (contrarian on extremes)
        norm = self._STRONG_CONTANGO
        sentiment_score = max(-1.0, min(1.0, -basis_pct / norm))

        # Signal
        if sentiment_score >= 0.6:
            signal = "bullish"
        elif sentiment_score >= 0.25:
            signal = "slightly_bullish"
        elif sentiment_score <= -0.6:
            signal = "bearish"
        elif sentiment_score <= -0.25:
            signal = "slightly_bearish"
        else:
            signal = "neutral"

        # Annualized basis for calendar futures
        annualized = None
        if futures_price and futures_days_to_expiry and futures_days_to_expiry > 0:
            f_basis = (futures_price - spot_price) / spot_price
            annualized = f_basis / futures_days_to_expiry * 365 * 100

        # Interpretation
        if label == "strong_contango":
            interp = (
                f"Strong contango (+{basis_pct:.3f}%). Perp premium extreme. "
                "Market over-extended long — bearish mean-reversion signal."
            )
        elif label == "contango":
            interp = f"Contango (+{basis_pct:.3f}%). Longs at a small premium. Slight bearish lean."
        elif label == "strong_backwardation":
            interp = (
                f"Strong backwardation ({basis_pct:.3f}%). Perp at deep discount. "
                "Market over-extended short — bullish mean-reversion signal."
            )
        elif label == "backwardation":
            interp = f"Backwardation ({basis_pct:.3f}%). Shorts paying to hold. Slight bullish lean."
        else:
            interp = (
                f"Basis near fair value ({basis_pct:.3f}%). No strong basis signal."
            )

        return BasisData(
            spot_price=spot_price,
            perp_price=perp_price,
            basis_usd=basis_usd,
            basis_pct=basis_pct,
            basis_label=label,
            signal=signal,
            sentiment_score=round(sentiment_score, 4),
            futures_price=futures_price,
            futures_days=futures_days_to_expiry,
            annualized_basis_pct=annualized,
            avg_basis_pct_1h=round(avg_1h, 4),
            basis_trend=trend,
            interpretation=interp,
        )
