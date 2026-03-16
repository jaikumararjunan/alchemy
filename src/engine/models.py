"""Pydantic models for Emotion Engine v2."""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Article(BaseModel):
    title: str
    summary: str = ""
    source: str = "unknown"
    url: str = ""
    published_at: str = ""


class AnalyzeRequest(BaseModel):
    articles: List[Article] = Field(..., min_length=1)
    model: Optional[str] = None  # override default model per-request
    context: Optional[str] = None  # optional extra context (e.g. "BTC just hit ATH")


class EmotionBreakdown(BaseModel):
    fear: float = 0.0
    greed: float = 0.0
    optimism: float = 0.0
    pessimism: float = 0.0
    panic: float = 0.0
    uncertainty: float = 0.0


class EmotionResult(BaseModel):
    sentiment_score: float = Field(description="-1.0 (extreme fear) to +1.0 (extreme greed)")
    confidence: float = Field(description="0.0–1.0")
    dominant_emotion: str
    emotions: EmotionBreakdown
    geopolitical_risk: str = Field(description="low | medium | high | critical")
    key_events: List[str] = Field(default_factory=list)
    trading_bias: str = Field(description="strong_buy | buy | neutral | sell | strong_sell")
    reasoning: str
    impact_horizon: str = Field(description="immediate | short_term | medium_term")
    crypto_specific_sentiment: float
    # v2 extras
    market_narrative: str = ""
    signal_strength: str = ""
    model_used: str = ""
    articles_analyzed: int = 0


class AnalyzeResponse(BaseModel):
    success: bool
    result: Optional[EmotionResult] = None
    error: Optional[str] = None
    analysis_id: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    model: str
    total_analyses: int
    version: str = "2.0.0"
