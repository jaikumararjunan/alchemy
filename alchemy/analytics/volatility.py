"""
alchemy.analytics.volatility
=============================
GARCH/EGARCH volatility forecasting.
Requires: numpy, pandas, arch  (pip install numpy pandas arch)
Falls back gracefully if not installed.
"""
from __future__ import annotations
from typing import Optional
import structlog

log = structlog.get_logger(__name__)

try:
    import numpy as np
    import pandas as pd
    from arch import arch_model
    _QUANT_AVAILABLE = True
except ImportError:
    _QUANT_AVAILABLE = False
    log.warning("volatility.quant_libs_missing",
                hint="pip install numpy pandas arch")


def forecast_garch_vol(
    returns: list[float],
    horizon: int = 1,
    model: str = "GARCH",
) -> float:
    """
    Forecast next-period volatility using GARCH(1,1).
    Returns annualised volatility, or 0.0 if libs not available.
    """
    if not _QUANT_AVAILABLE:
        return 0.0
    try:
        ret_series = pd.Series(returns) * 100
        am  = arch_model(ret_series, vol=model, p=1, q=1)
        res = am.fit(disp="off", show_warning=False)
        fcast = res.forecast(horizon=horizon)
        var   = fcast.variance.iloc[-1, 0]
        daily = float(np.sqrt(var)) / 100
        return daily * float(np.sqrt(252))
    except Exception as e:
        log.error("volatility.forecast_failed", error=str(e))
        return 0.0


def rolling_vol(prices: list[float], window: int = 20) -> float:
    """Simple rolling std-dev volatility — no heavy deps needed."""
    if len(prices) < window:
        return 0.0
    import math
    chunk = prices[-window:]
    mean  = sum(chunk) / window
    if mean == 0:
        return 0.0
    variance = sum((p - mean) ** 2 for p in chunk) / (window - 1)
    return math.sqrt(variance / mean ** 2) * math.sqrt(252)


class VolatilityEngine:
    """
    GARCH(1,1) volatility engine matching the test contract.

    Usage::
        engine = VolatilityEngine(model="GARCH")
        engine.fit(returns_series)
        vol    = engine.get_current_vol()    # pd.Series
        fc     = engine.forecast_vol(horizon=5)  # float
        regime = engine.vol_regime()         # str
        info   = engine.summary()            # dict
    """

    MIN_OBS = 30   # tests expect "at least 30"

    def __init__(self, model: str = "GARCH") -> None:
        self._model_type = model
        self._fitted     = False
        self._arch_model = None
        self._result     = None
        self._returns    = None
        self.available   = _QUANT_AVAILABLE

    def fit(self, returns, model: Optional[str] = None) -> "VolatilityEngine":
        """
        Fit GARCH model to returns.

        Args:
            returns: pd.Series or list of log-returns / % returns
            model:   "GARCH" | "EGARCH" | "GJR-GARCH" (overrides __init__)
        """
        if not _QUANT_AVAILABLE:
            log.warning("VolatilityEngine.fit: numpy/arch not installed")
            return self

        model_type = model or self._model_type

        if hasattr(returns, '__len__') and len(returns) < self.MIN_OBS:
            raise ValueError(
                f"Need at least {self.MIN_OBS} observations, got {len(returns)}"
            )

        try:
            if not isinstance(returns, pd.Series):
                returns = pd.Series(returns)

            # Scale to percentage returns for numerical stability
            scaled = returns * 100 if returns.abs().max() < 1 else returns

            self._arch_model = arch_model(scaled, vol=model_type, p=1, q=1)
            self._result     = self._arch_model.fit(disp="off", show_warning=False)
            self._returns    = returns
            self._fitted     = True
        except Exception as e:
            raise RuntimeError(f"GARCH fit failed: {e}") from e
        return self

    def get_current_vol(self) -> "pd.Series":
        """
        Return conditional volatility series (annualised).
        Tests expect a pd.Series so iloc[-1] works.
        """
        if not self._fitted:
            raise RuntimeError("VolatilityEngine not fitted — call fit() first")
        cond_vol = self._result.conditional_volatility / 100 * float(np.sqrt(252))
        return cond_vol

    def forecast_vol(self, horizon: int = 1) -> float:
        """Return scalar annualised volatility forecast for given horizon."""
        if not self._fitted:
            raise RuntimeError("VolatilityEngine not fitted — call fit() first")
        fcast = self._result.forecast(horizon=horizon)
        var   = fcast.variance.iloc[-1, 0]
        daily = float(np.sqrt(var)) / 100
        return daily * float(np.sqrt(252))

    def current_vol(self) -> float:
        """Scalar alias for the last value of get_current_vol()."""
        return float(self.get_current_vol().iloc[-1])

    def vol_regime(self) -> str:
        vol = self.current_vol()
        if vol < 0.15: return "low"
        if vol < 0.25: return "normal"
        if vol < 0.40: return "high"
        return "extreme"

    def summary(self) -> dict:
        """Return dict with keys expected by tests."""
        if not self._fitted:
            return {"fitted": False, "available": self.available}
        return {
            "fitted":                True,
            "current_vol_annualised": round(self.current_vol(), 6),
            "forecast_1d":           round(self.forecast_vol(horizon=1), 6),
            "vol_regime":            self.vol_regime(),
            "aic":                   round(float(self._result.aic), 4),
            "bic":                   round(float(self._result.bic), 4),
            "model":                 f"{self._model_type}(1,1)",
        }
