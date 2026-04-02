"""
alchemy.api.app
===============
FastAPI application — REST API for the Alchemy trading platform.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from alchemy.core.config import get_config
from alchemy.core.state import AlchemyTradingState, TradingSignal

log = structlog.get_logger(__name__)

# ── Request / Response Models ─────────────────────────────────────────────────

class SignalRequest(BaseModel):
    ticker: str
    market: str = "NSE"
    broker: str = "PAPER"
    news_headlines: list[str] = []
    price_data: dict = {}

class SignalResponse(BaseModel):
    ticker: str
    signal: str
    position_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    sentiment_score: float
    forecast_vol: float
    reasoning: str
    run_id: str

class HealthResponse(BaseModel):
    status: str
    version: str
    env: str

# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    log.info("alchemy.startup", env=cfg.env, ai_agents=cfg.enable_ai_agents)
    yield
    log.info("alchemy.shutdown")


app = FastAPI(
    title="Alchemy Trading Platform",
    description="AI-powered algorithmic trading — QuantInsti Integration",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    cfg = get_config()
    return HealthResponse(status="ok", version="0.1.0", env=cfg.env)


@app.post("/signal", response_model=SignalResponse)
async def generate_signal(req: SignalRequest):
    """Run the full AI agent pipeline and return a trading signal."""
    cfg = get_config()
    if not cfg.enable_ai_agents:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    try:
        from alchemy.agents.graph import run_agent
        signal: TradingSignal = run_agent(
            ticker=req.ticker,
            market=req.market,
            broker=req.broker,
            price_data=req.price_data,
            news_headlines=req.news_headlines,
        )
        return SignalResponse(**signal.to_dict())
    except Exception as e:
        log.error("api.signal_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/risk/status")
async def risk_status():
    """Return current risk manager status."""
    from alchemy.risk.manager import RiskManager
    rm = RiskManager()
    return rm.status()
