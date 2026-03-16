"""
Performance Metrics Calculator.

Computes institutional-grade metrics from a list of trade PnLs and equity curve.

Metrics:
  Total return            — simple % gain/loss on initial balance
  Annualized return       — CAGR (assuming 365 trading days)
  Sharpe ratio            — excess return / total volatility (annualised, rf=0)
  Sortino ratio           — excess return / downside volatility
  Calmar ratio            — annualized return / max drawdown
  Max drawdown (%)        — peak-to-trough equity decline
  Win rate                — % of trades that were profitable
  Profit factor           — gross profit / gross loss
  Average win / loss      — mean PnL of winning vs losing trades
  Expectancy              — average expected PnL per trade
  Recovery factor         — total net profit / max drawdown $
  Best / worst trade      — single best and worst PnL
  Consecutive wins/losses — longest run
"""

import math
import statistics
from dataclasses import dataclass
from typing import List


@dataclass
class PerformanceMetrics:
    # Returns
    initial_balance: float
    final_balance: float
    total_return_pct: float
    annualized_return_pct: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown_pct: float
    max_drawdown_usd: float
    avg_drawdown_pct: float
    recovery_factor: float

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_usd: float

    avg_win_usd: float
    avg_loss_usd: float
    avg_win_pct: float
    avg_loss_pct: float

    best_trade_usd: float
    worst_trade_usd: float
    best_trade_pct: float
    worst_trade_pct: float

    # Streaks
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Timing
    total_bars: int
    trading_days: float
    avg_trade_duration_bars: float

    def to_dict(self) -> dict:
        return {
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.final_balance, 2),
            "total_return_pct": round(self.total_return_pct, 3),
            "annualized_return_pct": round(self.annualized_return_pct, 3),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "avg_drawdown_pct": round(self.avg_drawdown_pct, 3),
            "recovery_factor": round(self.recovery_factor, 3),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "profit_factor": round(self.profit_factor, 3),
            "expectancy_usd": round(self.expectancy_usd, 4),
            "avg_win_usd": round(self.avg_win_usd, 4),
            "avg_loss_usd": round(self.avg_loss_usd, 4),
            "avg_win_pct": round(self.avg_win_pct, 3),
            "avg_loss_pct": round(self.avg_loss_pct, 3),
            "best_trade_usd": round(self.best_trade_usd, 4),
            "worst_trade_usd": round(self.worst_trade_usd, 4),
            "best_trade_pct": round(self.best_trade_pct, 3),
            "worst_trade_pct": round(self.worst_trade_pct, 3),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "total_bars": self.total_bars,
            "trading_days": round(self.trading_days, 1),
            "avg_trade_duration_bars": round(self.avg_trade_duration_bars, 1),
        }

    def summary(self) -> str:
        return (
            f"Return: {self.total_return_pct:+.2f}% | "
            f"Ann: {self.annualized_return_pct:+.2f}% | "
            f"Sharpe: {self.sharpe_ratio:.2f} | "
            f"Sortino: {self.sortino_ratio:.2f} | "
            f"MaxDD: {self.max_drawdown_pct:.2f}% | "
            f"WinRate: {self.win_rate_pct:.1f}% | "
            f"PF: {self.profit_factor:.2f} | "
            f"Trades: {self.total_trades}"
        )


class PerformanceCalculator:
    """Calculates all performance metrics from backtest trade records and equity curve."""

    def __init__(self, risk_free_rate: float = 0.0, periods_per_year: int = 8760):
        """
        risk_free_rate: annualized risk-free rate (0 = assume 0%)
        periods_per_year: for 1h bars = 8760; 1d bars = 365; 5m = 105120
        """
        self.rf = risk_free_rate
        self.ppy = periods_per_year

    def calculate(
        self,
        equity_curve: List[float],  # portfolio value at each bar
        trade_pnls_usd: List[float],  # net PnL per completed trade
        trade_pnls_pct: List[float],  # % PnL per completed trade
        trade_durations: List[int],  # duration in bars per trade
        initial_balance: float,
        total_bars: int,
    ) -> PerformanceMetrics:

        final_balance = equity_curve[-1] if equity_curve else initial_balance

        # ── Returns ──────────────────────────────────────────────────────────
        total_return = (final_balance - initial_balance) / initial_balance * 100
        trading_days = total_bars / 24.0  # assuming 1h bars
        if trading_days > 0 and final_balance > 0:
            ann_return = (
                (final_balance / initial_balance) ** (365.0 / trading_days) - 1
            ) * 100
        else:
            ann_return = 0.0

        # ── Sharpe / Sortino ─────────────────────────────────────────────────
        if len(equity_curve) >= 2:
            bar_returns = [
                (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                for i in range(1, len(equity_curve))
                if equity_curve[i - 1] > 0
            ]
            if len(bar_returns) >= 2:
                mean_r = statistics.mean(bar_returns)
                std_r = statistics.stdev(bar_returns)
                rf_bar = (1 + self.rf) ** (1 / self.ppy) - 1
                sharpe = (
                    (mean_r - rf_bar) / std_r * math.sqrt(self.ppy)
                    if std_r > 0
                    else 0.0
                )
                down_r = [r for r in bar_returns if r < rf_bar]
                down_std = statistics.stdev(down_r) if len(down_r) >= 2 else std_r
                sortino = (
                    (mean_r - rf_bar) / down_std * math.sqrt(self.ppy)
                    if down_std > 0
                    else 0.0
                )
            else:
                sharpe = sortino = 0.0
        else:
            sharpe = sortino = 0.0

        # ── Drawdown ─────────────────────────────────────────────────────────
        max_dd_pct, max_dd_usd, avg_dd, recovery = self._drawdown(
            equity_curve, initial_balance
        )
        calmar = (ann_return / max_dd_pct) if max_dd_pct > 0 else 0.0

        # ── Trade stats ───────────────────────────────────────────────────────
        wins = [p for p in trade_pnls_usd if p > 0]
        losses = [p for p in trade_pnls_usd if p <= 0]
        win_pcts = [p for p in trade_pnls_pct if p > 0]
        loss_pcts = [p for p in trade_pnls_pct if p <= 0]

        n = len(trade_pnls_usd)
        win_rate = len(wins) / n * 100 if n > 0 else 0.0
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        pf = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (999.0 if gross_profit > 0 else 0.0)
        )
        expectancy = statistics.mean(trade_pnls_usd) if trade_pnls_usd else 0.0

        avg_win = statistics.mean(wins) if wins else 0.0
        avg_loss = statistics.mean(losses) if losses else 0.0
        avg_win_pct = statistics.mean(win_pcts) if win_pcts else 0.0
        avg_loss_pct = statistics.mean(loss_pcts) if loss_pcts else 0.0

        best_usd = max(trade_pnls_usd) if trade_pnls_usd else 0.0
        worst_usd = min(trade_pnls_usd) if trade_pnls_usd else 0.0
        best_pct = max(trade_pnls_pct) if trade_pnls_pct else 0.0
        worst_pct = min(trade_pnls_pct) if trade_pnls_pct else 0.0

        # ── Streaks ───────────────────────────────────────────────────────────
        max_cw, max_cl = self._streaks(trade_pnls_usd)

        avg_dur = statistics.mean(trade_durations) if trade_durations else 0.0
        net_profit = final_balance - initial_balance
        recovery_f = net_profit / max_dd_usd if max_dd_usd > 0 else 0.0

        return PerformanceMetrics(
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return_pct=round(total_return, 4),
            annualized_return_pct=round(ann_return, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            calmar_ratio=round(calmar, 4),
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_usd=round(max_dd_usd, 4),
            avg_drawdown_pct=round(avg_dd, 4),
            recovery_factor=round(recovery_f, 4),
            total_trades=n,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=round(win_rate, 4),
            profit_factor=round(pf, 4),
            expectancy_usd=round(expectancy, 6),
            avg_win_usd=round(avg_win, 6),
            avg_loss_usd=round(avg_loss, 6),
            avg_win_pct=round(avg_win_pct, 4),
            avg_loss_pct=round(avg_loss_pct, 4),
            best_trade_usd=round(best_usd, 6),
            worst_trade_usd=round(worst_usd, 6),
            best_trade_pct=round(best_pct, 4),
            worst_trade_pct=round(worst_pct, 4),
            max_consecutive_wins=max_cw,
            max_consecutive_losses=max_cl,
            total_bars=total_bars,
            trading_days=round(trading_days, 2),
            avg_trade_duration_bars=round(avg_dur, 2),
        )

    @staticmethod
    def _drawdown(equity: List[float], initial: float):
        if not equity:
            return 0.0, 0.0, 0.0, 0.0
        peak = initial
        max_dd_pct = 0.0
        max_dd_usd = 0.0
        dd_list = []
        for v in equity:
            if v > peak:
                peak = v
            dd_usd = peak - v
            dd_pct = dd_usd / peak * 100 if peak > 0 else 0.0
            dd_list.append(dd_pct)
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_usd = dd_usd
        avg_dd = statistics.mean(dd_list) if dd_list else 0.0
        return max_dd_pct, max_dd_usd, avg_dd, 0.0

    @staticmethod
    def _streaks(pnls: List[float]):
        max_cw = max_cl = cw = cl = 0
        for p in pnls:
            if p > 0:
                cw += 1
                cl = 0
                max_cw = max(max_cw, cw)
            else:
                cl += 1
                cw = 0
                max_cl = max(max_cl, cl)
        return max_cw, max_cl
