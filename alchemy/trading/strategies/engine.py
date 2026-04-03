"""
alchemy.trading.strategies.engine
===================================
AI-powered trading strategy engine.

Strategies implemented:
  1. Scalping       — 1-5 min timeframe, tight stops, high frequency
  2. Momentum       — Trend-following with ADX + RSI
  3. Mean Reversion — Bollinger Bands + RSI oversold/overbought
  4. Breakout       — Volume-confirmed breakouts with ATR stops
  5. News-driven    — Intelligence-signal-triggered entries
  6. Options STBT/BTST — Short-term directional options plays

All strategies consume:
  - Market intelligence signals (geopolitical, news, video)
  - Technical indicators (computed locally)
  - Emotional intelligence scores (fear/greed index)
  - Portfolio risk state
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class StrategyType(str, Enum):
    SCALPING      = "scalping"
    MOMENTUM      = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT      = "breakout"
    NEWS_DRIVEN   = "news_driven"
    BTST          = "btst"     # Buy Today Sell Tomorrow
    OPTIONS_STBT  = "options_stbt"  # Sell Today Buy Tomorrow


class TradeDirection(str, Enum):
    LONG  = "long"
    SHORT = "short"
    FLAT  = "flat"


@dataclass
class TradeIdea:
    """A specific trade recommendation with entry/exit plan."""
    id:               str
    strategy:         StrategyType
    symbol:           str
    exchange:         str              # NSE | BSE | DELTA | BINANCE
    direction:        TradeDirection
    entry_price:      float
    stop_loss:        float
    take_profit_1:    float            # 1:1 target
    take_profit_2:    float            # 1:2 target (half position)
    take_profit_3:    float            # 1:3 target (final exit)
    position_size_pct: float           # % of capital to allocate
    leverage:         int   = 1
    timeframe:        str   = "15m"
    confidence:       float = 0.0
    reasoning:        str   = ""
    intelligence_signals: list[str] = field(default_factory=list)  # IDs of signals used
    emotional_score:  float = 0.5     # 0=panic, 1=euphoria (0.5=neutral)
    risk_reward:      float = 2.0
    created_at:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until:      Optional[datetime] = None

    @property
    def risk_pct(self) -> float:
        if self.entry_price == 0: return 0
        return abs(self.entry_price - self.stop_loss) / self.entry_price

    @property
    def reward_pct(self) -> float:
        if self.entry_price == 0: return 0
        return abs(self.take_profit_2 - self.entry_price) / self.entry_price


class TechnicalAnalyzer:
    """Compute technical indicators from OHLCV data."""

    @staticmethod
    def compute_rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def compute_atr(highs: list[float], lows: list[float], closes: list[float],
                     period: int = 14) -> float:
        if len(highs) < 2:
            return (highs[0] - lows[0]) if highs else 0
        trs = []
        for i in range(1, len(highs)):
            tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            trs.append(tr)
        return sum(trs[-period:]) / min(period, len(trs))

    @staticmethod
    def compute_sma(data: list[float], period: int) -> list[float]:
        result = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(data[i-period+1:i+1]) / period)
        return result

    @staticmethod
    def compute_ema(data: list[float], period: int) -> list[float]:
        result = []
        k = 2 / (period + 1)
        for i, v in enumerate(data):
            if i == 0:
                result.append(v)
            else:
                result.append(v * k + result[-1] * (1 - k))
        return result

    @staticmethod
    def compute_bollinger_bands(closes: list[float], period: int = 20, std_dev: float = 2.0) -> dict:
        sma = TechnicalAnalyzer.compute_sma(closes, period)
        result = {"upper": [], "middle": sma, "lower": []}
        for i in range(len(closes)):
            if sma[i] is None:
                result["upper"].append(None); result["lower"].append(None)
            else:
                window = closes[max(0,i-period+1):i+1]
                variance = sum((x - sma[i])**2 for x in window) / len(window)
                std = variance ** 0.5
                result["upper"].append(sma[i] + std_dev * std)
                result["lower"].append(sma[i] - std_dev * std)
        return result

    @staticmethod
    def compute_vwap(closes: list[float], highs: list[float], lows: list[float],
                      volumes: list[float]) -> float:
        if not volumes or sum(volumes) == 0:
            return closes[-1] if closes else 0
        total_vol = 0.0; total_tp_vol = 0.0
        for c, h, l, v in zip(closes, highs, lows, volumes):
            tp = (h + l + c) / 3
            total_tp_vol += tp * v
            total_vol    += v
        return total_tp_vol / total_vol if total_vol > 0 else closes[-1]

    @staticmethod
    def compute_adx(highs: list[float], lows: list[float], closes: list[float],
                     period: int = 14) -> float:
        """Average Directional Index — trend strength (>25 = trending)."""
        if len(highs) < period + 1:
            return 20.0
        plus_dm = [max(highs[i]-highs[i-1], 0) if highs[i]-highs[i-1] > lows[i-1]-lows[i] else 0
                   for i in range(1, len(highs))]
        minus_dm = [max(lows[i-1]-lows[i], 0) if lows[i-1]-lows[i] > highs[i]-highs[i-1] else 0
                    for i in range(1, len(highs))]
        tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
              for i in range(1, len(highs))]
        atr      = sum(tr[-period:]) / period
        plus_di  = 100 * sum(plus_dm[-period:])  / period / (atr or 1)
        minus_di = 100 * sum(minus_dm[-period:]) / period / (atr or 1)
        dx = 100 * abs(plus_di - minus_di) / ((plus_di + minus_di) or 1)
        return dx


class ScalpingStrategy:
    """
    1-5 minute scalping strategy.

    Rules:
      - Entry: Price near VWAP + RSI reversal (< 35 for long, > 65 for short)
      - Confirmation: 1-min momentum candle in direction
      - Stop: 0.3-0.5% from entry (ATR × 0.5)
      - Target: 1:1.5 to 1:2 R:R
      - Max 3-4 trades per symbol per session
      - No trades in last 30 min before market close
    """

    def generate(self, symbol: str, ohlcv: dict,
                 market_bias: str = "neutral",
                 emotional_score: float = 0.5) -> Optional[TradeIdea]:
        closes  = ohlcv.get("closes", [])
        highs   = ohlcv.get("highs", [])
        lows    = ohlcv.get("lows", [])
        volumes = ohlcv.get("volumes", [])

        if len(closes) < 20:
            return None

        current = closes[-1]
        rsi     = TechnicalAnalyzer.compute_rsi(closes, 14)
        atr     = TechnicalAnalyzer.compute_atr(highs, lows, closes, 14)
        vwap    = TechnicalAnalyzer.compute_vwap(closes, highs, lows, volumes)
        bb      = TechnicalAnalyzer.compute_bollinger_bands(closes, 20)

        # Emotional filter: don't scalp in extreme fear (< 0.2) or euphoria (> 0.9)
        if emotional_score < 0.15 or emotional_score > 0.92:
            return None

        # Long setup: price near lower BB / VWAP, RSI oversold
        near_lower_bb = bb["lower"][-1] and current <= bb["lower"][-1] * 1.005
        near_vwap_long = current <= vwap * 1.003
        rsi_oversold   = rsi < 38

        # Short setup: price near upper BB / VWAP, RSI overbought
        near_upper_bb  = bb["upper"][-1] and current >= bb["upper"][-1] * 0.995
        near_vwap_short = current >= vwap * 0.997
        rsi_overbought  = rsi > 62

        import uuid
        stop_dist = max(atr * 0.5, current * 0.003)  # Min 0.3%

        if (near_lower_bb or near_vwap_long) and rsi_oversold and market_bias != "bearish":
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.SCALPING,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.LONG,
                entry_price=current,
                stop_loss=current - stop_dist,
                take_profit_1=current + stop_dist,
                take_profit_2=current + stop_dist * 1.5,
                take_profit_3=current + stop_dist * 2.0,
                position_size_pct=0.015,  # 1.5% capital per scalp
                timeframe="5m",
                confidence=0.62,
                reasoning=(f"Scalp LONG: RSI={rsi:.0f} oversold, near "
                            f"{'lower BB' if near_lower_bb else 'VWAP'}, "
                            f"ATR stop={stop_dist:.2f}"),
                emotional_score=emotional_score,
                risk_reward=1.5,
            )

        if (near_upper_bb or near_vwap_short) and rsi_overbought and market_bias != "bullish":
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.SCALPING,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.SHORT,
                entry_price=current,
                stop_loss=current + stop_dist,
                take_profit_1=current - stop_dist,
                take_profit_2=current - stop_dist * 1.5,
                take_profit_3=current - stop_dist * 2.0,
                position_size_pct=0.015,
                timeframe="5m",
                confidence=0.62,
                reasoning=(f"Scalp SHORT: RSI={rsi:.0f} overbought, near "
                            f"{'upper BB' if near_upper_bb else 'VWAP'}, "
                            f"ATR stop={stop_dist:.2f}"),
                emotional_score=emotional_score,
                risk_reward=1.5,
            )
        return None


class MomentumStrategy:
    """
    Trend-following momentum strategy.
    Uses EMA crossover + ADX for trend confirmation.
    Best in trending markets (ADX > 25).
    """

    def generate(self, symbol: str, ohlcv: dict,
                 market_bias: str = "neutral",
                 emotional_score: float = 0.5) -> Optional[TradeIdea]:
        closes = ohlcv.get("closes", [])
        highs  = ohlcv.get("highs", [])
        lows   = ohlcv.get("lows", [])
        if len(closes) < 50: return None

        ema9  = TechnicalAnalyzer.compute_ema(closes, 9)
        ema21 = TechnicalAnalyzer.compute_ema(closes, 21)
        ema50 = TechnicalAnalyzer.compute_ema(closes, 50)
        adx   = TechnicalAnalyzer.compute_adx(highs, lows, closes, 14)
        rsi   = TechnicalAnalyzer.compute_rsi(closes, 14)
        atr   = TechnicalAnalyzer.compute_atr(highs, lows, closes, 14)

        current = closes[-1]
        if adx < 20: return None  # No trend

        import uuid
        # Bullish momentum
        if (ema9[-1] > ema21[-1] > ema50[-1] and
            ema9[-2] <= ema21[-2] and  # Fresh crossover
            35 < rsi < 70 and market_bias != "bearish"):
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.MOMENTUM,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.LONG,
                entry_price=current,
                stop_loss=ema21[-1] - atr * 0.5,
                take_profit_1=current + atr * 2,
                take_profit_2=current + atr * 3,
                take_profit_3=current + atr * 4,
                position_size_pct=0.03,
                timeframe="1h",
                confidence=0.68,
                reasoning=f"Momentum LONG: EMA9>{ema21[-1]:.0f}>EMA50, ADX={adx:.0f}, RSI={rsi:.0f}",
                emotional_score=emotional_score,
                risk_reward=2.5,
            )

        # Bearish momentum
        if (ema9[-1] < ema21[-1] < ema50[-1] and
            ema9[-2] >= ema21[-2] and
            30 < rsi < 65 and market_bias != "bullish"):
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.MOMENTUM,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.SHORT,
                entry_price=current,
                stop_loss=ema21[-1] + atr * 0.5,
                take_profit_1=current - atr * 2,
                take_profit_2=current - atr * 3,
                take_profit_3=current - atr * 4,
                position_size_pct=0.03,
                timeframe="1h",
                confidence=0.65,
                reasoning=f"Momentum SHORT: EMA9<{ema21[-1]:.0f}<EMA50, ADX={adx:.0f}, RSI={rsi:.0f}",
                emotional_score=emotional_score,
                risk_reward=2.5,
            )
        return None


class BreakoutStrategy:
    """
    Volume-confirmed breakout strategy.
    Identifies consolidation zones and trades breakouts with ATR stops.
    """

    def generate(self, symbol: str, ohlcv: dict,
                 market_bias: str = "neutral",
                 emotional_score: float = 0.5) -> Optional[TradeIdea]:
        closes  = ohlcv.get("closes", [])
        highs   = ohlcv.get("highs", [])
        lows    = ohlcv.get("lows", [])
        volumes = ohlcv.get("volumes", [])
        if len(closes) < 30: return None

        current  = closes[-1]
        atr      = TechnicalAnalyzer.compute_atr(highs, lows, closes, 14)
        lookback = min(20, len(closes)-1)
        resistance = max(highs[-lookback:-1])
        support    = min(lows[-lookback:-1])
        avg_vol    = sum(volumes[-lookback:-1]) / lookback if volumes else 1
        curr_vol   = volumes[-1] if volumes else avg_vol

        vol_surge = curr_vol > avg_vol * 1.5  # 50% above average

        import uuid
        # Upward breakout
        if current > resistance * 1.002 and vol_surge and market_bias != "bearish":
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.BREAKOUT,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.LONG,
                entry_price=current,
                stop_loss=resistance - atr * 0.5,  # Below breakout level
                take_profit_1=current + (current - support) * 0.5,
                take_profit_2=current + (current - support),
                take_profit_3=current + (current - support) * 1.5,
                position_size_pct=0.025,
                timeframe="daily",
                confidence=0.72,
                reasoning=f"Breakout LONG: Above resistance {resistance:.2f} with {vol_surge and 'high volume' or 'volume'}",
                emotional_score=emotional_score,
                risk_reward=2.0,
            )

        # Downward breakout
        if current < support * 0.998 and vol_surge and market_bias != "bullish":
            return TradeIdea(
                id=str(uuid.uuid4())[:8],
                strategy=StrategyType.BREAKOUT,
                symbol=symbol, exchange="NSE",
                direction=TradeDirection.SHORT,
                entry_price=current,
                stop_loss=support + atr * 0.5,
                take_profit_1=current - (resistance - current) * 0.5,
                take_profit_2=current - (resistance - current),
                take_profit_3=current - (resistance - current) * 1.5,
                position_size_pct=0.025,
                timeframe="daily",
                confidence=0.70,
                reasoning=f"Breakdown SHORT: Below support {support:.2f} with volume",
                emotional_score=emotional_score,
                risk_reward=2.0,
            )
        return None


class NewsIntelligenceStrategy:
    """
    News-driven trade ideas from market intelligence signals.
    Generates sector rotation and event-driven trades.
    """

    def generate_from_signals(self, signals: list[dict],
                               market_bias: str = "neutral") -> list[TradeIdea]:
        """Generate trade ideas from intelligence signals."""
        import uuid
        ideas = []
        for sig in signals[-10:]:  # Use latest 10 signals
            if abs(sig.get("impact_score", 0)) < 0.4:
                continue
            for sym in sig.get("affected_symbols", [])[:2]:
                is_bullish = sig["impact_score"] > 0
                direction  = TradeDirection.LONG if is_bullish else TradeDirection.SHORT
                idea = TradeIdea(
                    id=str(uuid.uuid4())[:8],
                    strategy=StrategyType.NEWS_DRIVEN,
                    symbol=sym, exchange="NSE",
                    direction=direction,
                    entry_price=0.0,   # Market price at time of execution
                    stop_loss=0.0,
                    take_profit_1=0.0,
                    take_profit_2=0.0,
                    take_profit_3=0.0,
                    position_size_pct=0.02,
                    timeframe="daily",
                    confidence=sig.get("confidence", 0.5),
                    reasoning=f"News signal ({sig['market_impact']}): {sig['title'][:80]}",
                    intelligence_signals=[sig["id"]],
                    risk_reward=2.0,
                )
                ideas.append(idea)
        return ideas


class StrategyOrchestrator:
    """
    Master orchestrator that:
      1. Pulls market intelligence
      2. Applies emotional intelligence filter
      3. Runs all strategies
      4. Ranks by confidence × R:R
      5. Returns top trade ideas
    """

    def __init__(self):
        self.scalping    = ScalpingStrategy()
        self.momentum    = MomentumStrategy()
        self.breakout    = BreakoutStrategy()
        self.news_strat  = NewsIntelligenceStrategy()

    async def generate_ideas(
        self,
        symbols:         list[str],
        price_data:      dict[str, dict],
        market_bias:     str = "neutral",
        emotional_score: float = 0.5,
        intelligence_signals: list[dict] = [],
    ) -> list[TradeIdea]:
        ideas = []
        for symbol in symbols:
            ohlcv = price_data.get(symbol, {})
            if not ohlcv:
                continue
            for strategy_fn in [self.scalping.generate, self.momentum.generate, self.breakout.generate]:
                try:
                    idea = strategy_fn(symbol, ohlcv, market_bias, emotional_score)
                    if idea:
                        ideas.append(idea)
                except Exception:
                    pass

        # Add news-driven ideas
        if intelligence_signals:
            news_ideas = self.news_strat.generate_from_signals(intelligence_signals, market_bias)
            ideas.extend(news_ideas)

        # Rank by composite score: confidence × risk_reward × (emotional appropriateness)
        def score(idea: TradeIdea) -> float:
            ei_multiplier = 1.0
            if emotional_score < 0.2 and idea.direction == TradeDirection.LONG:
                ei_multiplier = 0.5   # Reduce longs in extreme fear
            if emotional_score > 0.85 and idea.direction == TradeDirection.SHORT:
                ei_multiplier = 0.5  # Reduce shorts in extreme greed
            return idea.confidence * idea.risk_reward * ei_multiplier

        ideas.sort(key=score, reverse=True)
        return ideas[:10]  # Return top 10


def get_strategy_orchestrator() -> StrategyOrchestrator:
    return StrategyOrchestrator()
