"""
alchemy.analytics.portfolio_metrics
=====================================
Portfolio-level performance analytics.

Calculates:
  - Sharpe ratio, Sortino ratio
  - Max drawdown (depth, duration, recovery)
  - Win rate, average win/loss ratio
  - CAGR (Compound Annual Growth Rate)
  - Calmar ratio (CAGR / max drawdown)
  - Expectancy (expected $ per trade)
  - Consecutive wins/losses streak
  - Risk-adjusted return metrics

Works with PnLSegregationEngine's CompletedTrade list.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

RISK_FREE_RATE = 0.065   # 6.5% — India 10Y govt bond (approx)
TRADING_DAYS_YEAR = 252


@dataclass
class DrawdownInfo:
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    peak_value: float = 0.0
    trough_value: float = 0.0
    drawdown_duration_days: int = 0
    recovery_days: int = 0
    current_drawdown_pct: float = 0.0


@dataclass
class PortfolioMetrics:
    """Complete portfolio performance metrics."""
    # Returns
    total_return_pct: float = 0.0
    total_return_abs: float = 0.0
    cagr: float = 0.0

    # Risk-adjusted
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Drawdown
    drawdown: DrawdownInfo = None

    # Trade stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0

    # Streaks
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0
    current_streak_type: str = ""

    # Volume
    total_volume: float = 0.0
    total_fees: float = 0.0
    avg_holding_days: float = 0.0

    # Period
    first_trade_date: str = ""
    last_trade_date: str = ""
    active_days: int = 0

    def __post_init__(self):
        if self.drawdown is None:
            self.drawdown = DrawdownInfo()

    def to_dict(self) -> dict:
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "total_return_abs": round(self.total_return_abs, 2),
            "cagr": round(self.cagr, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown_pct": round(self.drawdown.max_drawdown_pct, 2),
            "max_drawdown_abs": round(self.drawdown.max_drawdown_abs, 2),
            "drawdown_duration_days": self.drawdown.drawdown_duration_days,
            "current_drawdown_pct": round(self.drawdown.current_drawdown_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "win_loss_ratio": round(self.win_loss_ratio, 2),
            "expectancy": round(self.expectancy, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_streak": self.current_streak,
            "current_streak_type": self.current_streak_type,
            "total_volume": round(self.total_volume, 2),
            "total_fees": round(self.total_fees, 2),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "first_trade_date": self.first_trade_date,
            "last_trade_date": self.last_trade_date,
            "active_days": self.active_days,
        }


def calculate_portfolio_metrics(
    trades: list,
    initial_capital: float = 10000.0,
    risk_free_rate: float = RISK_FREE_RATE,
) -> PortfolioMetrics:
    """
    Calculate comprehensive portfolio metrics from a list of CompletedTrade objects.
    """
    if not trades:
        return PortfolioMetrics()

    m = PortfolioMetrics()
    m.total_trades = len(trades)

    # Sort by exit time
    sorted_trades = sorted(
        trades,
        key=lambda t: t.exit_time or t.entry_time or date.today()
    )

    # Basic trade stats
    wins = [t for t in sorted_trades if t.net_pnl > 0]
    losses = [t for t in sorted_trades if t.net_pnl <= 0]
    m.winning_trades = len(wins)
    m.losing_trades = len(losses)
    m.win_rate = (m.winning_trades / m.total_trades) * 100 if m.total_trades else 0

    m.avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0
    m.avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0
    m.win_loss_ratio = abs(m.avg_win / m.avg_loss) if m.avg_loss != 0 else float("inf")

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    m.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    m.expectancy = (m.win_rate / 100 * m.avg_win) + ((1 - m.win_rate / 100) * m.avg_loss)

    # Total return
    m.total_return_abs = sum(t.net_pnl for t in sorted_trades)
    m.total_return_pct = (m.total_return_abs / initial_capital) * 100

    # Volume & fees
    m.total_volume = sum(t.entry_price * t.quantity for t in sorted_trades)
    m.total_fees = sum(t.total_fees for t in sorted_trades)
    m.avg_holding_days = (
        sum(t.holding_days for t in sorted_trades) / m.total_trades
    )

    # Dates
    if sorted_trades[0].exit_time:
        m.first_trade_date = sorted_trades[0].exit_time.strftime("%Y-%m-%d")
    if sorted_trades[-1].exit_time:
        m.last_trade_date = sorted_trades[-1].exit_time.strftime("%Y-%m-%d")
    if sorted_trades[0].exit_time and sorted_trades[-1].exit_time:
        m.active_days = (sorted_trades[-1].exit_time - sorted_trades[0].exit_time).days

    # Equity curve + drawdown
    equity = [initial_capital]
    daily_returns = []
    for t in sorted_trades:
        new_eq = equity[-1] + t.net_pnl
        daily_returns.append(t.net_pnl / equity[-1] if equity[-1] != 0 else 0)
        equity.append(new_eq)

    m.drawdown = _calculate_drawdown(equity)

    # CAGR
    if m.active_days > 0 and equity[-1] > 0 and initial_capital > 0:
        years = m.active_days / 365.25
        if years > 0:
            m.cagr = ((equity[-1] / initial_capital) ** (1 / years) - 1) * 100

    # Sharpe ratio
    if daily_returns:
        avg_return = sum(daily_returns) / len(daily_returns)
        std_return = _std(daily_returns)
        if std_return > 0:
            # Annualize: assume ~1 trade per day
            m.sharpe_ratio = (avg_return - risk_free_rate / TRADING_DAYS_YEAR) / std_return * math.sqrt(TRADING_DAYS_YEAR)

    # Sortino ratio (downside deviation only)
    downside_returns = [r for r in daily_returns if r < 0]
    if downside_returns:
        downside_std = _std(downside_returns)
        avg_return = sum(daily_returns) / len(daily_returns)
        if downside_std > 0:
            m.sortino_ratio = (avg_return - risk_free_rate / TRADING_DAYS_YEAR) / downside_std * math.sqrt(TRADING_DAYS_YEAR)

    # Calmar ratio
    if m.drawdown.max_drawdown_pct > 0:
        m.calmar_ratio = m.cagr / m.drawdown.max_drawdown_pct

    # Streaks
    m.max_consecutive_wins, m.max_consecutive_losses, m.current_streak, m.current_streak_type = (
        _calculate_streaks(sorted_trades)
    )

    return m


def _calculate_drawdown(equity: list[float]) -> DrawdownInfo:
    """Calculate drawdown from equity curve."""
    dd = DrawdownInfo()
    if len(equity) < 2:
        return dd

    peak = equity[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_peak = peak
    max_dd_trough = peak

    for i, val in enumerate(equity):
        if val > peak:
            peak = val
            peak_idx = i

        current_dd = (peak - val) / peak if peak > 0 else 0
        if current_dd > max_dd:
            max_dd = current_dd
            max_dd_peak = peak
            max_dd_trough = val
            dd.drawdown_duration_days = i - peak_idx

    dd.max_drawdown_pct = max_dd * 100
    dd.max_drawdown_abs = max_dd_peak - max_dd_trough
    dd.peak_value = max_dd_peak
    dd.trough_value = max_dd_trough

    # Current drawdown
    current_peak = max(equity)
    dd.current_drawdown_pct = ((current_peak - equity[-1]) / current_peak * 100
                               if current_peak > 0 else 0)

    return dd


def _calculate_streaks(trades: list) -> tuple[int, int, int, str]:
    """Calculate win/loss streaks."""
    max_wins = max_losses = 0
    current = 0
    current_type = ""

    for t in trades:
        if t.net_pnl > 0:
            if current_type == "win":
                current += 1
            else:
                current = 1
                current_type = "win"
            max_wins = max(max_wins, current)
        else:
            if current_type == "loss":
                current += 1
            else:
                current = 1
                current_type = "loss"
            max_losses = max(max_losses, current)

    return max_wins, max_losses, current, current_type


def _std(values: list[float]) -> float:
    """Standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)
