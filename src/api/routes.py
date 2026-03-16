"""FastAPI routes for Emotion Engine v2 + real-time trading dashboard."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

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

logger = logging.getLogger(__name__)

router = APIRouter()


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
