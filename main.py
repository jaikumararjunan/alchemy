"""Emotion Engine v2 — entry point."""
from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AppConfig
from src.api.routes import router
from src.engine.analyzer import EmotionAnalyzer
from src.storage.db import AnalysisStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    cfg = AppConfig()
    cfg.validate()

    app = FastAPI(
        title="Emotion Engine v2",
        description="Alternate Claude-powered crypto sentiment analyzer",
        version="2.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = cfg
    app.state.analyzer = EmotionAnalyzer(cfg.claude)
    app.state.store = AnalysisStore(cfg.storage.db_path)

    app.include_router(router, prefix="/api/v2")

    @app.get("/")
    async def root():
        return {"service": "emotion-engine-v2", "status": "running"}

    logger.info("Emotion Engine v2 ready — model=%s port=%s", cfg.claude.model, cfg.server.port)
    return app


app = create_app()

if __name__ == "__main__":
    cfg = AppConfig()
    uvicorn.run(
        "main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=cfg.server.debug,
        log_level="info",
    )
