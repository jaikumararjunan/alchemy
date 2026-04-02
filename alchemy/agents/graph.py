"""
alchemy.agents.graph
====================
LangGraph multi-agent trading orchestrator.
Adapted from: https://github.com/QuantInsti/AI-in-Trading-Workflow

Agent pipeline:
    fetch_news → analyze_sentiment → analyze_volatility → make_decision → [execute]

Each node is a pure function: AlchemyTradingState → AlchemyTradingState
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from alchemy.core.config import get_config
from alchemy.core.state import AlchemyTradingState, SignalType, TradingSignal
from alchemy.llm.router import AlchemyLLMRouter

log = structlog.get_logger(__name__)


# ── Prompts ──────────────────────────────────────────────────────────────────

SENTIMENT_PROMPT = """Analyse the following news headlines for {ticker} on {market}.

Headlines:
{headlines}

Return JSON only:
{{
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "key_themes": [<string>, ...],
  "reasoning": "<1-2 sentence explanation>"
}}"""

DECISION_PROMPT = """Generate a trading decision for {ticker} on {market}.

Context:
- Current price change: {change_pct:.2%}
- Sentiment score: {sentiment:.2f} (confidence: {confidence:.0%})
- Current annualised volatility: {current_vol:.1%}
- 5-day volatility forecast: {forecast_vol:.1%}
- Volatility regime: {vol_regime}
- Max allowed position: {max_position:.0%}

Rules:
- BUY only if sentiment > 0.25 AND vol_regime NOT 'extreme'
- SELL only if sentiment < -0.25
- HOLD otherwise
- Scale position inversely with volatility
- Stop loss = 2x daily vol, Take profit = 4x daily vol

Return JSON only:
{{
  "signal": "BUY" | "SELL" | "HOLD",
  "position_pct": <float 0.0-{max_position:.2f}>,
  "stop_loss_pct": <float>,
  "take_profit_pct": <float>,
  "reasoning": "<concise explanation>"
}}"""


# ── Node Functions ────────────────────────────────────────────────────────────

def fetch_news_node(state: dict) -> dict:
    """Fetch latest news headlines for the ticker. (Stub — wire to real feed.)"""
    ticker = state["ticker"]
    log.info("agent.fetch_news", ticker=ticker)

    # In production: call NewsAPI / QuantInsti news feed / yfinance news
    headlines = state.get("news_headlines", [
        f"{ticker} reports strong quarterly results, beating estimates",
        f"Analysts upgrade {ticker} price target amid sector momentum",
        f"{ticker} announces strategic expansion initiative",
    ])
    return {**state, "news_headlines": headlines}


def sentiment_node(state: dict, llm: AlchemyLLMRouter) -> dict:
    """LLM-powered news sentiment analysis node."""
    ticker = state["ticker"]
    market = state.get("market", "NSE")
    headlines = state.get("news_headlines", [])

    log.info("agent.sentiment", ticker=ticker, n_headlines=len(headlines))

    if not headlines:
        state_obj = AlchemyTradingState(**state)
        state_obj.add_warning("No headlines found; sentiment defaulting to neutral")
        return {**state_obj.to_dict(), "sentiment_score": 0.0, "sentiment_confidence": 0.5}

    prompt = SENTIMENT_PROMPT.format(
        ticker=ticker,
        market=market,
        headlines="\n".join(f"- {h}" for h in headlines),
    )

    try:
        result = llm.complete(user=prompt, json_mode=True)
        assert isinstance(result, dict)
        return {
            **state,
            "sentiment_score": float(result.get("sentiment_score", 0.0)),
            "sentiment_confidence": float(result.get("confidence", 0.5)),
            "sentiment_reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        log.error("agent.sentiment_error", error=str(e))
        return {**state, "sentiment_score": 0.0, "sentiment_confidence": 0.0}


def volatility_node(state: dict) -> dict:
    """
    GARCH volatility estimation node.
    Uses alchemy.analytics.volatility.VolatilityEngine (arch library).
    """
    log.info("agent.volatility", ticker=state["ticker"])

    # Lazy import to allow running without arch in test mode
    try:
        from alchemy.analytics.volatility import VolatilityEngine
        import numpy as np
        import pandas as pd

        returns_raw = state.get("historical_returns", [])
        if len(returns_raw) >= 30:
            returns = pd.Series(returns_raw)
            engine = VolatilityEngine()
            engine.fit(returns)
            current_vol = engine.get_current_vol().iloc[-1]
            forecast_5d = engine.forecast_vol(horizon=5)
        else:
            # Fallback: simple rolling vol
            price_data = state.get("price_data", {})
            current_vol = abs(price_data.get("change_pct", 0.01)) * 16  # rough annualise
            forecast_5d = current_vol

        # Classify regime
        if current_vol < 0.15:
            regime = "low"
        elif current_vol < 0.25:
            regime = "normal"
        elif current_vol < 0.40:
            regime = "high"
        else:
            regime = "extreme"

        return {
            **state,
            "current_volatility": round(float(current_vol), 4),
            "forecast_volatility_5d": round(float(forecast_5d), 4),
            "vol_regime": regime,
        }
    except Exception as e:
        log.warning("agent.volatility_fallback", error=str(e))
        return {**state, "current_volatility": 0.20, "forecast_volatility_5d": 0.20,
                "vol_regime": "normal"}


def decision_node(state: dict, llm: AlchemyLLMRouter) -> dict:
    """LLM-powered final trading decision node."""
    cfg = get_config().risk
    log.info("agent.decision", ticker=state["ticker"])

    prompt = DECISION_PROMPT.format(
        ticker=state["ticker"],
        market=state.get("market", "NSE"),
        change_pct=state.get("price_data", {}).get("change_pct", 0.0),
        sentiment=state.get("sentiment_score", 0.0),
        confidence=state.get("sentiment_confidence", 0.5),
        current_vol=state.get("current_volatility", 0.20),
        forecast_vol=state.get("forecast_volatility_5d", 0.20),
        vol_regime=state.get("vol_regime", "normal"),
        max_position=cfg.max_position_pct,
    )

    try:
        result = llm.complete(user=prompt, json_mode=True)
        assert isinstance(result, dict)
        return {
            **state,
            "signal": result.get("signal", "HOLD"),
            "position_pct": float(result.get("position_pct", 0.0)),
            "stop_loss_pct": float(result.get("stop_loss_pct", cfg.default_stop_loss_pct)),
            "take_profit_pct": float(result.get("take_profit_pct", cfg.default_take_profit_pct)),
            "decision_reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        log.error("agent.decision_error", error=str(e))
        return {**state, "signal": "HOLD", "position_pct": 0.0}


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_alchemy_graph(llm: AlchemyLLMRouter | None = None) -> Any:
    """
    Constructs the compiled LangGraph agent graph.

    Returns a CompiledGraph ready for .invoke() or .stream().
    """
    if llm is None:
        llm = AlchemyLLMRouter()

    # Bind LLM to nodes that need it
    def _sentiment(state: dict) -> dict:
        return sentiment_node(state, llm)

    def _decision(state: dict) -> dict:
        return decision_node(state, llm)

    graph = StateGraph(dict)
    graph.add_node("fetch_news",          fetch_news_node)
    graph.add_node("analyze_sentiment",   _sentiment)
    graph.add_node("analyze_volatility",  volatility_node)
    graph.add_node("make_decision",       _decision)

    graph.set_entry_point("fetch_news")
    graph.add_edge("fetch_news",         "analyze_sentiment")
    graph.add_edge("analyze_sentiment",  "analyze_volatility")
    graph.add_edge("analyze_volatility", "make_decision")
    graph.add_edge("make_decision",      END)

    return graph.compile()


def run_agent(
    ticker: str,
    market: str = "NSE",
    broker: str = "PAPER",
    price_data: dict | None = None,
    news_headlines: list[str] | None = None,
    historical_returns: list[float] | None = None,
) -> TradingSignal:
    """
    High-level entry point: run the full agent pipeline for one ticker.

    Example::

        signal = run_agent("RELIANCE", market="NSE", broker="PAPER")
        print(signal.signal, signal.position_pct)
    """
    initial_state = AlchemyTradingState(
        ticker=ticker,
        market=market,  # type: ignore[arg-type]
        broker=broker,  # type: ignore[arg-type]
        price_data=price_data or {},
        news_headlines=news_headlines or [],
        historical_returns=historical_returns or [],
    )

    graph = build_alchemy_graph()
    final = graph.invoke(initial_state.to_dict())

    return TradingSignal(
        ticker=final["ticker"],
        market=final.get("market", "NSE"),
        signal=final.get("signal", "HOLD"),
        position_pct=final.get("position_pct", 0.0),
        stop_loss_pct=final.get("stop_loss_pct", 0.02),
        take_profit_pct=final.get("take_profit_pct", 0.04),
        sentiment_score=final.get("sentiment_score", 0.0),
        forecast_vol=final.get("forecast_volatility_5d", 0.20),
        reasoning=final.get("decision_reasoning", ""),
        run_id=final.get("run_id", ""),
    )
