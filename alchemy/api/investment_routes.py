"""
alchemy.api.investment_routes
================================
API routes for investment analytics, P&L segregation, portfolio metrics,
position sizing, and market sessions.

Endpoints:
  GET  /api/investment/pnl                — Segregated P&L report
  GET  /api/investment/pnl/daily          — Daily P&L time series
  GET  /api/investment/tax-report         — Indian tax-ready report
  POST /api/investment/trade              — Record a completed trade
  GET  /api/investment/portfolio           — Portfolio analytics (Sharpe, etc.)
  POST /api/investment/position-size      — Calculate position size
  GET  /api/investment/sessions           — Market session status
  GET  /api/investment/sessions/{exchange} — Single exchange session
  GET  /api/investment/stats              — Quick engine stats
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alchemy.auth.middleware import CurrentUser, get_current_user

router = APIRouter(prefix="/investment", tags=["investment"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RecordTradeRequest(BaseModel):
    symbol: str
    exchange: str
    strategy: str = "manual"
    asset_class: str = "crypto_spot"
    side: str = "BUY"
    entry_price: float
    exit_price: float
    quantity: float
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    slippage: float = 0.0
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)


class PositionSizeRequest(BaseModel):
    method: str = "half_kelly"
    capital: float = 10000.0
    entry_price: float
    stop_loss: float = 0.0
    win_rate: float = 0.5
    avg_win: float = 100.0
    avg_loss: float = 100.0
    risk_per_trade_pct: float = 2.0
    volatility: float = 0.0
    target_vol: float = 0.15
    max_position_pct: float = 25.0


# ── P&L Segregation ──────────────────────────────────────────────────────────

@router.get("/pnl")
async def pnl_report(
    group_by: str = Query("exchange", description="exchange|strategy|asset_class|symbol|side|tax_category|month|week"),
    period: Optional[str] = Query(None, description="today|week|month|quarter|year|all"),
    exchange: Optional[str] = None,
    strategy: Optional[str] = None,
    asset_class: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics.pnl_segregation import get_pnl_engine
    return get_pnl_engine().get_report(
        group_by=group_by,
        period=period,
        exchange=exchange,
        strategy=strategy,
        asset_class=asset_class,
    )


@router.get("/pnl/daily")
async def daily_pnl_series(
    days: int = Query(30, ge=1, le=365),
    exchange: Optional[str] = None,
    strategy: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics.pnl_segregation import get_pnl_engine
    return get_pnl_engine().get_daily_pnl_series(
        days=days, exchange=exchange, strategy=strategy,
    )


@router.get("/tax-report")
async def tax_report(
    financial_year: Optional[str] = Query(None, description="e.g. 2025-26"),
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics.pnl_segregation import get_pnl_engine
    return get_pnl_engine().get_tax_report(financial_year=financial_year)


@router.post("/trade")
async def record_trade(
    body: RecordTradeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    from datetime import datetime, timezone
    from alchemy.analytics.pnl_segregation import (
        AssetClass, CompletedTrade, get_pnl_engine,
    )

    trade = CompletedTrade(
        symbol=body.symbol,
        exchange=body.exchange,
        strategy=body.strategy,
        asset_class=AssetClass(body.asset_class),
        side=body.side,
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        quantity=body.quantity,
        entry_fee=body.entry_fee,
        exit_fee=body.exit_fee,
        slippage=body.slippage,
        notes=body.notes,
        tags=body.tags,
    )

    if body.entry_time:
        trade.entry_time = datetime.fromisoformat(body.entry_time)
    if body.exit_time:
        trade.exit_time = datetime.fromisoformat(body.exit_time)
    else:
        trade.exit_time = datetime.now(timezone.utc)

    get_pnl_engine().record_trade(trade)
    return {"ok": True, "trade": trade.to_dict()}


# ── Portfolio Analytics ───────────────────────────────────────────────────────

@router.get("/portfolio")
async def portfolio_metrics(
    initial_capital: float = Query(10000.0),
    period: Optional[str] = Query(None),
    exchange: Optional[str] = None,
    strategy: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics.pnl_segregation import get_pnl_engine
    from alchemy.analytics.portfolio_metrics import calculate_portfolio_metrics

    engine = get_pnl_engine()
    trades = engine._filter_trades(
        period=period, exchange=exchange, strategy=strategy,
    )

    metrics = calculate_portfolio_metrics(trades, initial_capital=initial_capital)
    return metrics.to_dict()


# ── Position Sizing ───────────────────────────────────────────────────────────

@router.post("/position-size")
async def position_size(
    body: PositionSizeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.risk.position_sizing import SizingMethod, calculate_position_size
    result = calculate_position_size(
        method=SizingMethod(body.method),
        capital=body.capital,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        win_rate=body.win_rate,
        avg_win=body.avg_win,
        avg_loss=body.avg_loss,
        risk_per_trade_pct=body.risk_per_trade_pct,
        volatility=body.volatility,
        target_vol=body.target_vol,
        max_position_pct=body.max_position_pct,
    )
    return result.to_dict()


# ── Market Sessions ───────────────────────────────────────────────────────────

@router.get("/sessions")
async def all_sessions(user: CurrentUser = Depends(get_current_user)):
    from alchemy.trading.session_manager import get_session_manager
    return get_session_manager().all_sessions_status()


@router.get("/sessions/{exchange}")
async def exchange_session(
    exchange: str,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.trading.session_manager import get_session_manager
    mgr = get_session_manager()
    info = mgr.next_open(exchange)
    info["should_trade"], info["reason"] = mgr.should_trade(exchange)
    return info


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def engine_stats(user: CurrentUser = Depends(get_current_user)):
    from alchemy.analytics.pnl_segregation import get_pnl_engine
    return get_pnl_engine().stats()
