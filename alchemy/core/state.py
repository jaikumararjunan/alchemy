"""
alchemy.core.state
==================
Shared LangGraph state schema for the Alchemy multi-agent system.
Maps to AI-in-Trading-Workflow/gemini_fullstack_langgraph/state.py pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_serializer, Field


# ── Signal Types ──────────────────────────────────────────────────────────────

SignalType = Literal["BUY", "SELL", "HOLD"]
MarketType = Literal["NSE", "BSE", "NYSE", "NASDAQ", "CRYPTO"]
BrokerType = Literal["IB", "KITE", "PAPER"]


# ── LangGraph State (TypedDict-compatible via Pydantic) ───────────────────────

class AlchemyTradingState(BaseModel):
    """
    Shared state flowing through the LangGraph multi-agent pipeline.

    Lifecycle:
        fetch_news → analyze_sentiment → analyze_volatility → make_decision → execute
    """

    # ── Input ────────────────────────────────────────────────────────────────
    ticker: str = Field(..., description="Instrument symbol, e.g. 'RELIANCE' or 'AAPL'")
    market: MarketType = Field(default="NSE", description="Exchange for this instrument")
    broker: BrokerType = Field(default="PAPER", description="Execution broker")
    run_id: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))

    # ── Market Data ─────────────────────────────────────────────────────────
    price_data: dict = Field(default_factory=dict,
        description="Latest OHLCV snapshot: {open, high, low, close, volume, change_pct}")
    historical_returns: list[float] = Field(default_factory=list,
        description="Last 252 daily returns for volatility modelling")

    # ── News & Sentiment (Sentiment Agent) ──────────────────────────────────
    news_headlines: list[str] = Field(default_factory=list)
    news_sources: list[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = Field(None,
        description="Aggregate sentiment: -1.0 (bearish) to +1.0 (bullish)")
    sentiment_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    sentiment_reasoning: Optional[str] = None

    # ── Volatility (ARCH/GARCH Agent) ───────────────────────────────────────
    current_volatility: Optional[float] = Field(None,
        description="Annualized current realized volatility")
    forecast_volatility_1d: Optional[float] = Field(None,
        description="GARCH 1-day ahead annualized vol forecast")
    forecast_volatility_5d: Optional[float] = Field(None,
        description="GARCH 5-day ahead annualized vol forecast")
    vol_regime: Optional[Literal["low", "normal", "high", "extreme"]] = None

    # ── Decision (Decision Agent) ────────────────────────────────────────────
    signal: Optional[SignalType] = None
    position_pct: Optional[float] = Field(None, ge=0.0, le=1.0,
        description="Target portfolio weight for this position")
    stop_loss_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
    take_profit_pct: Optional[float] = Field(None, ge=0.0)
    decision_reasoning: Optional[str] = None

    # ── Execution ─────────────────────────────────────────────────────────
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    execution_price: Optional[float] = None
    execution_time: Optional[datetime] = None

    # ── Audit ─────────────────────────────────────────────────────────────
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict()

    def is_actionable(self) -> bool:
        """Returns True if the state has a tradeable signal."""
        return self.signal in ("BUY", "SELL") and self.position_pct is not None

    def add_error(self, msg: str) -> None:
        self.errors.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    def add_warning(self, msg: str) -> None:
        self.warnings.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


@dataclass
class TradingSignal:
    """Lightweight signal emitted by the decision agent."""
    ticker: str
    market: MarketType
    signal: SignalType
    position_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    sentiment_score: float
    forecast_vol: float
    reasoning: str
    run_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "market": self.market,
            "signal": self.signal,
            "position_pct": round(self.position_pct, 4),
            "stop_loss_pct": round(self.stop_loss_pct, 4),
            "take_profit_pct": round(self.take_profit_pct, 4),
            "sentiment_score": round(self.sentiment_score, 4),
            "forecast_vol": round(self.forecast_vol, 4),
            "reasoning": self.reasoning,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
        }
