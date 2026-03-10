"""
Trading Strategy Engine.
Combines emotion intelligence and geopolitical signals with technical analysis
to generate trading decisions for Delta Exchange.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import statistics

from src.intelligence.emotion_engine import EmotionScore
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TechnicalSignal:
    """Technical analysis signals derived from OHLCV data."""
    price: float
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    volume_ratio: float = 1.0       # Current volume / average volume
    trend: str = "neutral"           # "uptrend", "downtrend", "neutral"
    momentum: float = 0.0            # -1.0 to 1.0


@dataclass
class TradeSignal:
    """A complete trade signal with entry, exit, and sizing parameters."""
    action: str                        # "buy", "sell", "close_long", "close_short", "hold"
    symbol: str
    confidence: float                  # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_multiplier: float    # 0.0 to 1.0 - scales actual position size
    reasoning: str
    emotion_bias: str
    geo_risk_level: str
    signal_sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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
        return (
            self.action in ("buy", "sell", "close_long", "close_short")
            and self.confidence >= 0.5
            and self.risk_reward_ratio >= 1.5
        )


class TradingStrategy:
    """
    Combines geopolitical emotion intelligence with technical analysis
    to produce high-quality trade signals for Delta Exchange.

    Signal Generation Flow:
    1. Collect technical indicators from price data
    2. Receive emotion score from Claude AI analysis
    3. Receive geopolitical risk assessment
    4. Combine all signals using weighted scoring
    5. Apply filters (risk level, trend alignment, min confidence)
    6. Output a TradeSignal with full context
    """

    def __init__(self, config):
        self.config = config
        self.symbol = config.trading.symbol
        self.stop_loss_pct = config.trading.stop_loss_pct / 100
        self.take_profit_pct = config.trading.take_profit_pct / 100
        self.bullish_threshold = config.trading.bullish_threshold
        self.bearish_threshold = config.trading.bearish_threshold
        self._signal_history: List[TradeSignal] = []
        logger.info(f"TradingStrategy initialized for {self.symbol}")

    def generate_signal(
        self,
        emotion_score: EmotionScore,
        geo_impact: Dict,
        candles: List[Dict],
        current_price: float,
        has_open_position: bool = False,
        open_position_side: Optional[str] = None,
    ) -> TradeSignal:
        """
        Generate a trade signal by combining all available signals.

        Args:
            emotion_score: Claude emotion analysis result
            geo_impact: Geopolitical aggregate impact dict
            candles: OHLCV candle data (most recent last)
            current_price: Current market price
            has_open_position: Whether there's already an open position
            open_position_side: "long" or "short" if position exists

        Returns:
            TradeSignal with full context
        """
        # 1. Calculate technical signals
        tech = self._calculate_technical(candles, current_price)

        # 2. Calculate emotion signal score (-1 to 1)
        emotion_signal = self._score_emotion(emotion_score)

        # 3. Calculate geo signal score (-1 to 1)
        geo_signal = self._score_geo(geo_impact)

        # 4. Calculate technical signal score (-1 to 1)
        tech_signal = self._score_technical(tech)

        # 5. Weighted combination
        # Emotion (Claude AI): 45%, Geo: 25%, Technical: 30%
        combined_score = (
            emotion_signal * 0.45 +
            geo_signal * 0.25 +
            tech_signal * 0.30
        )

        # 6. Determine action
        action, confidence = self._decide_action(
            combined_score=combined_score,
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            tech=tech,
            has_open_position=has_open_position,
            open_position_side=open_position_side,
        )

        # 7. Calculate trade levels
        stop_loss, take_profit = self._calculate_levels(
            action=action,
            entry_price=current_price,
            tech=tech,
        )

        # 8. Position sizing based on confidence and risk
        size_multiplier = self._calculate_size_multiplier(
            confidence=confidence,
            geo_risk=geo_impact.get("risk_level", "low"),
            emotion_confidence=emotion_score.confidence,
        )

        # 9. Build reasoning
        reasoning = self._build_reasoning(
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            tech=tech,
            combined_score=combined_score,
            action=action,
        )

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
        )

        self._signal_history.append(signal)
        if len(self._signal_history) > 100:
            self._signal_history = self._signal_history[-100:]

        logger.info(
            f"Signal: {action.upper()} | score={combined_score:.3f} | "
            f"confidence={confidence:.2f} | R:R={signal.risk_reward_ratio:.2f} | "
            f"emotion={emotion_score.dominant_emotion}"
        )
        return signal

    def _calculate_technical(self, candles: List[Dict], price: float) -> TechnicalSignal:
        """Compute technical indicators from candle data."""
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
        bb_upper, bb_lower = None, None
        if len(closes) >= 20:
            mean20 = statistics.mean(closes[-20:])
            std20 = statistics.stdev(closes[-20:])
            bb_upper = mean20 + 2 * std20
            bb_lower = mean20 - 2 * std20

        # Volume ratio
        avg_volume = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else 1.0
        current_volume = volumes[-1] if volumes else 1.0
        vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Trend
        trend = "neutral"
        if sma_20 and sma_50:
            if price > sma_20 > sma_50:
                trend = "uptrend"
            elif price < sma_20 < sma_50:
                trend = "downtrend"

        # Momentum (rate of change)
        momentum = 0.0
        if len(closes) >= 10:
            roc = (closes[-1] - closes[-10]) / closes[-10]
            momentum = max(-1.0, min(1.0, roc * 10))

        return TechnicalSignal(
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

    @staticmethod
    def _calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = statistics.mean(gains[-period:])
        avg_loss = statistics.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _score_emotion(emotion_score: EmotionScore) -> float:
        """Convert emotion score to normalized -1 to 1 signal."""
        # Use crypto-specific sentiment weighted with general sentiment
        return (emotion_score.crypto_specific_sentiment * 0.6 +
                emotion_score.sentiment_score * 0.4) * emotion_score.confidence

    @staticmethod
    def _score_geo(geo_impact: Dict) -> float:
        """Convert geo impact to -1 to 1 signal."""
        total = geo_impact.get("total_impact", 0.0)
        risk_level = geo_impact.get("risk_level", "low")
        # High risk reduces signal strength (uncertainty)
        risk_dampener = {"low": 1.0, "medium": 0.8, "high": 0.5, "critical": 0.2}
        return total * risk_dampener.get(risk_level, 0.8)

    @staticmethod
    def _score_technical(tech: TechnicalSignal) -> float:
        """Convert technical indicators to -1 to 1 signal."""
        score = 0.0
        weight = 0.0

        if tech.rsi is not None:
            # RSI: oversold (<30) = bullish, overbought (>70) = bearish
            rsi_signal = (50 - tech.rsi) / 50  # +1 at RSI=0, -1 at RSI=100
            score += rsi_signal * 0.4
            weight += 0.4

        if tech.trend != "neutral":
            trend_signal = 0.5 if tech.trend == "uptrend" else -0.5
            score += trend_signal * 0.3
            weight += 0.3

        if tech.momentum != 0:
            score += tech.momentum * 0.3
            weight += 0.3

        if tech.bb_upper and tech.bb_lower:
            price = tech.price
            bb_range = tech.bb_upper - tech.bb_lower
            if bb_range > 0:
                bb_position = (price - tech.bb_lower) / bb_range  # 0=lower, 1=upper
                bb_signal = (0.5 - bb_position)  # Positive near lower band
                score += bb_signal * 0.2
                weight += 0.2

        return score / max(weight, 1.0) if weight > 0 else 0.0

    def _decide_action(
        self,
        combined_score: float,
        emotion_score: EmotionScore,
        geo_impact: Dict,
        tech: TechnicalSignal,
        has_open_position: bool,
        open_position_side: Optional[str],
    ) -> Tuple[str, float]:
        """Determine trade action and confidence from combined signal."""

        geo_risk = geo_impact.get("risk_level", "low")
        confidence = abs(combined_score) * emotion_score.confidence

        # Don't trade in critical geopolitical risk
        if geo_risk == "critical" and not has_open_position:
            return "hold", 0.1

        # Manage existing positions
        if has_open_position:
            if open_position_side == "long" and combined_score < self.bearish_threshold:
                return "close_long", min(confidence * 1.2, 1.0)
            if open_position_side == "short" and combined_score > self.bullish_threshold:
                return "close_short", min(confidence * 1.2, 1.0)
            return "hold", confidence

        # New position signals
        if combined_score >= self.bullish_threshold:
            # Confirm with trend alignment
            if tech.trend in ("uptrend", "neutral"):
                return "buy", min(confidence, 1.0)
            else:
                return "buy", confidence * 0.7  # Lower confidence against trend

        if combined_score <= self.bearish_threshold:
            if tech.trend in ("downtrend", "neutral"):
                return "sell", min(confidence, 1.0)
            else:
                return "sell", confidence * 0.7

        return "hold", confidence

    def _calculate_levels(
        self, action: str, entry_price: float, tech: TechnicalSignal
    ) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels."""
        if action == "buy":
            stop_loss = entry_price * (1 - self.stop_loss_pct)
            take_profit = entry_price * (1 + self.take_profit_pct)
            # Use Bollinger Band lower as SL if available and closer
            if tech.bb_lower and tech.bb_lower > stop_loss:
                stop_loss = tech.bb_lower * 0.999
        elif action == "sell":
            stop_loss = entry_price * (1 + self.stop_loss_pct)
            take_profit = entry_price * (1 - self.take_profit_pct)
            if tech.bb_upper and tech.bb_upper < stop_loss:
                stop_loss = tech.bb_upper * 1.001
        else:
            stop_loss = entry_price * (1 - self.stop_loss_pct)
            take_profit = entry_price * (1 + self.take_profit_pct)
        return round(stop_loss, 2), round(take_profit, 2)

    @staticmethod
    def _calculate_size_multiplier(
        confidence: float, geo_risk: str, emotion_confidence: float
    ) -> float:
        """Scale position size based on signal quality and risk."""
        base = confidence * emotion_confidence
        risk_factor = {"low": 1.0, "medium": 0.75, "high": 0.5, "critical": 0.25}
        return min(base * risk_factor.get(geo_risk, 0.75), 1.0)

    @staticmethod
    def _build_reasoning(
        emotion_score: EmotionScore,
        geo_impact: Dict,
        tech: TechnicalSignal,
        combined_score: float,
        action: str,
    ) -> str:
        parts = [
            f"Action: {action.upper()} | Combined score: {combined_score:.3f}",
            f"Emotion: {emotion_score.dominant_emotion} (sentiment={emotion_score.sentiment_score:.2f})",
            f"Geo risk: {geo_impact.get('risk_level', 'unknown')} | Events: {geo_impact.get('event_count', 0)}",
            f"Technical: trend={tech.trend}, RSI={tech.rsi:.1f if tech.rsi else 'N/A'}",
            f"Claude insight: {emotion_score.reasoning[:150]}",
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
        return sources

    @property
    def signal_history(self) -> List[TradeSignal]:
        return self._signal_history
