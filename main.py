"""Alchemy — Emotion Engine v2 + real-time trading dashboard entry point."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import AppConfig
from src.api.price_feed import feed
from src.api.routes import router
from src.engine.analyzer import EmotionAnalyzer
from src.storage.db import AnalysisStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    cfg = AppConfig()
    cfg.validate()

    app = FastAPI(
        title="Alchemy Trading Dashboard",
        description="Real-time crypto trading dashboard with AI sentiment analysis",
        version="2.1.0",
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

    # Serve static assets (JS, CSS, images etc.)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Dashboard root
    @app.get("/")
    async def dashboard():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"service": "alchemy", "status": "running", "dashboard": "/static/index.html"}

    # Background price feed
    @app.on_event("startup")
    async def _start_feed():
        asyncio.create_task(feed.run())
        logger.info("PriceFeed background task started")

    @app.on_event("shutdown")
    async def _stop_feed():
        feed.stop()

    logger.info(
        "Alchemy ready — model=%s port=%s dashboard=http://localhost:%s",
        cfg.claude.model,
        cfg.server.port,
        cfg.server.port,
    )
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
