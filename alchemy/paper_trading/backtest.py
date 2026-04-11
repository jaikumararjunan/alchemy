"""
alchemy.paper_trading.backtest
================================
Backtesting engine — run strategies against historical data.

Strategies:
  - SMA Crossover (fast/slow moving average)
  - RSI Mean Reversion (buy oversold, sell overbought)
  - Bollinger Band Breakout
  - Combined (SMA + RSI confirmation)

Usage::

    result = await run_backtest(BacktestConfig(
        user_id="user123",
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1h",
        start_date="2025-01-01",
        initial_capital=100000,
    ))
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import structlog

from alchemy.paper_trading import BacktestConfig, BacktestResult

log = structlog.get_logger(__name__)

# ── Storage for user backtest results ─────────────────────────────────────────
_results: dict[str, list[BacktestResult]] = {}  # user_id → list[BacktestResult]


def get_user_backtests(user_id: str) -> list[dict]:
    """Get all backtest results for a user."""
    return [r.to_dict() for r in _results.get(user_id, [])]


def get_backtest_by_id(user_id: str, backtest_id: str) -> Optional[BacktestResult]:
    for r in _results.get(user_id, []):
        if r.id == backtest_id:
            return r
    return None


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def run_backtest(config: BacktestConfig) -> BacktestResult:
    """
    Run a backtest with the given configuration.
    Fetches historical data from Binance and simulates trading.
    """
    result = BacktestResult(config=config, started_at=datetime.now(timezone.utc))
    result.status = "running"

    try:
        # Fetch historical candles
        candles = await _fetch_candles(config.symbol, config.interval,
                                       config.start_date, config.end_date)
        if not candles or len(candles) < config.slow_period + 10:
            result.status = "failed"
            result.error = f"Insufficient data: got {len(candles)} candles, need at least {config.slow_period + 10}"
            return result

        result.candles_processed = len(candles)

        # Run strategy
        strategy_fn = _STRATEGIES.get(config.strategy)
        if not strategy_fn:
            result.status = "failed"
            result.error = f"Unknown strategy: {config.strategy}. Available: {list(_STRATEGIES.keys())}"
            return result

        signals = strategy_fn(candles, config)

        # Simulate trades
        _simulate(candles, signals, config, result)

        result.status = "completed"
        result.completed_at = datetime.now(timezone.utc)

        # Store result
        if config.user_id not in _results:
            _results[config.user_id] = []
        _results[config.user_id].append(result)
        # Keep last 20 backtests per user
        if len(_results[config.user_id]) > 20:
            _results[config.user_id] = _results[config.user_id][-20:]

        log.info("backtest.completed", user_id=config.user_id,
                 strategy=config.strategy, trades=result.total_trades,
                 return_pct=round(result.total_return_pct, 2))

    except Exception as e:
        result.status = "failed"
        result.error = str(e)
        log.error("backtest.failed", error=str(e))

    return result


# ── Data Fetching ─────────────────────────────────────────────────────────────

async def _fetch_candles(
    symbol: str, interval: str,
    start_date: str, end_date: str,
) -> list[dict]:
    """Fetch historical candles from Binance REST API."""
    import httpx

    url = "https://api.binance.com/api/v3/klines"
    all_candles = []
    limit = 1000

    # Convert dates to timestamps
    start_ts = int(datetime.fromisoformat(start_date).timestamp() * 1000) if start_date else None
    end_ts = int(datetime.fromisoformat(end_date).timestamp() * 1000) if end_date else None

    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }
    if start_ts:
        params["startTime"] = start_ts
    if end_ts:
        params["endTime"] = end_ts

    async with httpx.AsyncClient(timeout=30) as client:
        # Paginate through all data
        for _ in range(10):  # Max 10 pages = 10,000 candles
            resp = await client.get(url, params=params)
            data = resp.json()

            if not isinstance(data, list) or not data:
                break

            for k in data:
                all_candles.append({
                    "timestamp": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "date": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
                })

            if len(data) < limit:
                break

            # Next page
            params["startTime"] = data[-1][0] + 1
            if end_ts and params["startTime"] > end_ts:
                break

    return all_candles


# ── Strategy Implementations ─────────────────────────────────────────────────

def _calc_sma(closes: list[float], period: int) -> list[Optional[float]]:
    result = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1:i + 1]) / period
    return result


def _calc_rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result[period] = 100
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(0, diff)
        loss = max(0, -diff)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 100
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
    return result


def _calc_bb(closes: list[float], period: int = 20, std_mult: float = 2.0):
    upper, lower, mid = [None]*len(closes), [None]*len(closes), [None]*len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        m = sum(window) / period
        var = sum((x - m) ** 2 for x in window) / period
        std = math.sqrt(var)
        mid[i] = m
        upper[i] = m + std_mult * std
        lower[i] = m - std_mult * std
    return upper, lower, mid


def strategy_sma_crossover(candles: list[dict], config: BacktestConfig) -> list[str]:
    """SMA Crossover: BUY when fast > slow, SELL when fast < slow."""
    closes = [c["close"] for c in candles]
    fast = _calc_sma(closes, config.fast_period)
    slow = _calc_sma(closes, config.slow_period)

    signals = ["hold"] * len(candles)
    for i in range(1, len(candles)):
        if fast[i] is None or slow[i] is None or fast[i-1] is None or slow[i-1] is None:
            continue
        if fast[i-1] <= slow[i-1] and fast[i] > slow[i]:
            signals[i] = "buy"
        elif fast[i-1] >= slow[i-1] and fast[i] < slow[i]:
            signals[i] = "sell"
    return signals


def strategy_rsi(candles: list[dict], config: BacktestConfig) -> list[str]:
    """RSI Mean Reversion: BUY when RSI < oversold, SELL when RSI > overbought."""
    closes = [c["close"] for c in candles]
    rsi = _calc_rsi(closes, config.rsi_period)

    signals = ["hold"] * len(candles)
    for i in range(1, len(candles)):
        if rsi[i] is None or rsi[i-1] is None:
            continue
        if rsi[i-1] >= config.rsi_oversold and rsi[i] < config.rsi_oversold:
            signals[i] = "buy"
        elif rsi[i-1] <= config.rsi_overbought and rsi[i] > config.rsi_overbought:
            signals[i] = "sell"
    return signals


def strategy_bollinger(candles: list[dict], config: BacktestConfig) -> list[str]:
    """Bollinger Band: BUY at lower band touch, SELL at upper band touch."""
    closes = [c["close"] for c in candles]
    upper, lower, mid = _calc_bb(closes)

    signals = ["hold"] * len(candles)
    for i in range(1, len(candles)):
        if lower[i] is None:
            continue
        if candles[i]["low"] <= lower[i] and candles[i]["close"] > lower[i]:
            signals[i] = "buy"
        elif candles[i]["high"] >= upper[i] and candles[i]["close"] < upper[i]:
            signals[i] = "sell"
    return signals


def strategy_combined(candles: list[dict], config: BacktestConfig) -> list[str]:
    """Combined: SMA crossover confirmed by RSI."""
    closes = [c["close"] for c in candles]
    fast = _calc_sma(closes, config.fast_period)
    slow = _calc_sma(closes, config.slow_period)
    rsi = _calc_rsi(closes, config.rsi_period)

    signals = ["hold"] * len(candles)
    for i in range(1, len(candles)):
        if fast[i] is None or slow[i] is None or rsi[i] is None:
            continue
        # BUY: fast crosses above slow AND RSI < 60 (not overbought)
        if fast[i-1] <= slow[i-1] and fast[i] > slow[i] and rsi[i] < 60:
            signals[i] = "buy"
        # SELL: fast crosses below slow AND RSI > 40 (not oversold)
        elif fast[i-1] >= slow[i-1] and fast[i] < slow[i] and rsi[i] > 40:
            signals[i] = "sell"
    return signals


_STRATEGIES = {
    "sma_crossover": strategy_sma_crossover,
    "rsi_mean_reversion": strategy_rsi,
    "bollinger_band": strategy_bollinger,
    "combined_sma_rsi": strategy_combined,
}

STRATEGY_INFO = {
    "sma_crossover": {
        "name": "SMA Crossover",
        "description": "Buys when fast moving average crosses above slow MA, sells on cross below. Classic trend-following strategy.",
        "parameters": ["fast_period", "slow_period"],
        "best_for": "Trending markets (crypto, forex)",
    },
    "rsi_mean_reversion": {
        "name": "RSI Mean Reversion",
        "description": "Buys when RSI drops below oversold level (30), sells when RSI rises above overbought (70). Works in ranging markets.",
        "parameters": ["rsi_period", "rsi_overbought", "rsi_oversold"],
        "best_for": "Range-bound markets, mean reversion",
    },
    "bollinger_band": {
        "name": "Bollinger Band Breakout",
        "description": "Buys when price touches lower band and bounces, sells at upper band. Combines volatility with mean reversion.",
        "parameters": ["fast_period"],
        "best_for": "Volatile markets with defined ranges",
    },
    "combined_sma_rsi": {
        "name": "Combined SMA + RSI",
        "description": "SMA crossover confirmed by RSI filter. Reduces false signals by requiring momentum confirmation.",
        "parameters": ["fast_period", "slow_period", "rsi_period"],
        "best_for": "Balanced approach for any market condition",
    },
}


# ── Trade Simulation ──────────────────────────────────────────────────────────

def _simulate(
    candles: list[dict],
    signals: list[str],
    config: BacktestConfig,
    result: BacktestResult,
) -> None:
    """Simulate trades based on strategy signals."""
    capital = config.initial_capital
    cash = capital
    position = None  # {"side", "entry_price", "quantity", "entry_idx"}
    equity_curve = []
    trades = []
    total_fees = 0.0

    for i, (candle, signal) in enumerate(zip(candles, signals)):
        price = candle["close"]

        # Check stop-loss / take-profit on open positions
        if position:
            hit_sl = (position["side"] == "long" and candle["low"] <= position.get("stop_loss", 0))
            hit_tp = (position["side"] == "long" and candle["high"] >= position.get("take_profit", float("inf")))

            if hit_sl:
                exit_price = position["stop_loss"]
                pnl = (exit_price - position["entry_price"]) * position["quantity"]
                fee = exit_price * position["quantity"] * (config.commission_pct / 100)
                total_fees += fee
                cash += exit_price * position["quantity"]
                trades.append({
                    "entry_date": candles[position["entry_idx"]]["date"],
                    "exit_date": candle["date"],
                    "side": position["side"],
                    "entry_price": round(position["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "quantity": round(position["quantity"], 8),
                    "gross_pnl": round(pnl, 2),
                    "fee": round(fee, 2),
                    "net_pnl": round(pnl - fee, 2),
                    "return_pct": round((pnl / (position["entry_price"] * position["quantity"])) * 100, 2),
                    "exit_reason": "stop_loss",
                })
                position = None
                continue

            if hit_tp:
                exit_price = position["take_profit"]
                pnl = (exit_price - position["entry_price"]) * position["quantity"]
                fee = exit_price * position["quantity"] * (config.commission_pct / 100)
                total_fees += fee
                cash += exit_price * position["quantity"]
                trades.append({
                    "entry_date": candles[position["entry_idx"]]["date"],
                    "exit_date": candle["date"],
                    "side": position["side"],
                    "entry_price": round(position["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "quantity": round(position["quantity"], 8),
                    "gross_pnl": round(pnl, 2),
                    "fee": round(fee, 2),
                    "net_pnl": round(pnl - fee, 2),
                    "return_pct": round((pnl / (position["entry_price"] * position["quantity"])) * 100, 2),
                    "exit_reason": "take_profit",
                })
                position = None
                continue

        # Process signals
        if signal == "buy" and position is None:
            # Open long position
            position_value = cash * (config.position_size_pct / 100)
            qty = position_value / price
            fee = position_value * (config.commission_pct / 100)
            total_fees += fee
            slippage = price * (config.slippage_pct / 100)
            entry = price + slippage
            cash -= position_value

            sl = entry * (1 - config.stop_loss_pct / 100) if config.stop_loss_pct > 0 else 0
            tp = entry * (1 + config.take_profit_pct / 100) if config.take_profit_pct > 0 else float("inf")

            position = {
                "side": "long",
                "entry_price": entry,
                "quantity": qty,
                "entry_idx": i,
                "stop_loss": sl,
                "take_profit": tp,
            }

        elif signal == "sell" and position and position["side"] == "long":
            # Close long position
            slippage = price * (config.slippage_pct / 100)
            exit_price = price - slippage
            pnl = (exit_price - position["entry_price"]) * position["quantity"]
            fee = exit_price * position["quantity"] * (config.commission_pct / 100)
            total_fees += fee
            cash += exit_price * position["quantity"]

            trades.append({
                "entry_date": candles[position["entry_idx"]]["date"],
                "exit_date": candle["date"],
                "side": position["side"],
                "entry_price": round(position["entry_price"], 2),
                "exit_price": round(exit_price, 2),
                "quantity": round(position["quantity"], 8),
                "gross_pnl": round(pnl, 2),
                "fee": round(fee, 2),
                "net_pnl": round(pnl - fee, 2),
                "return_pct": round((pnl / (position["entry_price"] * position["quantity"])) * 100, 2),
                "exit_reason": "signal",
            })
            position = None

        # Record equity
        pos_value = 0
        if position:
            pos_value = price * position["quantity"]
        portfolio_value = cash + pos_value

        # Sample equity curve (every N candles to keep it manageable)
        sample_rate = max(1, len(candles) // 200)
        if i % sample_rate == 0 or i == len(candles) - 1:
            equity_curve.append({
                "date": candle["date"],
                "value": round(portfolio_value, 2),
                "cash": round(cash, 2),
            })

    # Close any remaining position at last price
    if position:
        last_price = candles[-1]["close"]
        pnl = (last_price - position["entry_price"]) * position["quantity"]
        fee = last_price * position["quantity"] * (config.commission_pct / 100)
        total_fees += fee
        cash += last_price * position["quantity"]
        trades.append({
            "entry_date": candles[position["entry_idx"]]["date"],
            "exit_date": candles[-1]["date"],
            "side": position["side"],
            "entry_price": round(position["entry_price"], 2),
            "exit_price": round(last_price, 2),
            "quantity": round(position["quantity"], 8),
            "gross_pnl": round(pnl, 2),
            "fee": round(fee, 2),
            "net_pnl": round(pnl - fee, 2),
            "return_pct": round((pnl / (position["entry_price"] * position["quantity"])) * 100, 2),
            "exit_reason": "end_of_data",
        })

    # Calculate metrics
    result.trades = trades
    result.equity_curve = equity_curve
    result.total_trades = len(trades)
    result.total_fees = total_fees

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    result.winning_trades = len(wins)
    result.losing_trades = len(losses)
    result.win_rate = (len(wins) / len(trades) * 100) if trades else 0

    result.avg_win = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0
    result.avg_loss = sum(t["net_pnl"] for t in losses) / len(losses) if losses else 0

    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    final_value = cash
    result.total_pnl = final_value - capital
    result.total_return_pct = ((final_value - capital) / capital) * 100

    # Max drawdown
    peak = capital
    max_dd = 0
    for eq in equity_curve:
        val = eq["value"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd
    result.max_drawdown_pct = max_dd

    # Sharpe ratio (simplified)
    if trades:
        returns = [t["return_pct"] / 100 for t in trades]
        avg_ret = sum(returns) / len(returns)
        if len(returns) > 1:
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1))
            if std_ret > 0:
                result.sharpe_ratio = (avg_ret / std_ret) * math.sqrt(252)
