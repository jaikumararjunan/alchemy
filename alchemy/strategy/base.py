"""
alchemy.strategy.base
=====================
Abstract base class for all Alchemy trading strategies.
Wraps the Blueshift strategy pattern from blueshift-developer-kit.
Source: https://github.com/QuantInsti/blueshift-developer-kit
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyParams:
    """Configuration parameters for a strategy."""
    name: str
    universe: list[str] = field(default_factory=list)
    lookback: int = 20
    rebalance_freq: str = "weekly"          # daily | weekly | monthly
    max_position_pct: float = 0.05
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    extra: dict = field(default_factory=dict)


class AlchemyStrategyBase(ABC):
    """
    Abstract base for all Alchemy strategies.

    Mirrors the Blueshift callback interface:
        initialize  → called once at start
        handle_data → called every bar
        rebalance   → called on schedule

    Subclass and implement the abstract methods, then deploy on
    Blueshift or run via AlchemyBacktestEngine.

    Example::

        class SMACrossover(AlchemyStrategyBase):
            def initialize(self, context):
                self.fast = 10
                self.slow = 30
                self.schedule_rebalance(context)

            def rebalance(self, context, data):
                for asset in self.params.universe:
                    prices = data.history(asset, 'close', self.slow, '1d')
                    if prices[-self.fast:].mean() > prices.mean():
                        self.order_target_percent(context, asset, self.params.max_position_pct)
                    else:
                        self.order_target_percent(context, asset, 0.0)

            def handle_data(self, context, data):
                pass
    """

    def __init__(self, params: StrategyParams) -> None:
        self.params = params
        self._initialized = False

    # ── Abstract Interface (Blueshift callbacks) ──────────────────────────────

    @abstractmethod
    def initialize(self, context: Any) -> None:
        """Called once at strategy start. Set up universe, schedule functions."""

    @abstractmethod
    def handle_data(self, context: Any, data: Any) -> None:
        """Called every bar. Avoid heavy computation here."""

    @abstractmethod
    def rebalance(self, context: Any, data: Any) -> None:
        """Called on schedule. Main portfolio rebalancing logic."""

    # ── Optional Hooks ────────────────────────────────────────────────────────

    def before_trading_start(self, context: Any, data: Any) -> None:
        """Optional: pre-market data fetching / pipeline computation."""

    def after_trading_hours(self, context: Any, data: Any) -> None:
        """Optional: post-market logging, cleanup, reporting."""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def order_target_percent(self, context: Any, asset: str, pct: float) -> None:
        """Route to Blueshift order_target_percent or paper engine."""
        pct = min(max(pct, 0.0), self.params.max_position_pct)
        try:
            from blueshift.api import order_target_percent as _ot
            _ot(asset, pct)
        except ImportError:
            # Paper mode: log only
            import structlog
            structlog.get_logger(__name__).info(
                "paper.order", asset=asset, target_pct=round(pct, 4)
            )

    def schedule_rebalance(self, context: Any) -> None:
        """Attach rebalance to the appropriate schedule."""
        try:
            from blueshift.api import schedule_function, date_rules, time_rules
            freq_map = {
                "daily":   date_rules.every_day(),
                "weekly":  date_rules.week_start(),
                "monthly": date_rules.month_start(),
            }
            schedule_function(
                self.rebalance,
                freq_map.get(self.params.rebalance_freq, date_rules.week_start()),
                time_rules.market_open(minutes=30),
            )
        except ImportError:
            pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.params.name!r})"
