"""
alchemy.analytics.portfolio
============================
Portfolio analytics wrapping pyfolio (QuantInsti fork).
Source: https://github.com/QuantInsti/pyfolio

Provides institutional-grade tear sheets, risk metrics, and
live portfolio monitoring for the Alchemy dashboard.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False
    import structlog
    structlog.get_logger(__name__).warning("portfolio.pandas_missing",
        hint="pip install pandas numpy")
import structlog

log = structlog.get_logger(__name__)


class PortfolioAnalytics:
    """
    Wraps pyfolio to provide performance analytics for Alchemy strategies.

    Usage::

        analytics = PortfolioAnalytics(returns=my_strategy_returns)
        metrics = analytics.compute_metrics()
        analytics.save_tear_sheet("reports/strategy_v1.png")
    """

    def __init__(
        self,
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
        positions: Optional[pd.DataFrame] = None,
        transactions: Optional[pd.DataFrame] = None,
        strategy_name: str = "Alchemy Strategy",
    ) -> None:
        """
        Args:
            returns: Daily strategy returns (decimal, e.g. 0.012 not 1.2%).
                     Must have a DatetimeIndex.
            benchmark_returns: Optional benchmark (e.g. NIFTY 50) returns.
            positions: Optional pd.DataFrame of daily positions per asset.
            transactions: Optional pd.DataFrame of individual transactions.
        """
        self.returns = returns.dropna()
        self.benchmark_returns = benchmark_returns
        self.positions = positions
        self.transactions = transactions
        self.strategy_name = strategy_name

        if not isinstance(self.returns.index, pd.DatetimeIndex):
            raise ValueError("returns.index must be a DatetimeIndex")

    # ── Metrics ───────────────────────────────────────────────────────────────

    def compute_metrics(self) -> dict[str, float]:
        """
        Compute all key performance metrics using pyfolio timeseries.

        Returns dict with: sharpe, sortino, calmar, max_drawdown, annual_return,
                           annual_volatility, omega, tail_ratio, var_5pct
        """
        try:
            from pyfolio import timeseries as ts

            metrics = {
                "annual_return":     round(ts.annual_return(self.returns), 4),
                "annual_volatility": round(ts.annual_volatility(self.returns), 4),
                "sharpe_ratio":      round(ts.sharpe_ratio(self.returns), 4),
                "sortino_ratio":     round(ts.sortino_ratio(self.returns), 4),
                "calmar_ratio":      round(ts.calmar_ratio(self.returns), 4),
                "max_drawdown":      round(ts.max_drawdown(self.returns), 4),
                "omega_ratio":       round(ts.omega_ratio(self.returns), 4),
                "tail_ratio":        round(ts.tail_ratio(self.returns), 4),
                "var_5pct":          round(ts.value_at_risk(self.returns), 4),
                "n_trading_days":    len(self.returns),
                "total_return":      round((1 + self.returns).prod() - 1, 4),
            }
            if self.benchmark_returns is not None:
                alpha, beta = ts.alpha_beta(self.returns, self.benchmark_returns)
                metrics["alpha"] = round(alpha, 4)
                metrics["beta"]  = round(beta, 4)

            log.info("portfolio.metrics", strategy=self.strategy_name, **{
                k: v for k, v in metrics.items() if k in (
                    "sharpe_ratio", "max_drawdown", "annual_return")
            })
            return metrics

        except ImportError:
            log.warning("pyfolio.not_installed", msg="Falling back to manual metrics")
            return self._fallback_metrics()

    # ── Tear Sheets ───────────────────────────────────────────────────────────

    def create_full_tear_sheet(self) -> None:
        """Generate and display full pyfolio tear sheet in Jupyter / interactive mode."""
        try:
            import pyfolio as pf
            pf.create_full_tear_sheet(
                self.returns,
                benchmark_rets=self.benchmark_returns,
                positions=self.positions,
                transactions=self.transactions,
            )
        except ImportError:
            log.error("pyfolio.import_error")
            raise

    def save_tear_sheet(self, output_path: str | Path) -> Path:
        """
        Generate a simple returns tear sheet and save as PNG.

        Args:
            output_path: File path to save the PNG.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        fig = plt.figure(figsize=(14, 8))
        gs = gridspec.GridSpec(2, 2, figure=fig)

        ax1 = fig.add_subplot(gs[0, :])
        ax2 = fig.add_subplot(gs[1, 0])
        ax3 = fig.add_subplot(gs[1, 1])

        # Cumulative returns
        cum = (1 + self.returns).cumprod()
        ax1.plot(cum.index, cum.values, color="#2E75B6", linewidth=1.5,
                 label=self.strategy_name)
        if self.benchmark_returns is not None:
            bm_cum = (1 + self.benchmark_returns.reindex(cum.index).fillna(0)).cumprod()
            ax1.plot(bm_cum.index, bm_cum.values, color="#E53935",
                     linewidth=1.0, alpha=0.7, linestyle="--", label="Benchmark")
        ax1.set_title("Cumulative Returns", fontsize=12, fontweight="bold")
        ax1.legend()
        ax1.grid(alpha=0.3)

        # Drawdown
        roll_max = cum.cummax()
        drawdown = (cum - roll_max) / roll_max
        ax2.fill_between(drawdown.index, drawdown.values, 0,
                         alpha=0.6, color="#E53935")
        ax2.set_title("Drawdown", fontsize=11, fontweight="bold")
        ax2.grid(alpha=0.3)

        # Return distribution
        ax3.hist(self.returns.values * 100, bins=50, color="#2E75B6",
                 alpha=0.7, edgecolor="white")
        ax3.axvline(0, color="black", linestyle="--", linewidth=0.8)
        ax3.set_title("Daily Return Distribution (%)", fontsize=11, fontweight="bold")
        ax3.grid(alpha=0.3)

        metrics = self._fallback_metrics()
        fig.suptitle(
            f"{self.strategy_name}  |  "
            f"Sharpe: {metrics['sharpe_ratio']:.2f}  "
            f"Max DD: {metrics['max_drawdown']:.1%}  "
            f"Ann. Return: {metrics['annual_return']:.1%}",
            fontsize=11, y=1.01,
        )
        fig.tight_layout()

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        log.info("portfolio.tear_sheet_saved", path=str(out))
        return out

    # ── Fallback (no pyfolio) ─────────────────────────────────────────────────

    def _fallback_metrics(self) -> dict[str, float]:
        import numpy as np
        r = self.returns
        ann = r.mean() * 252
        vol = r.std() * np.sqrt(252)
        cum = (1 + r).cumprod()
        roll_max = cum.cummax()
        dd = ((cum - roll_max) / roll_max).min()
        sharpe = ann / vol if vol > 0 else 0.0
        return {
            "annual_return":     round(ann, 4),
            "annual_volatility": round(vol, 4),
            "sharpe_ratio":      round(sharpe, 4),
            "sortino_ratio":     0.0,
            "calmar_ratio":      round(ann / abs(dd), 4) if dd < 0 else 0.0,
            "max_drawdown":      round(dd, 4),
            "omega_ratio":       0.0,
            "tail_ratio":        0.0,
            "var_5pct":          round(float(r.quantile(0.05)), 4),
            "n_trading_days":    len(r),
            "total_return":      round(float(cum.iloc[-1] - 1), 4),
        }
