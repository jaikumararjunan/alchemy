"""FastAPI routes for Emotion Engine v2 + real-time trading dashboard."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import AppConfig
from src.api.price_feed import feed
from src.api.ws import manager
from src.engine.analyzer import EmotionAnalyzer
from src.engine.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    Article,
    HealthResponse,
)
from src.storage.db import AnalysisStore
from src.strategy.futures_strategies import (
    FundingSnapshot,
    FuturesContract,
    FuturesStrategySelector,
)
from src.strategy.options_strategies import OptionsStrategySelector

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic request bodies for new strategy endpoints ────────────────────────


class OptionsSignalRequest(BaseModel):
    """Request body for the /options/signal endpoint."""
    symbol: str = "BTC"
    spot: float = Field(..., gt=0, description="Current spot price in USD")
    iv: float = Field(..., gt=0, le=5.0, description="Implied volatility as decimal (e.g. 0.80)")
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    iv_percentile: float = Field(50.0, ge=0.0, le=100.0)
    geopolitical_risk: str = "low"
    expected_move_pct: float = Field(0.0, ge=0.0)
    run_all: bool = False


class FuturesContractInput(BaseModel):
    symbol: str
    contract_type: str = "perpetual"
    mark_price: float
    index_price: float
    funding_rate_8h: float = 0.0
    open_interest_usd: float = 0.0
    volume_24h_usd: float = 0.0
    leverage: float = 5.0
    expiry_days: Optional[int] = None
    annualised_basis_pct: Optional[float] = None


class FundingSnapshotInput(BaseModel):
    symbol: str
    funding_rate_8h: float
    predicted_funding_8h: float = 0.0
    oi_usd: float = 0.0
    oi_change_pct_1h: float = 0.0
    long_ratio: float = 0.5
    short_ratio: float = 0.5
    liquidations_1h_long_usd: float = 0.0
    liquidations_1h_short_usd: float = 0.0


class FuturesSignalRequest(BaseModel):
    """Request body for the /futures/signal endpoint."""
    symbol: str = "BTC"
    candles: List[Dict[str, Any]] = Field(default_factory=list)
    perp_contract: FuturesContractInput
    funding: FundingSnapshotInput
    spot: float = 0.0
    near_contract: Optional[FuturesContractInput] = None
    far_contract: Optional[FuturesContractInput] = None
    run_all: bool = False


# ── Dependency helpers ────────────────────────────────────────────────────────

def _get_analyzer(request) -> EmotionAnalyzer:  # type: ignore[no-untyped-def]
    return request.app.state.analyzer


def _get_store(request) -> AnalysisStore:  # type: ignore[no-untyped-def]
    return request.app.state.store


def _get_config(request) -> AppConfig:  # type: ignore[no-untyped-def]
    return request.app.state.config


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health(request) -> HealthResponse:  # type: ignore[no-untyped-def]
    store: AnalysisStore = _get_store(request)
    cfg: AppConfig = _get_config(request)
    return HealthResponse(
        status="ok",
        model=cfg.claude.model,
        total_analyses=store.count(),
    )


# ── Sentiment analysis ────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest, request) -> AnalyzeResponse:  # type: ignore[no-untyped-def]
    analyzer: EmotionAnalyzer = _get_analyzer(request)
    store: AnalysisStore = _get_store(request)

    try:
        result = analyzer.analyze(
            articles=body.articles,
            model_override=body.model,
            context=body.context,
        )
        analysis_id = store.save(result)

        # Push live result to all dashboard clients
        await manager.broadcast({
            "type": "sentiment",
            "analysis_id": analysis_id,
            "result": result.model_dump(),
        })

        return AnalyzeResponse(success=True, result=result, analysis_id=analysis_id)
    except Exception as exc:
        logger.error("Analysis failed: %s", exc, exc_info=True)
        return AnalyzeResponse(success=False, error=str(exc))


# ── Recent analyses ───────────────────────────────────────────────────────────

@router.get("/analyses/recent")
async def recent_analyses(request, limit: int = 10) -> list:  # type: ignore[no-untyped-def]
    store: AnalysisStore = _get_store(request)
    return store.get_recent(limit=min(limit, 100))


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: int, request):  # type: ignore[no-untyped-def]
    store: AnalysisStore = _get_store(request)
    data = store.get_by_id(analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return data


# ── Price data (REST) ─────────────────────────────────────────────────────────

@router.get("/prices")
async def get_prices() -> dict:
    """Current prices for all tracked symbols."""
    return {"prices": feed.last_prices()}


@router.get("/prices/{symbol}/history")
async def get_price_history(symbol: str) -> dict:
    """
    Return cached OHLC history for a symbol.
    Triggers a fresh CoinGecko fetch if cache is empty.
    """
    sym = symbol.upper()
    candles = feed.cached_history(sym)
    if not candles:
        candles = await feed.fetch_history(sym)
    return {"symbol": sym, "candles": candles}


# ── Options strategy signals ─────────────────────────────────────────────────


@router.post("/options/signal")
async def options_signal(body: OptionsSignalRequest) -> dict:
    """
    Run the options strategy selector (or all strategies) and return signals.

    The selector picks the single highest-confidence signal.
    Set `run_all=true` to get all eight strategies' outputs.
    """
    selector = OptionsStrategySelector(symbol=body.symbol)

    if body.run_all:
        signals = selector.run_all(
            spot=body.spot,
            iv=body.iv,
            sentiment_score=body.sentiment_score,
            iv_percentile=body.iv_percentile,
            geopolitical_risk=body.geopolitical_risk,
            expected_move_pct=body.expected_move_pct,
        )
        result = {"signals": [s.to_dict() for s in signals]}
    else:
        sig = selector.select_best(
            spot=body.spot,
            iv=body.iv,
            sentiment_score=body.sentiment_score,
            iv_percentile=body.iv_percentile,
            geopolitical_risk=body.geopolitical_risk,
            expected_move_pct=body.expected_move_pct,
        )
        result = {"signal": sig.to_dict()}

    # Broadcast to dashboard
    await manager.broadcast({
        "type": "options_signal",
        "symbol": body.symbol,
        **result,
    })
    return result


# ── Futures strategy signals ──────────────────────────────────────────────────


def _build_contract(inp: FuturesContractInput) -> FuturesContract:
    return FuturesContract(
        symbol=inp.symbol,
        contract_type=inp.contract_type,
        mark_price=inp.mark_price,
        index_price=inp.index_price,
        funding_rate_8h=inp.funding_rate_8h,
        open_interest_usd=inp.open_interest_usd,
        volume_24h_usd=inp.volume_24h_usd,
        leverage=inp.leverage,
        expiry_days=inp.expiry_days,
        annualised_basis_pct=inp.annualised_basis_pct,
    )


def _build_funding(inp: FundingSnapshotInput) -> FundingSnapshot:
    return FundingSnapshot(
        symbol=inp.symbol,
        funding_rate_8h=inp.funding_rate_8h,
        predicted_funding_8h=inp.predicted_funding_8h,
        oi_usd=inp.oi_usd,
        oi_change_pct_1h=inp.oi_change_pct_1h,
        long_ratio=inp.long_ratio,
        short_ratio=inp.short_ratio,
        liquidations_1h_long_usd=inp.liquidations_1h_long_usd,
        liquidations_1h_short_usd=inp.liquidations_1h_short_usd,
    )


@router.post("/futures/signal")
async def futures_signal(body: FuturesSignalRequest) -> dict:
    """
    Run the futures strategy selector (or all strategies) and return signals.

    Provide `candles` (OHLCV list), `perp_contract`, and `funding` at minimum.
    Include `near_contract` and `far_contract` to enable basis/calendar signals.
    Set `run_all=true` to get every strategy's output.
    """
    selector = FuturesStrategySelector(symbol=body.symbol)
    perp = _build_contract(body.perp_contract)
    funding = _build_funding(body.funding)
    near = _build_contract(body.near_contract) if body.near_contract else None
    far  = _build_contract(body.far_contract)  if body.far_contract  else None

    if body.run_all:
        signals = selector.run_all(
            candles=body.candles,
            perp_contract=perp,
            funding=funding,
            spot=body.spot,
            near_contract=near,
            far_contract=far,
        )
        result = {"signals": [s.to_dict() for s in signals]}
    else:
        sig = selector.select_best(
            candles=body.candles,
            perp_contract=perp,
            funding=funding,
            spot=body.spot,
            near_contract=near,
            far_contract=far,
        )
        result = {"signal": sig.to_dict()}

    # Broadcast to dashboard
    await manager.broadcast({
        "type": "futures_signal",
        "symbol": body.symbol,
        **result,
    })
    return result


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send initial state on connect
        await manager.send(ws, {
            "type": "init",
            "prices": feed.last_prices(),
            "symbols": list(feed.symbols),
        })
        # Keep the connection alive; broadcast is handled by PriceFeed
        while True:
            data = await ws.receive_json()
            # Handle client requests (e.g. symbol history fetch)
            if data.get("action") == "get_history":
                sym = data.get("symbol", "BTCUSD").upper()
                candles = feed.cached_history(sym)
                if not candles:
                    candles = await feed.fetch_history(sym)
                await manager.send(ws, {
                    "type": "candle_history",
                    "symbol": sym,
                    "candles": candles,
                })
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        manager.disconnect(ws)
