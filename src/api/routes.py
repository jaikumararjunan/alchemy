"""FastAPI routes for Emotion Engine v2."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from config import AppConfig
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

# Singletons injected via app.state in main.py
def _get_analyzer(request) -> EmotionAnalyzer:  # type: ignore[no-untyped-def]
    return request.app.state.analyzer


def _get_store(request) -> AnalysisStore:  # type: ignore[no-untyped-def]
    return request.app.state.store


def _get_config(request) -> AppConfig:  # type: ignore[no-untyped-def]
    return request.app.state.config


@router.get("/health", response_model=HealthResponse)
async def health(request) -> HealthResponse:  # type: ignore[no-untyped-def]
    store: AnalysisStore = _get_store(request)
    cfg: AppConfig = _get_config(request)
    return HealthResponse(
        status="ok",
        model=cfg.claude.model,
        total_analyses=store.count(),
    )


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
        return AnalyzeResponse(success=True, result=result, analysis_id=analysis_id)
    except Exception as exc:
        logger.error("Analysis failed: %s", exc, exc_info=True)
        return AnalyzeResponse(success=False, error=str(exc))


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
