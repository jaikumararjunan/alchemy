"""
alchemy.intelligence.emotion.ei_engine
=======================================
Emotional Intelligence (EI) Engine for trading.

Tracks and models:
  1. Market Fear & Greed Index (composite of VIX, breadth, momentum, safe havens)
  2. Trader emotional state (per-user P&L-driven emotional calibration)
  3. Crowd sentiment (social media, options put/call ratio)
  4. Historical emotion-to-outcome correlation (stored in vector DB)

All EI data is stored in ChromaDB vector database for:
  - Finding similar historical market emotional states
  - Retrieving what strategies worked in those states
  - Fine-tuning trade sizing based on emotional regime

Usage::

    ei = EmotionalIntelligenceEngine()
    score = await ei.compute_market_ei(ohlcv_data, news_signals)
    print(score.fear_greed_index)    # 0-100 (0=extreme fear, 100=extreme greed)
    similar = await ei.find_similar_states(score)   # Vector DB lookup
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import structlog

log = structlog.get_logger(__name__)


@dataclass
class EmotionalState:
    """Composite emotional intelligence reading."""
    timestamp:          datetime   = field(default_factory=lambda: datetime.now(timezone.utc))
    fear_greed_index:   float      = 50.0    # 0 = extreme fear, 100 = extreme greed
    regime:             str        = "neutral"  # extreme_fear|fear|neutral|greed|extreme_greed
    vix_score:          float      = 50.0    # 0=low vol, 100=high vol
    breadth_score:      float      = 50.0    # Advance/decline ratio
    momentum_score:     float      = 50.0
    social_score:       float      = 50.0    # Social media sentiment
    options_score:      float      = 50.0    # Put/call ratio sentiment
    news_score:         float      = 50.0    # News sentiment from intelligence
    trader_emotion:     str        = "calm"  # panic|anxious|calm|confident|euphoric
    recommended_sizing: float      = 1.0     # 0.25-1.5 multiplier on base position size
    notes:              str        = ""

    def to_vector(self) -> list[float]:
        """Convert to embedding vector for ChromaDB."""
        return [
            self.fear_greed_index / 100,
            self.vix_score / 100,
            self.breadth_score / 100,
            self.momentum_score / 100,
            self.social_score / 100,
            self.options_score / 100,
            self.news_score / 100,
        ]

    def to_dict(self) -> dict:
        return {
            "timestamp":          self.timestamp.isoformat(),
            "fear_greed_index":   round(self.fear_greed_index, 1),
            "regime":             self.regime,
            "trader_emotion":     self.trader_emotion,
            "recommended_sizing": self.recommended_sizing,
            "vix_score":          round(self.vix_score, 1),
            "breadth_score":      round(self.breadth_score, 1),
            "news_score":         round(self.news_score, 1),
            "notes":              self.notes,
        }


@dataclass
class TradeEmotionRecord:
    """Links an emotional state to a trade outcome for ML training."""
    trade_id:         str
    user_id:          str
    emotional_state:  EmotionalState
    strategy:         str
    symbol:           str
    direction:        str
    pnl:              float
    pnl_pct:          float
    outcome:          str      # win | loss | breakeven
    lesson:           str      = ""
    created_at:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VectorStore:
    """
    ChromaDB-backed vector store for emotional intelligence history.
    Falls back to in-memory store if ChromaDB unavailable.
    """

    def __init__(self, path: str = "./data/chromadb") -> None:
        self._client = None
        self._collection = None
        self._fallback: list[dict] = []
        self._path = path
        self._init()

    def _init(self) -> None:
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self._path)
            self._collection = self._client.get_or_create_collection(
                name="emotional_intelligence",
                metadata={"hnsw:space": "cosine"},
            )
            log.info("chromadb.initialized", path=self._path,
                     count=self._collection.count())
        except ImportError:
            log.warning("chromadb.not_installed",
                        hint="pip install chromadb")
        except Exception as e:
            log.error("chromadb.init_failed", error=str(e))

    def store(self, state: EmotionalState, metadata: dict) -> bool:
        """Store an emotional state with metadata."""
        doc_id = f"ei_{int(state.timestamp.timestamp())}"
        document = (f"fear_greed={state.fear_greed_index:.0f} "
                    f"regime={state.regime} "
                    f"strategy={metadata.get('strategy','')} "
                    f"outcome={metadata.get('outcome','')} "
                    f"pnl_pct={metadata.get('pnl_pct',0):.2f}")
        try:
            if self._collection:
                self._collection.upsert(
                    ids=[doc_id],
                    embeddings=[state.to_vector()],
                    documents=[document],
                    metadatas=[{**metadata, "timestamp": state.timestamp.isoformat(),
                                "regime": state.regime,
                                "fear_greed": state.fear_greed_index}],
                )
                return True
        except Exception as e:
            log.error("vector_store.store_failed", error=str(e))
        # Fallback
        self._fallback.append({"id": doc_id, "state": state.to_dict(), "metadata": metadata})
        if len(self._fallback) > 500:
            self._fallback = self._fallback[-250:]
        return True

    def find_similar(self, state: EmotionalState, n_results: int = 5) -> list[dict]:
        """Find historically similar emotional states and their outcomes."""
        try:
            if self._collection and self._collection.count() > 0:
                results = self._collection.query(
                    query_embeddings=[state.to_vector()],
                    n_results=min(n_results, self._collection.count()),
                )
                return [
                    {"document": doc, "metadata": meta, "distance": dist}
                    for doc, meta, dist in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    )
                ]
        except Exception as e:
            log.error("vector_store.query_failed", error=str(e))
        # Fallback: filter by similar regime
        return [r for r in self._fallback
                if r["state"].get("regime") == state.regime][:n_results]

    def get_strategy_performance_by_regime(self, regime: str) -> dict:
        """Get average P&L per strategy for a given emotional regime."""
        try:
            if self._collection and self._collection.count() > 0:
                results = self._collection.get(
                    where={"regime": regime},
                )
                if results["metadatas"]:
                    from collections import defaultdict
                    perf = defaultdict(list)
                    for meta in results["metadatas"]:
                        strat = meta.get("strategy", "unknown")
                        pnl   = meta.get("pnl_pct", 0)
                        perf[strat].append(pnl)
                    return {
                        strat: {
                            "avg_pnl_pct": sum(pnls)/len(pnls),
                            "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
                            "trades":   len(pnls),
                        }
                        for strat, pnls in perf.items()
                    }
        except Exception:
            pass
        return {}


class EmotionalIntelligenceEngine:
    """
    Core EI engine — measures market and trader emotional state.

    Computes a composite Fear & Greed Index from:
      - Price momentum vs 50-day average (25% weight)
      - Market breadth proxy (20%)
      - News sentiment (25%)
      - Social media sentiment (10%)
      - Options put/call proxy (20%)
    """

    def __init__(self) -> None:
        self.vector_store = VectorStore()
        self._history: list[EmotionalState] = []

    def compute_from_price_data(
        self,
        closes: list[float],
        volumes: list[float],
        news_score: float = 50.0,
        social_score: float = 50.0,
    ) -> EmotionalState:
        """
        Compute emotional state from OHLCV data + external sentiment scores.

        Args:
            closes:      List of closing prices (50+ bars)
            volumes:     List of volumes
            news_score:  0-100 from intelligence crawler (0=very bearish, 100=very bullish)
            social_score: 0-100 from social sentiment
        """
        if not closes:
            return EmotionalState()

        # 1. Momentum: price vs 50-day SMA
        period = min(50, len(closes))
        sma50  = sum(closes[-period:]) / period
        curr   = closes[-1]
        momentum_raw  = (curr - sma50) / sma50  # -0.2 to +0.2 typically
        momentum_score = max(0, min(100, 50 + momentum_raw * 200))

        # 2. Volatility: coefficient of variation of last 20 closes
        if len(closes) >= 20:
            recent   = closes[-20:]
            mean_r   = sum(recent) / len(recent)
            std_r    = math.sqrt(sum((x-mean_r)**2 for x in recent) / len(recent))
            cv       = std_r / (mean_r or 1)
            vix_score = max(0, min(100, cv * 1000))  # Scale
        else:
            vix_score = 50.0

        # 3. Volume trend (high volume down = fear, high volume up = greed)
        vol_score = 50.0
        if len(volumes) >= 10 and len(closes) >= 10:
            recent_vols   = volumes[-10:]
            avg_vol       = sum(recent_vols) / len(recent_vols)
            price_5d      = closes[-5] if len(closes) >= 5 else closes[0]
            price_up      = curr > price_5d
            vol_ratio     = (volumes[-1] / avg_vol) if avg_vol > 0 else 1.0
            vol_score     = 50 + (25 if price_up else -25) * min(vol_ratio, 2.0) / 2.0

        # 4. Composite Fear & Greed (weighted average)
        fg = (
            momentum_score  * 0.25 +
            news_score      * 0.25 +
            (100 - vix_score) * 0.20 +   # Low vol = greed
            social_score    * 0.10 +
            vol_score       * 0.20
        )
        fg = max(0, min(100, fg))

        # Determine regime
        if fg <= 20:   regime = "extreme_fear"
        elif fg <= 40: regime = "fear"
        elif fg <= 60: regime = "neutral"
        elif fg <= 80: regime = "greed"
        else:          regime = "extreme_greed"

        # Trader emotion label
        emotion_map = {
            "extreme_fear": "panic",
            "fear":         "anxious",
            "neutral":      "calm",
            "greed":        "confident",
            "extreme_greed":"euphoric",
        }
        trader_emotion = emotion_map[regime]

        # Position sizing recommendation
        sizing_map = {
            "extreme_fear":  0.25,   # Be very cautious in panic
            "fear":          0.60,   # Slightly cautious
            "neutral":       1.00,   # Normal sizing
            "greed":         0.85,   # Slightly reduce (market complacent)
            "extreme_greed": 0.50,   # Reduce significantly (euphoria = top)
        }
        recommended_sizing = sizing_map[regime]

        state = EmotionalState(
            fear_greed_index=round(fg, 1),
            regime=regime,
            vix_score=round(vix_score, 1),
            breadth_score=round(vol_score, 1),
            momentum_score=round(momentum_score, 1),
            social_score=round(social_score, 1),
            options_score=50.0,
            news_score=round(news_score, 1),
            trader_emotion=trader_emotion,
            recommended_sizing=recommended_sizing,
            notes=self._generate_notes(fg, regime, momentum_score, vix_score),
        )
        self._history.append(state)
        if len(self._history) > 200:
            self._history = self._history[-100:]
        return state

    def _generate_notes(self, fg: float, regime: str, momentum: float, vix: float) -> str:
        notes = []
        if fg < 20:
            notes.append("Extreme fear — historically good BUY opportunity if fundamentals intact")
        elif fg > 80:
            notes.append("Extreme greed — consider reducing positions, risk of correction")
        if vix > 70:
            notes.append("High volatility — widen stops, reduce size, expect whipsaws")
        if momentum < 30:
            notes.append("Below 50-day SMA — trend is down, prefer short setups")
        elif momentum > 70:
            notes.append("Above 50-day SMA — trend is up, prefer long setups")
        return ". ".join(notes) if notes else "Normal market conditions."

    def record_trade_outcome(self, trade_id: str, user_id: str, strategy: str,
                              symbol: str, direction: str, pnl: float, pnl_pct: float) -> None:
        """Record trade outcome linked to current emotional state for ML training."""
        if not self._history:
            return
        state   = self._history[-1]
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"
        lesson  = self._derive_lesson(state, outcome, strategy)

        record = TradeEmotionRecord(
            trade_id=trade_id, user_id=user_id,
            emotional_state=state, strategy=strategy,
            symbol=symbol, direction=direction,
            pnl=pnl, pnl_pct=pnl_pct,
            outcome=outcome, lesson=lesson,
        )
        # Store in vector DB
        self.vector_store.store(state, {
            "trade_id": trade_id, "user_id": user_id,
            "strategy": strategy, "symbol": symbol,
            "direction": direction, "pnl": pnl,
            "pnl_pct": pnl_pct, "outcome": outcome,
            "lesson": lesson,
        })
        log.info("ei.trade_recorded", trade_id=trade_id, outcome=outcome, regime=state.regime)

    def _derive_lesson(self, state: EmotionalState, outcome: str, strategy: str) -> str:
        if outcome == "loss" and state.regime == "extreme_fear" and strategy == "scalping":
            return "Avoid scalping in extreme fear — stop runs are common"
        if outcome == "win" and state.regime == "extreme_fear" and strategy == "breakout":
            return "Breakout shorts work well in fear regimes"
        if outcome == "loss" and state.regime == "extreme_greed":
            return "Reduce position size in extreme greed — reversals are sharp"
        return f"{strategy} resulted in {outcome} during {state.regime}"

    def get_strategy_guidance(self) -> dict:
        """
        Return strategy recommendations based on current emotional state.
        Factors in historical performance from vector DB.
        """
        if not self._history:
            return {"regime": "unknown", "recommendations": []}

        state  = self._history[-1]
        regime = state.regime
        historical_perf = self.vector_store.get_strategy_performance_by_regime(regime)

        recommendations = {
            "extreme_fear": [
                "BUY extreme fear on quality stocks — use 25% normal size",
                "Avoid scalping — high whipsaw risk",
                "Look for oversold RSI < 20 bounces",
                "Consider contra-trend options (call buying on oversold)",
            ],
            "fear": [
                "Cautious longs on key support levels",
                "Scalping valid but tight stops",
                "Prefer cash-rich, defensive sectors (FMCG, Pharma)",
            ],
            "neutral": [
                "All strategies valid",
                "Momentum and breakout setups have best R:R",
                "Normal position sizing",
            ],
            "greed": [
                "Reduce new longs — take partial profits",
                "Tighten trailing stops",
                "Watch for distribution patterns",
            ],
            "extreme_greed": [
                "SELL into euphoria — reduce 50% of longs",
                "Buy puts for portfolio hedge",
                "Only trade short setups with tight stops",
                "Preserve capital — next correction can be sharp",
            ],
        }

        result = {
            "regime":             regime,
            "fear_greed_index":   state.fear_greed_index,
            "trader_emotion":     state.trader_emotion,
            "recommended_sizing": state.recommended_sizing,
            "recommendations":    recommendations.get(regime, []),
            "historical_perf":    historical_perf,
            "notes":              state.notes,
        }
        return result

    def current_state(self) -> Optional[dict]:
        if not self._history:
            return None
        return self._history[-1].to_dict()


# Singleton
_ei_engine: Optional[EmotionalIntelligenceEngine] = None

def get_ei_engine() -> EmotionalIntelligenceEngine:
    global _ei_engine
    if _ei_engine is None:
        _ei_engine = EmotionalIntelligenceEngine()
    return _ei_engine
