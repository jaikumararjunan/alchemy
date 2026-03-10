"""
Liquidation Level Tracker.

Estimates where clusters of leveraged positions would be liquidated,
creating potential price magnets or cascade zones.

For a long position at entry price P with leverage L:
  liquidation ≈ P × (1 - 1/L + maintenance_margin/L)
  simplified: liq_long ≈ P × (1 - (1/L) × 0.9)

For a short:
  liq_short ≈ P × (1 + (1/L) × 0.9)

Delta Exchange maintenance margin ≈ 0.5% (0.005).
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LiquidationLevel:
    """A single estimated liquidation cluster."""
    price: float
    direction: str        # "long_liq" | "short_liq"
    leverage: int
    estimated_entry: float
    distance_pct: float   # % from current price
    severity: str         # "close" | "moderate" | "far"
    description: str

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 2),
            "direction": self.direction,
            "leverage": self.leverage,
            "estimated_entry": round(self.estimated_entry, 2),
            "distance_pct": round(self.distance_pct, 3),
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class LiquidationMap:
    """Map of estimated liquidation levels around current price."""
    current_price: float
    long_liquidation_levels: List[LiquidationLevel]    # below current price
    short_liquidation_levels: List[LiquidationLevel]   # above current price
    nearest_long_liq: Optional[LiquidationLevel]
    nearest_short_liq: Optional[LiquidationLevel]
    cascade_risk_below_pct: float   # % from current where cascade could start
    cascade_risk_above_pct: float
    signal: str                     # "short_squeeze_risk" | "long_squeeze_risk" | "neutral"
    sentiment_score: float
    interpretation: str

    def to_dict(self) -> dict:
        return {
            "current_price": round(self.current_price, 2),
            "long_liquidation_levels": [l.to_dict() for l in self.long_liquidation_levels],
            "short_liquidation_levels": [l.to_dict() for l in self.short_liquidation_levels],
            "nearest_long_liq": self.nearest_long_liq.to_dict() if self.nearest_long_liq else None,
            "nearest_short_liq": self.nearest_short_liq.to_dict() if self.nearest_short_liq else None,
            "cascade_risk_below_pct": round(self.cascade_risk_below_pct, 3),
            "cascade_risk_above_pct": round(self.cascade_risk_above_pct, 3),
            "signal": self.signal,
            "sentiment_score": round(self.sentiment_score, 4),
            "interpretation": self.interpretation,
        }


class LiquidationTracker:
    """
    Estimates liquidation levels for common leverage multiples.
    Maps zones where cascading liquidations could occur.
    """

    LEVERAGE_LEVELS   = [3, 5, 10, 20, 50]
    MAINTENANCE_MARGIN = 0.005   # Delta Exchange 0.5%

    def compute_map(self, current_price: float) -> LiquidationMap:
        """
        Generate estimated liquidation levels for typical leveraged entries.
        Assumes entries at progressively higher/lower prices from current.
        """
        long_liqs: List[LiquidationLevel] = []
        short_liqs: List[LiquidationLevel] = []

        for lev in self.LEVERAGE_LEVELS:
            # Longs entered at various distances below current price
            # (recent longs who bought the dip would have entered ~1-3% below)
            for entry_dist_pct in [0.5, 1.5, 3.0]:
                entry_long = current_price * (1 - entry_dist_pct / 100)
                liq_long = entry_long * (1 - (1 / lev) * (1 - self.MAINTENANCE_MARGIN * lev))
                liq_long = max(0, liq_long)
                dist = ((current_price - liq_long) / current_price) * 100

                sev = "close" if dist < 3 else ("moderate" if dist < 8 else "far")
                long_liqs.append(LiquidationLevel(
                    price=round(liq_long, 2),
                    direction="long_liq",
                    leverage=lev,
                    estimated_entry=round(entry_long, 2),
                    distance_pct=round(dist, 3),
                    severity=sev,
                    description=f"{lev}× long entry ~{entry_dist_pct:.1f}% below current",
                ))

            # Shorts entered above current
            for entry_dist_pct in [0.5, 1.5, 3.0]:
                entry_short = current_price * (1 + entry_dist_pct / 100)
                liq_short = entry_short * (1 + (1 / lev) * (1 - self.MAINTENANCE_MARGIN * lev))
                dist = ((liq_short - current_price) / current_price) * 100

                sev = "close" if dist < 3 else ("moderate" if dist < 8 else "far")
                short_liqs.append(LiquidationLevel(
                    price=round(liq_short, 2),
                    direction="short_liq",
                    leverage=lev,
                    estimated_entry=round(entry_short, 2),
                    distance_pct=round(dist, 3),
                    severity=sev,
                    description=f"{lev}× short entry ~{entry_dist_pct:.1f}% above current",
                ))

        long_liqs.sort(key=lambda l: -l.price)   # closest liq first (highest price)
        short_liqs.sort(key=lambda l: l.price)    # closest liq first (lowest price)

        nearest_long  = next((l for l in long_liqs if l.severity in ("close", "moderate")), None)
        nearest_short = next((l for l in short_liqs if l.severity in ("close", "moderate")), None)

        # Cascade risk = nearest severe cluster distance
        cascade_below = nearest_long.distance_pct if nearest_long else 15.0
        cascade_above = nearest_short.distance_pct if nearest_short else 15.0

        # Signal: if shorts cluster closer than longs → short squeeze more likely
        if cascade_above < cascade_below and cascade_above < 5:
            signal = "short_squeeze_risk"
            sentiment_score = 0.5
        elif cascade_below < cascade_above and cascade_below < 5:
            signal = "long_squeeze_risk"
            sentiment_score = -0.5
        else:
            signal = "neutral"
            sentiment_score = 0.0

        interp_parts = []
        if nearest_long:
            interp_parts.append(f"Nearest long liq at ${nearest_long.price:,.0f} "
                                 f"({nearest_long.distance_pct:.1f}% below).")
        if nearest_short:
            interp_parts.append(f"Nearest short liq at ${nearest_short.price:,.0f} "
                                 f"({nearest_short.distance_pct:.1f}% above).")
        if signal == "short_squeeze_risk":
            interp_parts.append("Short positions densely stacked above — short squeeze risk.")
        elif signal == "long_squeeze_risk":
            interp_parts.append("Long positions densely stacked below — liquidation cascade risk.")

        return LiquidationMap(
            current_price=current_price,
            long_liquidation_levels=long_liqs[:10],
            short_liquidation_levels=short_liqs[:10],
            nearest_long_liq=nearest_long,
            nearest_short_liq=nearest_short,
            cascade_risk_below_pct=round(cascade_below, 3),
            cascade_risk_above_pct=round(cascade_above, 3),
            signal=signal,
            sentiment_score=round(sentiment_score, 4),
            interpretation=" ".join(interp_parts) or "No immediate liquidation cascade risk identified.",
        )
