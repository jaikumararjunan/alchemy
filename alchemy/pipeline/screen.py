"""
alchemy.pipeline.screen
========================
Factor-based universe screening using zipline-pipeline.
Source: https://github.com/QuantInsti/zipline-pipeline

Screens a tradeable universe daily using liquidity, momentum,
and quality factors via Zipline's Pipeline API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None
import structlog

log = structlog.get_logger(__name__)


@dataclass
class ScreenConfig:
    universe_size: int = 20
    liquidity_window: int = 30          # days for avg dollar volume
    momentum_window: int = 63           # ~3 months
    rsi_window: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    min_price: float = 10.0


class AlchemyPipelineScreen:
    """
    Zipline Pipeline wrapper for systematic universe construction.

    Builds a daily factor pipeline and screens the top N assets
    by momentum score, filtered by liquidity and RSI.

    Usage::

        screen = AlchemyPipelineScreen(engine, config=ScreenConfig(universe_size=20))
        universe_df = screen.run("2024-01-01", "2024-12-31")
        top_assets  = screen.get_top_assets(universe_df, date="2024-06-01")
    """

    def __init__(
        self,
        engine: Optional[object] = None,
        config: Optional[ScreenConfig] = None,
    ) -> None:
        self.engine = engine
        self.cfg = config or ScreenConfig()

    def build_pipeline(self) -> object:
        """Construct the Zipline Pipeline with factors and screen."""
        try:
            from zipline_pipeline.pipeline import Pipeline
            from zipline_pipeline.pipeline.factors import (
                AverageDollarVolume,
                Returns,
                RSI,
            )

            cfg = self.cfg

            # ── Factors ───────────────────────────────────────────────────
            dollar_vol   = AverageDollarVolume(window_length=cfg.liquidity_window)
            momentum_1m  = Returns(window_length=21)
            momentum_3m  = Returns(window_length=cfg.momentum_window)
            rsi          = RSI(window_length=cfg.rsi_window)

            # ── Composite momentum score ──────────────────────────────────
            momentum_score = (
                momentum_1m.zscore() * 0.40 +
                momentum_3m.zscore() * 0.60
            )

            # ── Filters ──────────────────────────────────────────────────
            liquid       = dollar_vol.top(500)
            not_overbought = rsi < cfg.rsi_overbought
            top_momentum = momentum_score.top(
                cfg.universe_size, mask=liquid & not_overbought
            )

            return Pipeline(
                columns={
                    "momentum_1m":     momentum_1m,
                    "momentum_3m":     momentum_3m,
                    "momentum_score":  momentum_score,
                    "rsi":             rsi,
                    "dollar_vol":      dollar_vol,
                },
                screen=top_momentum,
            )
        except ImportError:
            log.error("pipeline.zipline_not_installed")
            raise RuntimeError(
                "zipline-pipeline not installed. "
                "Run: pip install git+https://github.com/QuantInsti/zipline-pipeline.git"
            )

    def run(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Execute the pipeline over a date range.

        Returns:
            pd.DataFrame with MultiIndex (date, asset) and factor columns.
        """
        if self.engine is None:
            raise RuntimeError("Pipeline engine not configured. Pass engine= to __init__.")

        pipeline = self.build_pipeline()
        log.info("pipeline.run", start=start_date, end=end_date,
                 universe_size=self.cfg.universe_size)

        results = self.engine.run_pipeline(pipeline, start_date, end_date)
        log.info("pipeline.complete", rows=len(results))
        return results

    def get_top_assets(
        self, pipeline_output: pd.DataFrame, date: str
    ) -> list[str]:
        """Extract the top-ranked assets for a specific date."""
        try:
            day_data = pipeline_output.loc[pd.Timestamp(date)]
            return (
                day_data.sort_values("momentum_score", ascending=False)
                .head(self.cfg.universe_size)
                .index.tolist()
            )
        except KeyError:
            log.warning("pipeline.date_not_found", date=date)
            return []

    def momentum_factor_offline(
        self, prices: pd.DataFrame, top_n: int = 20
    ) -> pd.DataFrame:
        """
        Compute momentum factor rankings without Zipline engine.
        Useful for quick backtests with a plain price DataFrame.

        Args:
            prices: pd.DataFrame, assets as columns, DatetimeIndex.
            top_n:  Number of top momentum assets to select.

        Returns:
            pd.DataFrame of boolean selection mask (True = selected).
        """
        mom_3m = prices.pct_change(63)
        mom_1m = prices.pct_change(21)
        score  = 0.6 * mom_3m + 0.4 * mom_1m
        ranked = score.rank(axis=1, ascending=False)
        return ranked <= top_n
