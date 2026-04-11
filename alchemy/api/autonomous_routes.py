"""
alchemy.api.autonomous_routes
===============================
REST API endpoints for autonomous trading engine.

Endpoints:
  POST /autonomous/start    — Start the autonomous trading loop
  POST /autonomous/stop     — Stop the autonomous trading loop
  GET  /autonomous/status   — Current engine status
  GET  /autonomous/history  — Trade signal/execution history
  POST /autonomous/configure — Update engine configuration
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser

router = APIRouter(prefix="/autonomous", tags=["autonomous-trading"])


class ConfigureRequest(BaseModel):
    symbols: Optional[list[str]] = None
    strategies: Optional[list[str]] = None
    interval_seconds: Optional[int] = None
    auto_execute: Optional[bool] = None
    exchange: Optional[str] = None
    timeframe: Optional[str] = None


@router.post("/start")
async def start_autonomous(
    body: Optional[ConfigureRequest] = None,
    user: CurrentUser = Depends(get_current_user),
):
    """Start the autonomous trading engine."""
    from alchemy.trading.autonomous import get_autonomous_engine

    engine = get_autonomous_engine()

    # Apply configuration if provided
    if body:
        engine.configure(
            symbols=body.symbols,
            strategies=body.strategies,
            interval_seconds=body.interval_seconds,
            auto_execute=body.auto_execute,
            exchange=body.exchange,
            timeframe=body.timeframe,
        )

    # Get the WebSocket broadcast function
    try:
        from alchemy.api.app import manager
        ws_broadcast = manager.broadcast
    except ImportError:
        ws_broadcast = None

    result = await engine.start(ws_broadcast=ws_broadcast)
    engine._user_id = user.user_id  # Link trades to user's paper portfolio
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "Failed to start"))
    return result


@router.post("/stop")
async def stop_autonomous(
    user: CurrentUser = Depends(get_current_user),
):
    """Stop the autonomous trading engine."""
    from alchemy.trading.autonomous import get_autonomous_engine

    engine = get_autonomous_engine()
    result = await engine.stop()
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "Failed to stop"))
    return result


@router.get("/status")
async def autonomous_status(
    user: CurrentUser = Depends(get_current_user),
):
    """Get the current autonomous engine status."""
    from alchemy.trading.autonomous import get_autonomous_engine
    return get_autonomous_engine().get_status()


@router.get("/history")
async def autonomous_history(
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    """Get trade signal/execution history."""
    from alchemy.trading.autonomous import get_autonomous_engine
    return {"trades": get_autonomous_engine().get_history(limit=limit)}


@router.post("/configure")
async def configure_autonomous(
    body: ConfigureRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update engine configuration (while running or idle)."""
    from alchemy.trading.autonomous import get_autonomous_engine

    engine = get_autonomous_engine()
    engine.configure(
        symbols=body.symbols,
        strategies=body.strategies,
        interval_seconds=body.interval_seconds,
        auto_execute=body.auto_execute,
        exchange=body.exchange,
        timeframe=body.timeframe,
    )
    return engine.get_status()
