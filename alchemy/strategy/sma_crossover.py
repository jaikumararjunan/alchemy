"""
alchemy.strategy.sma_crossover
================================
Simple Moving Average crossover strategy.
Adapted from: https://github.com/QuantInsti/blueshift-demo-strategies

A classic momentum strategy: go long when fast SMA crosses above slow SMA,
flat otherwise. Demonstrates the AlchemyStrategyBase pattern.
"""
from __future__ import annotations

from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None
import structlog

from alchemy.strategy.base import AlchemyStrategyBase, StrategyParams

log = structlog.get_logger(__name__)


class SMACrossoverStrategy(AlchemyStrategyBase):
    """
    Dual SMA crossover strategy.

    Signal:
        BUY  → fast_sma > slow_sma (uptrend)
        FLAT → fast_sma <= slow_sma

    Usage (Blueshift)::

        strategy = SMACrossoverStrategy(StrategyParams(
            name="sma_crossover",
            universe=["NIFTY-I"],
            lookback=50,
        ))
        # Deploy on Blueshift as:
        #   initialize = strategy.initialize
        #   handle_data = strategy.handle_data

    Usage (backtest)::

        from alchemy.strategy.backtest import run_backtest
        results = run_backtest(strategy, "2022-01-01", "2024-12-31")
    """

    def __init__(
        self,
        params: StrategyParams | None = None,
        fast: int = 10,
        slow: int = 30,
    ) -> None:
        if params is None:
            params = StrategyParams(name="sma_crossover")
        super().__init__(params)
        self.fast = fast
        self.slow = slow
        self._positions: dict[str, float] = {}

    def initialize(self, context: Any) -> None:
        log.info("strategy.init", name=self.params.name,
                 fast=self.fast, slow=self.slow)
        self._initialized = True
        self.schedule_rebalance(context)

        try:
            from blueshift.finance import commission, slippage
            from blueshift.api import set_commission, set_slippage
            set_commission(commission.PerShare(cost=0.001, min_trade_cost=0))
            set_slippage(slippage.VolumeShareSlippage(volume_limit=0.025))
        except ImportError:
            pass

    def handle_data(self, context: Any, data: Any) -> None:
        """No per-bar logic — all done in rebalance."""

    def rebalance(self, context: Any, data: Any) -> None:
        """Weekly SMA crossover check and rebalance."""
        for asset in self.params.universe:
            try:
                prices = data.history(asset, "close", self.slow + 5, "1d")
                if prices is None or len(prices) < self.slow:
                    log.warning("strategy.insufficient_data", asset=asset)
                    continue

                fast_sma = float(prices.iloc[-self.fast:].mean())
                slow_sma = float(prices.mean())
                current   = float(prices.iloc[-1])

                if fast_sma > slow_sma:
                    target_pct = self.params.max_position_pct
                    log.info("strategy.signal", asset=asset, signal="LONG",
                             fast_sma=round(fast_sma, 2), slow_sma=round(slow_sma, 2))
                else:
                    target_pct = 0.0
                    log.info("strategy.signal", asset=asset, signal="FLAT",
                             fast_sma=round(fast_sma, 2), slow_sma=round(slow_sma, 2))

                self.order_target_percent(context, asset, target_pct)
                self._positions[asset] = target_pct

            except Exception as e:
                log.error("strategy.rebalance_error", asset=asset, error=str(e))

    def before_trading_start(self, context: Any, data: Any) -> None:
        log.debug("strategy.pre_market", positions=len(self._positions))

    def compute_signals_offline(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Compute SMA crossover signals from a price DataFrame (for backtesting).

        Args:
            prices: pd.DataFrame with assets as columns, DatetimeIndex.

        Returns:
            pd.DataFrame of +1 (long) / 0 (flat) signals per asset per day.
        """
        fast_ma = prices.rolling(self.fast).mean()
        slow_ma = prices.rolling(self.slow).mean()
        signals = (fast_ma > slow_ma).astype(float)
        return signals.shift(1).fillna(0)  # Avoid lookahead
