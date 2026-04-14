"""
alchemy.api.capital_engine_routes
====================================
API for Capital Preservation Engine.

Endpoints:
  GET  /api/capital-engine/summary     — Full capital state
  POST /api/capital-engine/configure   — Update capital config
  POST /api/capital-engine/evaluate    — Pre-trade evaluation
  POST /api/capital-engine/record      — Record closed trade
  POST /api/capital-engine/reset       — Reset capital state
  GET  /api/capital-engine/drawdown    — Drawdown status + circuit breaker
  GET  /api/capital-engine/reinvestment — Reinvestment history
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser
from alchemy.trading.capital_engine import get_capital_engine, CapitalConfig

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/capital-engine", tags=["capital-engine"])


class EvaluateRequest(BaseModel):
    symbol: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float = 0
    strategy: str = "auto"


class RecordTradeRequest(BaseModel):
    symbol: str
    gross_pnl: float
    fee: float = 0
    strategy: str = ""
    position_size: float = 0


class ConfigureRequest(BaseModel):
    reinvest_mode: Optional[str] = None
    reinvest_cadence: Optional[str] = None
    base_risk_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    profit_lock_pct: Optional[float] = None
    drawdown_pause_pct: Optional[float] = None
    max_daily_trades: Optional[int] = None
    max_daily_loss_pct: Optional[float] = None
    min_risk_reward: Optional[float] = None
    min_confidence: Optional[float] = None
    consecutive_loss_pause: Optional[int] = None


@router.get("/summary")
async def capital_summary(user: CurrentUser = Depends(get_current_user)):
    """Get full capital state including drawdown, P&L, reinvestment status."""
    engine = get_capital_engine(user.user_id)
    return engine.summary()


@router.post("/evaluate")
async def evaluate_trade(req: EvaluateRequest,
                          user: CurrentUser = Depends(get_current_user)):
    """
    Pre-trade evaluation: checks drawdown, daily limits, R:R,
    confidence, and calculates risk-based position size.
    """
    engine = get_capital_engine(user.user_id)
    decision = engine.evaluate_trade(
        symbol=req.symbol, confidence=req.confidence,
        entry_price=req.entry_price, stop_loss=req.stop_loss,
        take_profit=req.take_profit, strategy=req.strategy,
    )
    return decision.to_dict()


@router.post("/record")
async def record_trade(req: RecordTradeRequest,
                        user: CurrentUser = Depends(get_current_user)):
    """Record a closed trade — updates capital state, reinvestment, drawdown."""
    engine = get_capital_engine(user.user_id)
    result = engine.record_trade(
        symbol=req.symbol, gross_pnl=req.gross_pnl,
        fee=req.fee, strategy=req.strategy,
        position_size=req.position_size,
    )
    return {"ok": True, "trade": result, "summary": engine.summary()}


@router.post("/configure")
async def configure_capital(req: ConfigureRequest,
                              user: CurrentUser = Depends(get_current_user)):
    """Update capital management configuration."""
    engine = get_capital_engine(user.user_id)
    cfg = engine.config

    if req.reinvest_mode is not None:
        if req.reinvest_mode not in ("conservative", "moderate", "aggressive", "full_compound", "preserve"):
            raise HTTPException(400, "Invalid reinvest mode")
        cfg.reinvest_mode = req.reinvest_mode
    if req.reinvest_cadence is not None:
        cfg.reinvest_cadence = req.reinvest_cadence
    if req.base_risk_pct is not None:
        cfg.base_risk_pct = max(0.1, min(5.0, req.base_risk_pct))
    if req.max_position_pct is not None:
        cfg.max_position_pct = max(1.0, min(50.0, req.max_position_pct))
    if req.profit_lock_pct is not None:
        cfg.profit_lock_pct = max(0, min(100, req.profit_lock_pct))
    if req.drawdown_pause_pct is not None:
        cfg.drawdown_pause_pct = max(5, min(50, req.drawdown_pause_pct))
    if req.max_daily_trades is not None:
        cfg.max_daily_trades = max(1, min(100, req.max_daily_trades))
    if req.max_daily_loss_pct is not None:
        cfg.max_daily_loss_pct = max(0.5, min(20, req.max_daily_loss_pct))
    if req.min_risk_reward is not None:
        cfg.min_risk_reward = max(0.5, min(10, req.min_risk_reward))
    if req.min_confidence is not None:
        cfg.min_confidence = max(0.1, min(1.0, req.min_confidence))
    if req.consecutive_loss_pause is not None:
        cfg.consecutive_loss_pause = max(2, min(20, req.consecutive_loss_pause))

    from alchemy.trading.capital_engine import REINVEST_RATIOS
    engine._reinvest_ratio = REINVEST_RATIOS.get(cfg.reinvest_mode, 0.5)
    engine._save_state()

    return {"ok": True, "config": {
        "reinvest_mode": cfg.reinvest_mode,
        "base_risk_pct": cfg.base_risk_pct,
        "max_position_pct": cfg.max_position_pct,
        "profit_lock_pct": cfg.profit_lock_pct,
        "drawdown_pause_pct": cfg.drawdown_pause_pct,
        "max_daily_trades": cfg.max_daily_trades,
        "min_risk_reward": cfg.min_risk_reward,
    }}


@router.post("/reset")
async def reset_capital(body: dict = {},
                         user: CurrentUser = Depends(get_current_user)):
    """Reset capital state to initial balance."""
    engine = get_capital_engine(user.user_id)
    engine.reset(body.get("initial_capital"))
    return {"ok": True, "summary": engine.summary()}


@router.get("/drawdown")
async def drawdown_status(user: CurrentUser = Depends(get_current_user)):
    """Get current drawdown status and circuit breaker mode."""
    engine = get_capital_engine(user.user_id)
    s = engine.state
    return {
        "current_drawdown_pct": round(s.current_drawdown_pct, 2),
        "max_drawdown_pct": round(s.max_drawdown_pct, 2),
        "peak_equity": round(s.peak_equity, 2),
        "current_equity": round(s.current_equity, 2),
        "drawdown_mode": s.drawdown_mode,
        "thresholds": {
            "warning": engine.config.drawdown_warning_pct,
            "reduce": engine.config.drawdown_reduce_pct,
            "pause": engine.config.drawdown_pause_pct,
            "kill": engine.config.drawdown_kill_pct,
        },
    }


@router.get("/reinvestment")
async def reinvestment_info(user: CurrentUser = Depends(get_current_user)):
    """Get reinvestment configuration and history."""
    engine = get_capital_engine(user.user_id)
    s = engine.state
    return {
        "mode": engine.config.reinvest_mode,
        "ratio": engine._reinvest_ratio,
        "cadence": engine.config.reinvest_cadence,
        "reinvested_total": round(s.reinvested_total, 2),
        "pending_profit": round(s.pending_profit, 2),
        "locked_reserve": round(s.locked_reserve, 2),
        "cycle_count": s.cycle_count,
        "last_cycle_date": s.last_cycle_date,
    }
