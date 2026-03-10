"""
Strategy Parameter Optimizer.

Performs a grid-search over stop-loss %, take-profit %, leverage, and
position-size combinations, running a full BacktestEngine simulation for
each point and ranking by Sharpe ratio (or any chosen metric).

Usage::

    optimizer = StrategyOptimizer(config)
    result = optimizer.run(candles, symbol="BTCUSD", timeframe="1h",
                           initial_balance=10_000)
    print(result.best.summary())

The search space is deliberately compact by default (≤ 200 iterations) so
the API endpoint responds in a few seconds.  Pass a custom ``grid`` dict to
expand or narrow the search.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from src.backtest.backtester import BacktestEngine, BacktestResult
from src.backtest.performance import PerformanceMetrics
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Default search grid ───────────────────────────────────────────────────────

DEFAULT_GRID: Dict[str, List] = {
    "stop_loss_pct":    [1.0, 1.5, 2.0, 2.5, 3.0],
    "take_profit_pct":  [2.5, 3.5, 4.5, 6.0, 8.0],
    "leverage":         [3, 5, 7],
    "position_size_pct": [3.0, 5.0, 7.0],   # % of initial_balance
}

# Quick grid for smoke-testing (max ~20 combos)
QUICK_GRID: Dict[str, List] = {
    "stop_loss_pct":    [1.5, 2.0, 2.5],
    "take_profit_pct":  [3.5, 4.5, 6.0],
    "leverage":         [5],
    "position_size_pct": [5.0],
}


# ── Result data class ─────────────────────────────────────────────────────────

@dataclass
class OptimizationResult:
    """Output of one StrategyOptimizer.run() call."""
    symbol: str
    timeframe: str
    total_combinations: int
    valid_combinations: int          # had at least 1 trade
    sort_metric: str
    results: List[Dict[str, Any]]    # sorted, best first; each entry has params + metrics
    best_params: Dict[str, Any]
    best_metrics: Dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_combinations": self.total_combinations,
            "valid_combinations": self.valid_combinations,
            "sort_metric": self.sort_metric,
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "results": self.results[:50],   # cap API response at top-50
        }


# ── Optimizer ─────────────────────────────────────────────────────────────────

class StrategyOptimizer:
    """Grid-search optimizer for BacktestEngine parameters."""

    def __init__(self, config):
        self.config = config

    def run(
        self,
        candles: List[Dict],
        symbol: str = "BTCUSD",
        timeframe: str = "1h",
        initial_balance: float = 10_000.0,
        grid: Optional[Dict[str, List]] = None,
        sort_metric: str = "sharpe_ratio",
        warmup_bars: int = 50,
        min_trades: int = 3,
    ) -> OptimizationResult:
        """
        Run grid-search over parameter combinations.

        Args:
            candles:         OHLCV list
            symbol:          label
            timeframe:       label
            initial_balance: starting equity
            grid:            override DEFAULT_GRID
            sort_metric:     metric key from PerformanceMetrics.to_dict() to rank by
            warmup_bars:     skip first N bars for indicator warm-up
            min_trades:      skip results with fewer trades than this
        """
        g = grid or DEFAULT_GRID
        keys   = list(g.keys())
        values = list(g.values())
        combos = list(itertools.product(*values))
        total  = len(combos)
        logger.info(f"Optimizer: {total} combinations × {len(candles)} candles")

        engine  = BacktestEngine(self.config)
        results = []

        for combo in combos:
            params = dict(zip(keys, combo))
            sl_pct   = params["stop_loss_pct"]
            tp_pct   = params["take_profit_pct"]
            lev      = params["leverage"]
            pos_pct  = params.get("position_size_pct", 5.0)
            pos_size = initial_balance * pos_pct / 100.0

            try:
                bt: BacktestResult = engine.run(
                    candles=candles,
                    symbol=symbol,
                    timeframe=timeframe,
                    initial_balance=initial_balance,
                    position_size_usd=pos_size,
                    stop_loss_pct=sl_pct,
                    take_profit_pct=tp_pct,
                    leverage=lev,
                    warmup_bars=warmup_bars,
                )
            except Exception as e:
                logger.debug(f"Optimizer combo {params} failed: {e}")
                continue

            m = bt.metrics
            if m.total_trades < min_trades:
                continue

            entry = {
                "params": {
                    "stop_loss_pct":    sl_pct,
                    "take_profit_pct":  tp_pct,
                    "leverage":         lev,
                    "position_size_pct": pos_pct,
                    "position_size_usd": round(pos_size, 2),
                },
                **m.to_dict(),
            }
            results.append(entry)

        # ── Sort ──────────────────────────────────────────────────────────────
        def sort_key(r):
            v = r.get(sort_metric, 0)
            # Penalise infinite or very large values (e.g. PF when no losses)
            if isinstance(v, float) and (v != v or v > 1e6):
                return -1e9
            return v if v is not None else -1e9

        results.sort(key=sort_key, reverse=True)
        best = results[0] if results else {}

        return OptimizationResult(
            symbol=symbol,
            timeframe=timeframe,
            total_combinations=total,
            valid_combinations=len(results),
            sort_metric=sort_metric,
            results=results,
            best_params=best.get("params", {}),
            best_metrics={k: v for k, v in best.items() if k != "params"},
        )
