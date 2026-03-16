"""
Trading Strategy Engine.
Combines emotion intelligence, geopolitical signals, technical analysis,
and forward price forecasting to generate trading decisions for Delta Exchange.

Signal weights
--------------
  Emotion / Claude AI  : 35 %
  Geopolitical         : 20 %
  Technical            : 25 %
  Forecast (ADX/LR/VWAP): 20 %

Brokerage awareness
-------------------
  All R:R checks are done on net values after deducting the round-trip
  taker fee.  With 5× leverage and a 0.05 % taker fee the effective
  round-trip cost on margin ≈ 0.50 %.  stop_loss and take_profit levels
  are snapped to nearest pivot-point support / resistance where available.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import statistics

from src.intelligence.emotion_engine import EmotionScore
from src.intelligence.market_forecaster import MarketForecaster, ForecastResult
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class TechnicalSignal:
    """Technical analysis signals derived from OHLCV data."""

    price: float
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    volume_ratio: float = 1.0
    trend: str = "neutral"  # "uptrend" | "downtrend" | "neutral"
    momentum: float = 0.0  # −1.0 to +1.0

    # ── Forecast fields (populated by MarketForecaster) ──────────────────────
    adx: float = 0.0
    market_regime: str = "ranging"  # "trending" | "ranging" | "volatile"
    trend_direction: str = "neutral"  # "bullish" | "bearish" | "neutral"
    trend_strength_label: str = (
        "none"  # "very_strong" | "strong" | "moderate" | "weak" | "none"
    )
    forecast_bias: str = "neutral"
    forecast_price_3: Optional[float] = None
    vwap: Optional[float] = None
    vwap_position: str = "at"
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    breakeven_move_pct: float = 0.0  # % of margin needed to cover round-trip fees
    forecast_score: float = 0.0  # −1 → +1 composite forecast score
    regression_r2: float = 0.0


@dataclass
class TradeSignal:
    """A complete trade signal with entry, exit, and sizing parameters."""

    action: str  # "buy"|"sell"|"close_long"|"close_short"|"hold"
    symbol: str
    confidence: float  # 0.0–1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_multiplier: float  # 0.0–1.0
    reasoning: str
    emotion_bias: str
    geo_risk_level: str
    signal_sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Fee info for transparency
    breakeven_move_pct: float = 0.0
    net_rr_after_fees: float = 0.0

    @property
    def risk_reward_ratio(self) -> float:
        """Gross R:R (before fees)."""
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
        """Signal is valid when net R:R (after fees) meets minimum threshold."""
        return (
            self.action in ("buy", "sell", "close_long", "close_short")
            and self.confidence >= 0.5
            and self.net_rr_after_fees >= 1.5
        )


# ── Strategy engine ───────────────────────────────────────────────────────────


class TradingStrategy:
    """
    Signal generation pipeline:

    1. Calculate classic technical indicators (SMA, RSI, Bollinger Bands)
    2. Run MarketForecaster  (ADX, linear regression, VWAP, pivot points)
    3. Score emotion signal from Claude AI
    4. Score geopolitical impact
    5. Score technical + forecast signals
    6. Weighted combination → raw score
    7. Regime-aware action thresholds (trending / ranging)
    8. Snap SL/TP to pivot-point support / resistance
    9. Apply fee-adjusted R:R validation
    """

    # Weighting for combined score
    _W_EMOTION = 0.30
    _W_GEO = 0.15
    _W_TECH = 0.25
    _W_FORECAST = 0.15
    _W_DERIVATIVES = 0.15

    def __init__(self, config):
        self.config = config
        self.symbol = config.trading.symbol
        self.stop_loss_pct = config.trading.stop_loss_pct / 100
        self.take_profit_pct = config.trading.take_profit_pct / 100
        self.bullish_threshold = config.trading.bullish_threshold
        self.bearish_threshold = config.trading.bearish_threshold

        # Brokerage
        tc = config.trading
        self.taker_fee = getattr(tc, "taker_fee_rate", 0.0005)
        self.leverage = getattr(tc, "leverage", 5)

        self.forecaster = MarketForecaster(config)
        self._signal_history: List[TradeSignal] = []
        logger.info("TradingStrategy initialised for %s", self.symbol)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_signal(
        self,
        emotion_score: EmotionScore,
        geo_impact: Dict,
        candles: List[Dict],
        current_price: float,
        has_open_position: bool = False,
        open_position_side: Optional[str] = None,
        derivatives_score: float = 0.0,
    ) -> TradeSignal:
        """Generate a trade signal by combining all available signals."""

        # 1. Technical indicators + forecast
        tech = self._calculate_technical(candles, current_price)

        # 2. Individual signal scores (−1 → +1 each)
        emotion_signal = self._score_emotion(emotion_score)
        geo_signal = self._score_geo(geo_impact)
        tech_signal = self._score_technical(tech)
        forecast_signal = tech.forecast_score  # already −1 → +1
        deriv_signal = max(-1.0, min(1.0, derivatives_score))

        # 3. Weighted combination
        combined_score = (
            emotion_signal * self._W_EMOTION
            + geo_signal * self._W_GEO
            + tech_signal * self._W_TECH
            + forecast_signal * self._W_FORECAST
            + deriv_signal * self._W_DERIVATIVES
        )

        # 4. Regime-aware threshold adjustment
        effective_bullish, effective_bearish = self._regime_thresholds(tech)

        # 5. Action decision
        action, confidence = self._decide_action(
            combined_score=combined_score,
            effective_bullish=effective_bullish,
            effective_bearish=effective_bearish,
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            tech=tech,
            has_open_position=has_open_position,
            open_position_side=open_position_side,
        )

        # 6. SL / TP levels (pivot-point-aware)
        stop_loss, take_profit = self._calculate_levels(action, current_price, tech)

        # 7. Fee-adjusted net R:R
        net_rr = self._net_rr_after_fees(action, current_price, stop_loss, take_profit)

        # 8. Position sizing
        size_multiplier = self._calculate_size_multiplier(
            confidence=confidence,
            geo_risk=geo_impact.get("risk_level", "low"),
            emotion_confidence=emotion_score.confidence,
            adx=tech.adx,
        )

        # 9. Build reasoning
        reasoning = self._build_reasoning(
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            tech=tech,
            combined_score=combined_score,
            action=action,
        )

        breakeven_pct = tech.breakeven_move_pct

        signal = TradeSignal(
            action=action,
            symbol=self.symbol,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_multiplier=size_multiplier,
            reasoning=reasoning,
            emotion_bias=emotion_score.trading_bias,
            geo_risk_level=geo_impact.get("risk_level", "low"),
            signal_sources=self._get_signal_sources(emotion_score, geo_impact, tech),
            breakeven_move_pct=breakeven_pct,
            net_rr_after_fees=net_rr,
        )

        self._signal_history.append(signal)
        if len(self._signal_history) > 100:
            self._signal_history = self._signal_history[-100:]

        logger.info(
            "Signal: %s | score=%.3f | conf=%.2f | gross_RR=%.2f | net_RR=%.2f "
            "| ADX=%.1f (%s) | regime=%s | forecast=%s",
            action.upper(),
            combined_score,
            confidence,
            signal.risk_reward_ratio,
            net_rr,
            tech.adx,
            tech.trend_strength_label,
            tech.market_regime,
            tech.forecast_bias,
        )
        return signal

    # ── Technical calculations ────────────────────────────────────────────────

    def _calculate_technical(
        self, candles: List[Dict], price: float
    ) -> TechnicalSignal:
        """Compute SMA/RSI/BB/momentum, then run the MarketForecaster."""
        if not candles or len(candles) < 5:
            return TechnicalSignal(price=price)

        closes = [float(c.get("close", c.get("c", price))) for c in candles]
        volumes = [float(c.get("volume", c.get("v", 0))) for c in candles]

        # SMA
        sma_20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else None
        sma_50 = statistics.mean(closes[-50:]) if len(closes) >= 50 else None

        # RSI
        rsi = self._calculate_rsi(closes)

        # Bollinger Bands
        bb_upper = bb_lower = None
        if len(closes) >= 20:
            m20 = statistics.mean(closes[-20:])
            s20 = statistics.stdev(closes[-20:])
            bb_upper = m20 + 2 * s20
            bb_lower = m20 - 2 * s20

        # Volume ratio
        avg_vol = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else 1.0
        cur_vol = volumes[-1] if volumes else 1.0
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

        # Simple trend (SMA alignment)
        trend = "neutral"
        if sma_20 and sma_50:
            if price > sma_20 > sma_50:
                trend = "uptrend"
            elif price < sma_20 < sma_50:
                trend = "downtrend"

        # Momentum (10-period ROC)
        momentum = 0.0
        if len(closes) >= 10:
            roc = (closes[-1] - closes[-10]) / closes[-10]
            momentum = max(-1.0, min(1.0, roc * 10))

        tech = TechnicalSignal(
            price=price,
            sma_20=sma_20,
            sma_50=sma_50,
            rsi=rsi,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            volume_ratio=vol_ratio,
            trend=trend,
            momentum=momentum,
        )

        # Run forecaster and merge result into TechnicalSignal
        fc: ForecastResult = self.forecaster.forecast(candles, price)
        tech.adx = fc.adx
        tech.market_regime = fc.market_regime
        tech.trend_direction = fc.trend_direction
        tech.trend_strength_label = fc.trend_strength_label
        tech.forecast_bias = fc.forecast_bias
        tech.forecast_price_3 = fc.forecast_price_3
        tech.vwap = fc.vwap
        tech.vwap_position = fc.vwap_position
        tech.support_levels = fc.support_levels
        tech.resistance_levels = fc.resistance_levels
        tech.breakeven_move_pct = fc.breakeven_move_pct
        tech.forecast_score = fc.forecast_score
        tech.regression_r2 = fc.regression_r2

        return tech

    @staticmethod
    def _calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
        avg_gain = statistics.mean(gains[-period:])
        avg_loss = statistics.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    # ── Signal scorers ────────────────────────────────────────────────────────

    @staticmethod
    def _score_emotion(emotion_score: EmotionScore) -> float:
        return (
            emotion_score.crypto_specific_sentiment * 0.6
            + emotion_score.sentiment_score * 0.4
        ) * emotion_score.confidence

    @staticmethod
    def _score_geo(geo_impact: Dict) -> float:
        total = geo_impact.get("total_impact", 0.0)
        risk_level = geo_impact.get("risk_level", "low")
        dampener = {"low": 1.0, "medium": 0.8, "high": 0.5, "critical": 0.2}
        return total * dampener.get(risk_level, 0.8)

    @staticmethod
    def _score_technical(tech: TechnicalSignal) -> float:
        score, weight = 0.0, 0.0

        if tech.rsi is not None:
            rsi_signal = (50 - tech.rsi) / 50
            score += rsi_signal * 0.35
            weight += 0.35

        if tech.trend != "neutral":
            score += (0.5 if tech.trend == "uptrend" else -0.5) * 0.30
            weight += 0.30

        if tech.momentum != 0:
            score += tech.momentum * 0.20
            weight += 0.20

        if tech.bb_upper and tech.bb_lower:
            bb_range = tech.bb_upper - tech.bb_lower
            if bb_range > 0:
                bb_pos = (tech.price - tech.bb_lower) / bb_range
                score += (0.5 - bb_pos) * 0.15
                weight += 0.15

        return score / max(weight, 1.0) if weight > 0 else 0.0

    # ── Regime thresholds ─────────────────────────────────────────────────────

    def _regime_thresholds(self, tech: TechnicalSignal) -> Tuple[float, float]:
        """
        Adjust entry thresholds based on market regime and trend strength.

        Trending (ADX ≥ 25): loosen thresholds — ride the trend.
        Ranging              : tighten thresholds — be more selective.
        Volatile             : tightest thresholds — only very clear signals.
        """
        if tech.market_regime == "trending" and tech.adx >= 35:
            mult = 0.80  # easier to enter — strong trend is your friend
        elif tech.market_regime == "trending":
            mult = 0.90
        elif tech.market_regime == "volatile":
            mult = 1.30  # very conservative in volatile markets
        else:  # ranging
            mult = 1.15

        return self.bullish_threshold * mult, self.bearish_threshold * mult

    # ── Action decision ───────────────────────────────────────────────────────

    def _decide_action(
        self,
        combined_score: float,
        effective_bullish: float,
        effective_bearish: float,
        emotion_score: EmotionScore,
        geo_impact: Dict,
        tech: TechnicalSignal,
        has_open_position: bool,
        open_position_side: Optional[str],
    ) -> Tuple[str, float]:
        geo_risk = geo_impact.get("risk_level", "low")
        confidence = abs(combined_score) * emotion_score.confidence

        # Hard stop in critical geo-risk (no new positions)
        if geo_risk == "critical" and not has_open_position:
            return "hold", 0.1

        # Manage existing positions
        if has_open_position:
            if open_position_side == "long" and combined_score < effective_bearish:
                return "close_long", min(confidence * 1.2, 1.0)
            if open_position_side == "short" and combined_score > effective_bullish:
                return "close_short", min(confidence * 1.2, 1.0)
            return "hold", confidence

        # New position — only enter when forecast + trend agree
        if combined_score >= effective_bullish:
            # Require forecast and trend direction to align (or be neutral)
            if tech.forecast_bias in (
                "bullish",
                "neutral",
            ) and tech.trend_direction in ("bullish", "neutral"):
                return "buy", min(confidence, 1.0)
            elif tech.adx >= 35 and tech.trend_direction == "bullish":
                # Strong trend override — trust momentum
                return "buy", min(confidence * 0.90, 1.0)
            else:
                return "buy", confidence * 0.65  # weaker confirmation

        if combined_score <= effective_bearish:
            if tech.forecast_bias in (
                "bearish",
                "neutral",
            ) and tech.trend_direction in ("bearish", "neutral"):
                return "sell", min(confidence, 1.0)
            elif tech.adx >= 35 and tech.trend_direction == "bearish":
                return "sell", min(confidence * 0.90, 1.0)
            else:
                return "sell", confidence * 0.65

        return "hold", confidence

    # ── Level calculation ─────────────────────────────────────────────────────

    def _calculate_levels(
        self, action: str, entry_price: float, tech: TechnicalSignal
    ) -> Tuple[float, float]:
        """
        Compute SL and TP. Where pivot points exist, snap to nearest
        support (SL) or resistance (TP) for more realistic market-structure levels.
        """
        if action == "buy":
            sl = entry_price * (1 - self.stop_loss_pct)
            tp = entry_price * (1 + self.take_profit_pct)

            # Tighten SL to nearest support above config SL
            if tech.support_levels:
                supports_below = [
                    s for s in tech.support_levels if s < entry_price and s > sl
                ]
                if supports_below:
                    sl = max(supports_below) * 0.9995  # just below support

            # Bollinger lower as SL if closer
            if tech.bb_lower and tech.bb_lower > sl:
                sl = tech.bb_lower * 0.9995

            # Target nearest resistance as TP (only if between entry and config TP)
            if tech.resistance_levels:
                resistances_above = [
                    r for r in tech.resistance_levels if entry_price < r <= tp
                ]
                if resistances_above:
                    tp = min(resistances_above) * 0.9998  # just below resistance

        elif action == "sell":
            sl = entry_price * (1 + self.stop_loss_pct)
            tp = entry_price * (1 - self.take_profit_pct)

            if tech.resistance_levels:
                resistances_above = [
                    r for r in tech.resistance_levels if r > entry_price and r < sl
                ]
                if resistances_above:
                    sl = min(resistances_above) * 1.0005

            if tech.bb_upper and tech.bb_upper < sl:
                sl = tech.bb_upper * 1.0005

            if tech.support_levels:
                supports_below = [
                    s for s in tech.support_levels if entry_price > s >= tp
                ]
                if supports_below:
                    tp = max(supports_below) * 1.0002

        else:
            sl = entry_price * (1 - self.stop_loss_pct)
            tp = entry_price * (1 + self.take_profit_pct)

        return round(sl, 2), round(tp, 2)

    # ── Fee helpers ───────────────────────────────────────────────────────────

    def _net_rr_after_fees(
        self, action: str, entry: float, sl: float, tp: float
    ) -> float:
        """
        Net risk-reward ratio after deducting round-trip brokerage.

        Round-trip fee on notional = taker_fee * 2.
        Expressed as a % of entry price this is subtracted from both
        the profit (reduces reward) and loss (increases risk).
        Fee % of price = taker_fee * 2   (same notional basis)
        """
        fee_pct = self.taker_fee * 2  # total round-trip fee as fraction of price

        if action == "buy":
            gross_risk = abs(entry - sl)
            gross_reward = abs(tp - entry)
        elif action == "sell":
            gross_risk = abs(sl - entry)
            gross_reward = abs(entry - tp)
        else:
            return 0.0

        fee_dollars = entry * fee_pct
        net_reward = gross_reward - fee_dollars
        net_risk = gross_risk + fee_dollars

        return round(net_reward / net_risk, 4) if net_risk > 0 else 0.0

    # ── Sizing ────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_size_multiplier(
        confidence: float, geo_risk: str, emotion_confidence: float, adx: float
    ) -> float:
        base = confidence * emotion_confidence
        risk_factor = {"low": 1.0, "medium": 0.75, "high": 0.5, "critical": 0.25}
        rf = risk_factor.get(geo_risk, 0.75)

        # Boost size in strong trends (more conviction)
        adx_boost = 1.0
        if adx >= 40:
            adx_boost = 1.15
        elif adx >= 25:
            adx_boost = 1.05

        return min(base * rf * adx_boost, 1.0)

    # ── Reasoning & sources ───────────────────────────────────────────────────

    @staticmethod
    def _build_reasoning(
        emotion_score: EmotionScore,
        geo_impact: Dict,
        tech: TechnicalSignal,
        combined_score: float,
        action: str,
    ) -> str:
        parts = [
            f"Action: {action.upper()} | Score: {combined_score:.3f}",
            f"Emotion: {emotion_score.dominant_emotion} (sentiment={emotion_score.sentiment_score:.2f}, conf={emotion_score.confidence:.2f})",
            f"Geo risk: {geo_impact.get('risk_level', '?')} | Events: {geo_impact.get('event_count', 0)}",
            f"Technical: trend={tech.trend}, RSI={f'{tech.rsi:.1f}' if tech.rsi else 'N/A'}, BB_pos={f'{(tech.price - tech.bb_lower) / (tech.bb_upper - tech.bb_lower):.2f}' if tech.bb_upper and tech.bb_lower and tech.bb_upper != tech.bb_lower else 'N/A'}",
            f"Forecast: ADX={tech.adx:.1f} ({tech.trend_strength_label}) | regime={tech.market_regime} | bias={tech.forecast_bias} | VWAP={tech.vwap_position} | score={tech.forecast_score:.3f}",
            f"Break-even (fees): {tech.breakeven_move_pct:.2f}% of margin",
            f"Claude insight: {emotion_score.reasoning[:120]}",
        ]
        return " | ".join(parts)

    @staticmethod
    def _get_signal_sources(
        emotion_score: EmotionScore, geo_impact: Dict, tech: TechnicalSignal
    ) -> List[str]:
        sources = []
        if emotion_score.confidence >= 0.5:
            sources.append(f"Claude AI ({emotion_score.dominant_emotion})")
        if geo_impact.get("event_count", 0) > 0:
            sources.append(f"Geopolitical ({geo_impact.get('event_count')} events)")
        if tech.trend != "neutral":
            sources.append(f"Technical ({tech.trend})")
        if tech.rsi:
            if tech.rsi < 35:
                sources.append("RSI oversold")
            elif tech.rsi > 65:
                sources.append("RSI overbought")
        if tech.trend_strength_label in ("strong", "very_strong"):
            sources.append(f"ADX {tech.adx:.0f} ({tech.trend_direction})")
        if tech.forecast_bias != "neutral" and tech.regression_r2 > 0.3:
            sources.append(
                f"LR forecast {tech.forecast_bias} (R²={tech.regression_r2:.2f})"
            )
        if tech.vwap_position in ("above", "below"):
            sources.append(f"VWAP {tech.vwap_position}")
        return sources

    # ── Public accessors ──────────────────────────────────────────────────────

    @property
    def signal_history(self) -> List[TradeSignal]:
        return self._signal_history
