"""
DerivativesSignalEngine — aggregates all derivative market signals.

Weights:
  Funding rate    : 30%  (strong contrarian signal at extremes)
  Basis / premium : 20%  (secondary contrarian signal)
  Open Interest   : 30%  (confirms price direction conviction)
  Liquidation map : 10%  (cascade / squeeze risk)
  Options P/C     : 10%  (sentiment positioning)

Output: DerivativesSignal with composite score in -1..+1 and BUY/SELL/HOLD suggestion.
"""
from dataclasses import dataclass
from typing import Optional

from src.derivatives.funding_rate import FundingRateMonitor, FundingRateData
from src.derivatives.basis_tracker import BasisTracker, BasisData
from src.derivatives.open_interest import OpenInterestAnalyzer, OIData
from src.derivatives.liquidation_tracker import LiquidationTracker, LiquidationMap
from src.derivatives.options_analyzer import OptionsAnalyzer, OptionsChainSummary
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DerivativesSignal:
    """Composite signal from all derivative market data."""
    composite_score: float        # -1.0 (strong bearish) to +1.0 (strong bullish)
    action_suggestion: str        # "BUY" | "SELL" | "HOLD"
    confidence: float             # 0.0 – 1.0

    # Sub-signals
    funding: Optional[FundingRateData]
    basis: Optional[BasisData]
    oi: Optional[OIData]
    liquidation: Optional[LiquidationMap]
    options: Optional[OptionsChainSummary]

    # Individual scores
    funding_score: float
    basis_score: float
    oi_score: float
    liquidation_score: float
    options_score: float

    # Flags
    extreme_funding: bool         # funding at extreme levels
    short_squeeze_risk: bool
    long_squeeze_risk: bool
    high_oi_conviction: bool      # large OI + price confirmation

    summary: str

    def to_dict(self) -> dict:
        return {
            "composite_score": round(self.composite_score, 4),
            "action_suggestion": self.action_suggestion,
            "confidence": round(self.confidence, 3),
            "funding_score": round(self.funding_score, 4),
            "basis_score": round(self.basis_score, 4),
            "oi_score": round(self.oi_score, 4),
            "liquidation_score": round(self.liquidation_score, 4),
            "options_score": round(self.options_score, 4),
            "extreme_funding": self.extreme_funding,
            "short_squeeze_risk": self.short_squeeze_risk,
            "long_squeeze_risk": self.long_squeeze_risk,
            "high_oi_conviction": self.high_oi_conviction,
            "summary": self.summary,
            "funding": self.funding.to_dict() if self.funding else None,
            "basis": self.basis.to_dict() if self.basis else None,
            "oi": self.oi.to_dict() if self.oi else None,
            "liquidation": self.liquidation.to_dict() if self.liquidation else None,
            "options": self.options.to_dict() if self.options else None,
        }


class DerivativesSignalEngine:
    """
    Central engine for derivatives market intelligence.
    Instantiate once and call analyze() each trading cycle.
    """

    _W_FUNDING  = 0.30
    _W_BASIS    = 0.20
    _W_OI       = 0.30
    _W_LIQ      = 0.10
    _W_OPTIONS  = 0.10

    def __init__(self):
        self.funding_monitor  = FundingRateMonitor()
        self.basis_tracker    = BasisTracker()
        self.oi_analyzer      = OpenInterestAnalyzer()
        self.liq_tracker      = LiquidationTracker()
        self.options_analyzer = OptionsAnalyzer()

    def analyze(
        self,
        current_price: float,
        funding_rate: Optional[float] = None,
        spot_price: Optional[float] = None,
        open_interest: Optional[float] = None,
        options_chain: Optional[list] = None,
    ) -> DerivativesSignal:
        """
        Run all derivative sub-signals and combine into one composite score.

        Args:
            current_price  — perpetual mark price (or latest trade price)
            funding_rate   — 8-hour funding rate (decimal, e.g. 0.0001)
            spot_price     — spot/index price (for basis computation)
            open_interest  — total open interest in USD notional
            options_chain  — list of option dicts for chain analysis
        """
        # ── Funding ──────────────────────────────────────────────────────────
        f_data: Optional[FundingRateData] = None
        f_score = 0.0
        if funding_rate is not None:
            try:
                f_data  = self.funding_monitor.analyze(funding_rate)
                f_score = f_data.sentiment_score
            except Exception as e:
                logger.warning(f"Funding analysis error: {e}")

        # ── Basis ─────────────────────────────────────────────────────────────
        b_data: Optional[BasisData] = None
        b_score = 0.0
        perp_price = current_price
        spot = spot_price or current_price * 0.9997  # ~0.03% assumed basis if no spot
        try:
            b_data  = self.basis_tracker.analyze(spot, perp_price)
            b_score = b_data.sentiment_score
        except Exception as e:
            logger.warning(f"Basis analysis error: {e}")

        # ── Open Interest ─────────────────────────────────────────────────────
        oi_data: Optional[OIData] = None
        oi_score = 0.0
        if open_interest is not None:
            try:
                oi_data  = self.oi_analyzer.analyze(open_interest, current_price)
                oi_score = oi_data.sentiment_score
            except Exception as e:
                logger.warning(f"OI analysis error: {e}")

        # ── Liquidation ───────────────────────────────────────────────────────
        liq_data: Optional[LiquidationMap] = None
        liq_score = 0.0
        try:
            liq_data  = self.liq_tracker.compute_map(current_price)
            liq_score = liq_data.sentiment_score
        except Exception as e:
            logger.warning(f"Liquidation analysis error: {e}")

        # ── Options ───────────────────────────────────────────────────────────
        opt_data: Optional[OptionsChainSummary] = None
        opt_score = 0.0
        if options_chain:
            try:
                opt_data  = self.options_analyzer.analyze_chain(current_price, options_chain)
                opt_score = opt_data.pc_sentiment_score
            except Exception as e:
                logger.warning(f"Options analysis error: {e}")

        # ── Composite ─────────────────────────────────────────────────────────
        # Normalise weights for available signals
        weights = {
            "funding": self._W_FUNDING if f_data else 0.0,
            "basis":   self._W_BASIS,
            "oi":      self._W_OI if oi_data else 0.0,
            "liq":     self._W_LIQ,
            "options": self._W_OPTIONS if opt_data else 0.0,
        }
        total_w = sum(weights.values()) or 1.0
        composite = (
            f_score  * weights["funding"] +
            b_score  * weights["basis"] +
            oi_score * weights["oi"] +
            liq_score* weights["liq"] +
            opt_score* weights["options"]
        ) / total_w

        composite = round(max(-1.0, min(1.0, composite)), 4)

        # Confidence: how many signals agree with composite direction
        scores = [s for s, w in [(f_score, weights["funding"]), (b_score, weights["basis"]),
                                   (oi_score, weights["oi"]), (liq_score, weights["liq"]),
                                   (opt_score, weights["options"])] if w > 0]
        agree = sum(1 for s in scores if (s > 0) == (composite > 0)) if scores else 0
        confidence = round(agree / len(scores) if scores else 0.5, 3)

        # Action
        if composite >= 0.25 and confidence >= 0.5:
            action = "BUY"
        elif composite <= -0.25 and confidence >= 0.5:
            action = "SELL"
        else:
            action = "HOLD"

        # Flags
        extreme_funding   = f_data is not None and f_data.rate_label in ("extreme_positive", "extreme_negative")
        short_sq          = liq_data is not None and liq_data.signal == "short_squeeze_risk"
        long_sq           = liq_data is not None and liq_data.signal == "long_squeeze_risk"
        high_oi_conv      = (oi_data is not None and oi_data.large_oi_change and
                             oi_data.price_oi_signal in ("bullish_confirmation", "bearish_confirmation"))

        # Summary
        parts = [f"Derivatives score: {composite:+.3f} → {action}."]
        if extreme_funding:
            parts.append(f"⚠ Extreme funding ({f_data.rate_label}).")
        if short_sq:
            parts.append("⚠ Short squeeze risk detected.")
        if long_sq:
            parts.append("⚠ Long cascade risk detected.")
        if high_oi_conv:
            parts.append(f"High OI conviction: {oi_data.price_oi_signal}.")

        return DerivativesSignal(
            composite_score=composite,
            action_suggestion=action,
            confidence=confidence,
            funding=f_data, basis=b_data, oi=oi_data,
            liquidation=liq_data, options=opt_data,
            funding_score=round(f_score, 4),
            basis_score=round(b_score, 4),
            oi_score=round(oi_score, 4),
            liquidation_score=round(liq_score, 4),
            options_score=round(opt_score, 4),
            extreme_funding=extreme_funding,
            short_squeeze_risk=short_sq,
            long_squeeze_risk=long_sq,
            high_oi_conviction=high_oi_conv,
            summary=" ".join(parts),
        )
