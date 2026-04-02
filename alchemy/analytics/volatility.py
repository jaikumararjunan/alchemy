"""
alchemy.analytics.volatility
=============================
GARCH-based volatility engine wrapping the arch library.
Source: https://github.com/QuantInsti/arch

Provides conditional volatility estimation and forward forecasting
for dynamic position sizing and risk management.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import structlog
from arch import arch_model
from arch.univariate.base import ARCHModelResult

log = structlog.get_logger(__name__)

VOL_MODELS = ("GARCH", "EGARCH", "GJR-GARCH", "FIGARCH")


class VolatilityEngine:
    """
    Wraps arch library for production volatility modelling.

    Supported models:
        - GARCH(p, q)  — Standard conditional heteroskedasticity
        - EGARCH       — Asymmetric; captures leverage effect (negative returns → higher vol)
        - GJR-GARCH    — Threshold GARCH; another asymmetric variant

    Usage::

        engine = VolatilityEngine(model="GARCH", p=1, q=1)
        engine.fit(returns_series)

        current_vol  = engine.get_current_vol().iloc[-1]   # annualised
        forecast_5d  = engine.forecast_vol(horizon=5)       # annualised
    """

    TRADING_DAYS = 252

    def __init__(
        self,
        model: str = "GARCH",
        p: int = 1,
        q: int = 1,
        dist: str = "normal",
    ) -> None:
        if model not in VOL_MODELS:
            raise ValueError(f"model must be one of {VOL_MODELS}, got '{model}'")
        self.model_type = model
        self.p = p
        self.q = q
        self.dist = dist
        self._result: Optional[ARCHModelResult] = None
        self._returns: Optional[pd.Series] = None

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(self, returns: pd.Series) -> "VolatilityEngine":
        """
        Fit GARCH model to daily return series.

        Args:
            returns: pd.Series of daily returns (NOT percentages — e.g. 0.012 not 1.2).
                     Minimum 30 observations required; 252 recommended.
        """
        if len(returns) < 30:
            raise ValueError(f"Need at least 30 returns for GARCH fitting; got {len(returns)}")

        self._returns = returns.dropna()
        pct_returns = self._returns * 100  # arch expects percentage returns

        try:
            am = arch_model(
                pct_returns,
                vol=self.model_type if self.model_type != "GJR-GARCH" else "GARCH",
                o=1 if self.model_type == "GJR-GARCH" else 0,
                p=self.p,
                q=self.q,
                dist=self.dist,
            )
            self._result = am.fit(disp="off", show_warning=False)
            log.info(
                "volatility.fitted",
                model=self.model_type,
                n_obs=len(self._returns),
                aic=round(self._result.aic, 2),
                bic=round(self._result.bic, 2),
            )
        except Exception as e:
            log.error("volatility.fit_error", error=str(e))
            raise
        return self

    # ── Retrieval ────────────────────────────────────────────────────────────

    def get_current_vol(self) -> pd.Series:
        """
        Return annualised conditional volatility series (in-sample).

        Returns:
            pd.Series indexed like the input returns, values are annualised std.
        """
        self._check_fitted()
        daily_vol = self._result.conditional_volatility / 100  # back to decimal
        return daily_vol * np.sqrt(self.TRADING_DAYS)

    def forecast_vol(self, horizon: int = 1) -> float:
        """
        Return annualised volatility forecast for next `horizon` trading days.

        Args:
            horizon: Number of trading days to forecast (1–21).

        Returns:
            Float: annualised volatility (e.g. 0.24 = 24%)
        """
        self._check_fitted()
        if horizon < 1 or horizon > 252:
            raise ValueError(f"horizon must be 1–252, got {horizon}")

        fc = self._result.forecast(horizon=horizon, reindex=False)
        # fc.variance shape: (1, horizon) — take mean over horizon
        mean_variance_pct_sq = float(fc.variance.iloc[-1].mean())
        daily_vol = np.sqrt(mean_variance_pct_sq) / 100
        return float(daily_vol * np.sqrt(self.TRADING_DAYS))

    def vol_regime(self, thresholds: tuple[float, float, float] = (0.15, 0.25, 0.40)) -> str:
        """
        Classify current vol into: 'low' | 'normal' | 'high' | 'extreme'.

        Args:
            thresholds: (low_max, normal_max, high_max) annualised boundaries.
        """
        vol = self.get_current_vol().iloc[-1]
        low_max, normal_max, high_max = thresholds
        if vol < low_max:
            return "low"
        if vol < normal_max:
            return "normal"
        if vol < high_max:
            return "high"
        return "extreme"

    def summary(self) -> dict:
        """Return a summary dict of the fitted model."""
        self._check_fitted()
        current = self.get_current_vol()
        return {
            "model": self.model_type,
            "p": self.p,
            "q": self.q,
            "n_obs": len(self._returns),
            "aic": round(self._result.aic, 4),
            "bic": round(self._result.bic, 4),
            "current_vol_annualised": round(current.iloc[-1], 4),
            "forecast_1d": round(self.forecast_vol(1), 4),
            "forecast_5d": round(self.forecast_vol(5), 4),
            "vol_regime": self.vol_regime(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_fitted(self) -> None:
        if self._result is None:
            raise RuntimeError("Model not fitted. Call .fit(returns) first.")
