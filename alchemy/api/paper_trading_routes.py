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
from datetime import datetime, timezone

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

    # Check advanced orders (OCO, trailing stops)
    try:
        from alchemy.api.advanced_orders import check_advanced_orders
        adv_events = check_advanced_orders(user.user_id, body.prices)
        events.extend(adv_events)
    except Exception:
        pass

    # Send push + email notification for SL/TP triggers
    if events:
        try:
            from alchemy.api.push_routes import notify_sl_tp_trigger
            from alchemy.notifications.email_service import send_trade_alert_email
            for event in events:
                parts = event.split(": ")
                trigger = "take_profit" if "TAKE_PROFIT" in event else "stop_loss"
                sym_price = parts[1] if len(parts) > 1 else ""
                symbol = sym_price.split(" @ ")[0] if " @ " in sym_price else ""
                price = float(sym_price.split(" @ ")[1]) if " @ " in sym_price else 0
                # Push notification
                await notify_sl_tp_trigger(user.user_id, symbol, trigger, price, 0)
                # Email notification
                try:
                    send_trade_alert_email(user.email, trigger, symbol, "close", price)
                except Exception:
                    pass
        except Exception:
            pass

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


# ── Equity Curve ──────────────────────────────────────────────────────────────

@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """Get portfolio equity curve data points."""
    from alchemy.services.price_stream import get_equity_curve
    points = get_equity_curve(user.user_id, days=days)
    return {"points": points, "count": len(points)}


# ── Live Prices (from WebSocket cache) ────────────────────────────────────────

@router.get("/live-prices")
async def get_live_prices(user: CurrentUser = Depends(get_current_user)):
    """Get latest cached prices from Binance WebSocket stream."""
    from alchemy.services.price_stream import get_latest_prices
    prices = get_latest_prices()
    return {"prices": prices, "source": "binance_ws" if prices else "cache_empty"}


# ── Position Sizing Calculator ────────────────────────────────────────────────

@router.post("/position-size")
async def calculate_position_size(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Calculate optimal position size based on risk parameters.
    Body: { account_size, risk_pct, entry_price, stop_loss_price }
    """
    account = body.get("account_size", 0)
    risk_pct = body.get("risk_pct", 1.0)
    entry = body.get("entry_price", 0)
    sl = body.get("stop_loss_price", 0)

    if not account or not entry or not sl:
        raise HTTPException(400, "account_size, entry_price, stop_loss_price required")

    risk_amount = account * (risk_pct / 100)
    price_diff = abs(entry - sl)
    if price_diff == 0:
        raise HTTPException(400, "Entry and SL cannot be the same price")

    quantity = risk_amount / price_diff
    position_value = quantity * entry
    max_loss = risk_amount
    risk_reward = body.get("take_profit_price", 0)
    rr_ratio = abs(body.get("take_profit_price", entry) - entry) / price_diff if price_diff else 0

    return {
        "quantity": round(quantity, 6),
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "max_loss": round(max_loss, 2),
        "risk_reward_ratio": round(rr_ratio, 2),
        "position_pct": round((position_value / account) * 100, 2) if account else 0,
    }


# ── Strategy Performance Comparison ───────────────────────────────────────────

@router.get("/strategy-comparison")
async def strategy_comparison(user: CurrentUser = Depends(get_current_user)):
    """Compare performance across different trading strategies."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)

    strategies = {}
    for trade in portfolio.trade_log:
        strat = trade.get("strategy", "manual")
        if strat not in strategies:
            strategies[strat] = {"trades": 0, "wins": 0, "losses": 0,
                                  "total_pnl": 0, "total_return": 0, "pnls": []}
        s = strategies[strat]
        s["trades"] += 1
        pnl = trade.get("net_pnl", 0)
        s["total_pnl"] += pnl
        s["total_return"] += trade.get("return_pct", 0)
        s["pnls"].append(pnl)
        if pnl > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    result = []
    for name, s in strategies.items():
        avg_return = s["total_return"] / s["trades"] if s["trades"] else 0
        win_rate = (s["wins"] / s["trades"] * 100) if s["trades"] else 0
        avg_win = sum(p for p in s["pnls"] if p > 0) / max(s["wins"], 1)
        avg_loss = sum(p for p in s["pnls"] if p <= 0) / max(s["losses"], 1)
        profit_factor = abs(avg_win * s["wins"]) / abs(avg_loss * s["losses"]) if s["losses"] and avg_loss else 0

        result.append({
            "strategy": name,
            "trades": s["trades"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": round(win_rate, 1),
            "total_pnl": round(s["total_pnl"], 2),
            "avg_return_pct": round(avg_return, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
        })

    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return {"strategies": result, "total_closed": len(portfolio.trade_log)}


# ── Tax Report Export (CSV) ───────────────────────────────────────────────────

@router.get("/tax-export")
async def export_tax_report(
    financial_year: str = Query("2025-26"),
    user: CurrentUser = Depends(get_current_user),
):
    """Export trade history as CSV for Indian tax filing."""
    from alchemy.paper_trading.engine import get_paper_engine
    from datetime import datetime
    portfolio = get_paper_engine().get_portfolio(user.user_id)

    trades = portfolio.trade_log
    if not trades:
        return {"ok": False, "message": "No closed trades to export"}

    lines = ["Symbol,Side,Entry Price,Exit Price,Quantity,Gross P&L,Fee,Net P&L,Return %,Strategy,Holding Period,Tax Category,Closed At"]
    total_pnl = 0
    total_tax = 0

    for t in trades:
        pnl = t.get("net_pnl", 0)
        total_pnl += pnl
        # Indian tax: crypto = 30% flat, equity STCG = 15%, LTCG = 10%
        tax_cat = "Crypto 30%"
        tax = abs(pnl) * 0.30 if pnl > 0 else 0
        total_tax += tax

        holding = t.get("holding_time", "")
        lines.append(
            f"{t.get('symbol','')},{t.get('side','')},{t.get('entry_price',0)},"
            f"{t.get('exit_price',0)},{t.get('quantity',0)},{t.get('gross_pnl',0)},"
            f"{t.get('fee',0)},{pnl},{t.get('return_pct',0)}%,"
            f"{t.get('strategy','')},{holding},{tax_cat},{t.get('closed_at','')}"
        )

    lines.append("")
    lines.append(f"TOTAL,,,,,,{round(total_pnl,2)},,,,,,")
    lines.append(f"Estimated Tax ({financial_year}),,,,,,{round(total_tax,2)},,,,,,")

    from fastapi.responses import PlainTextResponse
    csv_content = "\n".join(lines)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=alchemy_tax_{financial_year}.csv"}
    )


# ── AI Trade Recommendations ─────────────────────────────────────────────────

@router.get("/ai-recommendations")
async def get_ai_recommendations(user: CurrentUser = Depends(get_current_user)):
    """Get AI-powered trade recommendations with reasoning."""
    from alchemy.paper_trading.engine import get_paper_engine
    import random

    portfolio = get_paper_engine().get_portfolio(user.user_id)
    positions = portfolio.positions
    recommendations = []

    # Analyze current positions
    for sym, pos in positions.items():
        pnl_pct = pos.unrealized_pct
        rec = {
            "symbol": sym,
            "current_side": pos.side.value,
            "entry_price": round(pos.avg_entry_price, 2),
            "current_price": round(pos.current_price, 2),
            "unrealized_pnl": round(pos.unrealized_pnl, 2),
            "return_pct": round(pnl_pct, 2),
            "quantity": pos.quantity,
        }

        # Generate recommendation based on P&L
        if pnl_pct > 3:
            rec["action"] = "TAKE_PROFIT"
            rec["confidence"] = 0.75
            rec["reasoning"] = f"Position up {pnl_pct:.1f}%. Consider taking partial profits (50%) to lock gains. Set trailing stop at entry price to protect remaining."
        elif pnl_pct < -5:
            rec["action"] = "CUT_LOSS"
            rec["confidence"] = 0.80
            rec["reasoning"] = f"Position down {abs(pnl_pct):.1f}%. Exceeds recommended 5% max loss. Consider closing to preserve capital for better setups."
        elif pnl_pct < -2:
            rec["action"] = "TIGHTEN_STOP"
            rec["confidence"] = 0.65
            rec["reasoning"] = f"Position down {abs(pnl_pct):.1f}%. Move stop loss closer to limit further downside. Current risk outweighs reward."
        else:
            rec["action"] = "HOLD"
            rec["confidence"] = 0.60
            rec["reasoning"] = f"Position within normal range ({pnl_pct:+.1f}%). No action needed. Monitor for breakout above entry + 2%."

        recommendations.append(rec)

    # Portfolio-level recommendations
    cash_pct = (portfolio.cash_balance / portfolio.portfolio_value * 100) if portfolio.portfolio_value else 100
    portfolio_rec = {
        "type": "portfolio",
        "cash_pct": round(cash_pct, 1),
        "positions_count": len(positions),
        "diversification": "low" if len(positions) <= 2 else "moderate" if len(positions) <= 5 else "good",
    }

    if cash_pct < 10:
        portfolio_rec["warning"] = "Very low cash reserve. Consider closing weakest position to free up capital."
    elif cash_pct > 80:
        portfolio_rec["suggestion"] = "High cash allocation. Consider deploying capital into trending assets."

    return {
        "recommendations": recommendations,
        "portfolio_summary": portfolio_rec,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Portfolio Heatmap Data ────────────────────────────────────────────────────

@router.get("/heatmap")
async def portfolio_heatmap(user: CurrentUser = Depends(get_current_user)):
    """Get portfolio data formatted for treemap/heatmap visualization."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    positions = portfolio.positions

    if not positions:
        return {"cells": [], "total_value": portfolio.portfolio_value}

    cells = []
    for sym, pos in positions.items():
        value = pos.current_price * pos.quantity
        pnl = pos.unrealized_pnl
        pnl_pct = pos.unrealized_pct
        cells.append({
            "symbol": sym.replace("USDT", ""),
            "full_symbol": sym,
            "side": pos.side.value,
            "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "quantity": pos.quantity,
            "entry": round(pos.avg_entry_price, 2),
            "current": round(pos.current_price, 2),
            "weight_pct": round(value / portfolio.portfolio_value * 100, 2) if portfolio.portfolio_value else 0,
        })

    # Add cash
    cash_pct = portfolio.cash_balance / portfolio.portfolio_value * 100 if portfolio.portfolio_value else 100
    cells.append({
        "symbol": "CASH", "full_symbol": "CASH", "side": "cash",
        "value": round(portfolio.cash_balance, 2), "pnl": 0, "pnl_pct": 0,
        "quantity": 0, "entry": 0, "current": 0,
        "weight_pct": round(cash_pct, 2),
    })

    cells.sort(key=lambda x: abs(x["value"]), reverse=True)
    return {"cells": cells, "total_value": round(portfolio.portfolio_value, 2)}


# ── Correlation Matrix ────────────────────────────────────────────────────────

@router.get("/correlation")
async def correlation_matrix(
    symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT"),
    interval: str = Query("1h"),
    limit: int = Query(100, ge=20, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    """Calculate correlation matrix between symbols using recent price data."""
    import httpx

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    price_series = {}

    for sym in sym_list:
        try:
            resp = httpx.get(
                f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}",
                timeout=10)
            klines = resp.json()
            closes = [float(k[4]) for k in klines]  # close price
            if len(closes) >= 20:
                # Calculate returns
                returns = [(closes[i] - closes[i-1]) / closes[i-1]
                           for i in range(1, len(closes))]
                price_series[sym] = returns
        except Exception:
            continue

    if len(price_series) < 2:
        return {"matrix": {}, "symbols": list(price_series.keys()), "error": "Need at least 2 symbols"}

    # Calculate correlation matrix
    syms = list(price_series.keys())
    n = len(syms)
    matrix = {}

    for i in range(n):
        matrix[syms[i]] = {}
        for j in range(n):
            if i == j:
                matrix[syms[i]][syms[j]] = 1.0
            else:
                a, b = price_series[syms[i]], price_series[syms[j]]
                min_len = min(len(a), len(b))
                a, b = a[:min_len], b[:min_len]
                mean_a = sum(a) / len(a)
                mean_b = sum(b) / len(b)
                cov = sum((a[k] - mean_a) * (b[k] - mean_b) for k in range(min_len)) / min_len
                std_a = (sum((x - mean_a)**2 for x in a) / len(a)) ** 0.5
                std_b = (sum((x - mean_b)**2 for x in b) / len(b)) ** 0.5
                corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0
                matrix[syms[i]][syms[j]] = round(corr, 4)

    # Diversification score
    off_diag = [abs(matrix[syms[i]][syms[j]]) for i in range(n) for j in range(n) if i != j]
    avg_corr = sum(off_diag) / len(off_diag) if off_diag else 0
    diversification = "excellent" if avg_corr < 0.3 else "good" if avg_corr < 0.5 else "moderate" if avg_corr < 0.7 else "poor"

    return {
        "matrix": matrix,
        "symbols": syms,
        "avg_correlation": round(avg_corr, 4),
        "diversification": diversification,
    }


@router.get("/trade-insights")
async def trade_insights(user: CurrentUser = Depends(get_current_user)):
    """AI-powered trade journal analysis — patterns, streaks, improvement suggestions."""
    from alchemy.services.trade_insights import analyze_trades
    engine = get_paper_engine()
    p = engine.get_portfolio(user.user_id)
    return analyze_trades(p.trade_log)
