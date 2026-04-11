"""
alchemy.api.paper_trading_routes
==================================
REST API for paper trading and backtesting.

Paper Trading:
  GET  /api/paper/portfolio              — Get your paper portfolio
  POST /api/paper/reset                  — Reset portfolio to starting balance
  POST /api/paper/order                  — Place a paper trade
  POST /api/paper/close                  — Close a position
  POST /api/paper/update-prices          — Update prices (triggers SL/TP)
  GET  /api/paper/orders                 — Order history
  GET  /api/paper/trades                 — Completed trade log
  GET  /api/paper/leaderboard            — Leaderboard

Backtesting:
  GET  /api/paper/backtest/strategies    — List available strategies
  POST /api/paper/backtest/run           — Run a backtest
  GET  /api/paper/backtest/results       — Get your backtest results
  GET  /api/paper/backtest/results/{id}  — Get specific backtest
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alchemy.auth.middleware import CurrentUser, get_current_user

router = APIRouter(prefix="/paper", tags=["paper-trading"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., gt=0, description="Amount to trade")
    current_price: float = Field(..., gt=0, description="Current market price")
    order_type: str = Field("market", description="market, limit, or stop_loss")
    limit_price: float = Field(0, description="Limit price (for limit orders)")
    stop_loss: float = Field(0, description="Stop loss price")
    take_profit: float = Field(0, description="Take profit price")
    strategy: str = Field("manual", description="Strategy name")
    notes: str = Field("", description="Trade notes")


class ClosePositionRequest(BaseModel):
    symbol: str
    current_price: float = Field(..., gt=0)
    quantity: float = Field(0, description="0 = close entire position")
    notes: str = ""


class UpdatePricesRequest(BaseModel):
    prices: dict[str, float] = Field(..., description="Symbol → current price mapping")


class ResetPortfolioRequest(BaseModel):
    initial_balance: float = Field(0, description="0 = use default ($100,000)")


class BacktestRequest(BaseModel):
    strategy: str = Field("sma_crossover", description="Strategy to test")
    symbol: str = Field("BTCUSDT", description="Trading pair")
    interval: str = Field("1h", description="Candle interval: 1m, 5m, 15m, 1h, 4h, 1d")
    start_date: str = Field("", description="Start date (YYYY-MM-DD)")
    end_date: str = Field("", description="End date (YYYY-MM-DD)")
    initial_capital: float = Field(100000, description="Starting capital")
    position_size_pct: float = Field(10, description="% of capital per trade")
    stop_loss_pct: float = Field(2, description="Stop loss %")
    take_profit_pct: float = Field(4, description="Take profit %")
    commission_pct: float = Field(0.1, description="Commission % per trade")
    fast_period: int = Field(9, description="Fast MA period")
    slow_period: int = Field(21, description="Slow MA period")
    rsi_period: int = Field(14, description="RSI period")
    rsi_overbought: float = Field(70, description="RSI overbought level")
    rsi_oversold: float = Field(30, description="RSI oversold level")


# ── Paper Trading Endpoints ──────────────────────────────────────────────────

@router.get("/portfolio")
async def get_portfolio(user: CurrentUser = Depends(get_current_user)):
    """Get your paper trading portfolio summary."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    return portfolio.summary()


@router.post("/reset")
async def reset_portfolio(
    body: ResetPortfolioRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Reset your paper portfolio to starting balance."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().reset_portfolio(
        user.user_id,
        initial_balance=body.initial_balance,
    )
    return {
        "ok": True,
        "message": f"Portfolio reset to ${portfolio.initial_balance:,.2f}",
        "portfolio": portfolio.summary(),
    }


@router.post("/order")
async def place_order(
    body: PlaceOrderRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Place a paper trade order.

    For market orders: fills immediately at current_price ± simulated slippage.
    For limit orders: stored as pending, fills when price reaches limit.
    """
    from alchemy.paper_trading.engine import get_paper_engine
    order = get_paper_engine().place_order(
        user_id=user.user_id,
        symbol=body.symbol,
        side=body.side,
        quantity=body.quantity,
        current_price=body.current_price,
        order_type=body.order_type,
        limit_price=body.limit_price,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        strategy=body.strategy,
        notes=body.notes,
    )

    if order.status.value == "rejected":
        raise HTTPException(400, {
            "code": "order_rejected",
            "message": order.notes,
            "order": order.to_dict(),
        })

    return {
        "ok": True,
        "message": f"{'Filled' if order.status.value == 'filled' else 'Pending'}: "
                   f"{body.side.upper()} {body.quantity} {body.symbol} @ ${order.filled_price or body.current_price:,.2f}",
        "order": order.to_dict(),
    }


@router.post("/close")
async def close_position(
    body: ClosePositionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Close an open paper position (fully or partially)."""
    from alchemy.paper_trading.engine import get_paper_engine
    order = get_paper_engine().close_position(
        user_id=user.user_id,
        symbol=body.symbol,
        current_price=body.current_price,
        quantity=body.quantity,
        notes=body.notes,
    )

    if not order:
        raise HTTPException(404, f"No open position for {body.symbol}")

    return {
        "ok": True,
        "message": f"Position closed: {body.symbol} @ ${body.current_price:,.2f}",
        "order": order.to_dict(),
    }


@router.post("/update-prices")
async def update_prices(
    body: UpdatePricesRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update current prices for your positions. Triggers stop-loss/take-profit if hit."""
    from alchemy.paper_trading.engine import get_paper_engine
    events = get_paper_engine().update_prices(user.user_id, body.prices)
    return {
        "ok": True,
        "events": events,
        "message": f"Prices updated. {len(events)} triggers fired." if events else "Prices updated.",
    }


@router.get("/orders")
async def get_orders(
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
):
    """Get your paper trade order history."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    orders = [o.to_dict() for o in portfolio.order_history[-limit:]]
    return {"total": len(portfolio.order_history), "orders": orders}


@router.get("/trades")
async def get_trades(
    limit: int = Query(50, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    """Get your completed paper trade log with P&L."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    trades = portfolio.trade_log[-limit:]
    return {
        "total": len(portfolio.trade_log),
        "realized_pnl": round(sum(t.get("net_pnl", 0) for t in portfolio.trade_log), 2),
        "trades": trades,
    }


@router.get("/leaderboard")
async def get_leaderboard(user: CurrentUser = Depends(get_current_user)):
    """Get paper trading leaderboard."""
    from alchemy.paper_trading.engine import get_paper_engine
    return get_paper_engine().get_leaderboard()


# ── Backtesting Endpoints ────────────────────────────────────────────────────

@router.get("/backtest/strategies")
async def list_strategies(user: CurrentUser = Depends(get_current_user)):
    """List available backtesting strategies with descriptions."""
    from alchemy.paper_trading.backtest import STRATEGY_INFO
    return {
        "strategies": STRATEGY_INFO,
        "intervals": ["1m", "5m", "15m", "1h", "4h", "1d"],
        "defaults": {
            "initial_capital": 100000,
            "position_size_pct": 10,
            "stop_loss_pct": 2,
            "take_profit_pct": 4,
            "commission_pct": 0.1,
            "fast_period": 9,
            "slow_period": 21,
            "rsi_period": 14,
        },
    }


@router.post("/backtest/run")
async def run_backtest(
    body: BacktestRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Run a backtest with historical data.

    Fetches candles from Binance, applies the selected strategy,
    simulates trades with realistic slippage and fees.
    Returns full trade log, equity curve, and performance metrics.
    """
    from alchemy.paper_trading import BacktestConfig
    from alchemy.paper_trading.backtest import run_backtest as _run

    config = BacktestConfig(
        user_id=user.user_id,
        strategy=body.strategy,
        symbol=body.symbol,
        interval=body.interval,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        position_size_pct=body.position_size_pct,
        stop_loss_pct=body.stop_loss_pct,
        take_profit_pct=body.take_profit_pct,
        commission_pct=body.commission_pct,
        fast_period=body.fast_period,
        slow_period=body.slow_period,
        rsi_period=body.rsi_period,
        rsi_overbought=body.rsi_overbought,
        rsi_oversold=body.rsi_oversold,
    )

    result = await _run(config)

    if result.status == "failed":
        raise HTTPException(400, {
            "code": "backtest_failed",
            "message": result.error,
        })

    return result.to_dict()


@router.get("/backtest/results")
async def get_backtest_results(user: CurrentUser = Depends(get_current_user)):
    """Get all your backtest results."""
    from alchemy.paper_trading.backtest import get_user_backtests
    results = get_user_backtests(user.user_id)
    return {
        "total": len(results),
        "results": [
            {
                "id": r["id"],
                "strategy": r["config"].get("strategy"),
                "symbol": r["config"].get("symbol"),
                "status": r["status"],
                "total_return_pct": r["performance"]["total_return_pct"],
                "total_trades": r["performance"]["total_trades"],
                "win_rate": r["performance"]["win_rate"],
                "sharpe_ratio": r["performance"]["sharpe_ratio"],
                "max_drawdown_pct": r["performance"]["max_drawdown_pct"],
                "completed_at": r["completed_at"],
            }
            for r in results
        ],
    }


@router.get("/backtest/results/{backtest_id}")
async def get_backtest_detail(
    backtest_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Get detailed backtest result including trades and equity curve."""
    from alchemy.paper_trading.backtest import get_backtest_by_id
    result = get_backtest_by_id(user.user_id, backtest_id)
    if not result:
        raise HTTPException(404, "Backtest not found")
    return result.to_dict()
