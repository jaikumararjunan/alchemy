"""
tests/unit/test_core.py
=======================
Unit tests for Alchemy core modules.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import date


# ── AlchemyTradingState ───────────────────────────────────────────────────────

class TestAlchemyTradingState:
    def test_default_state(self):
        from alchemy.core.state import AlchemyTradingState
        s = AlchemyTradingState(ticker="RELIANCE")
        assert s.ticker == "RELIANCE"
        assert s.market == "NSE"
        assert s.broker == "PAPER"
        assert s.signal is None
        assert s.errors == []

    def test_is_actionable_false_on_hold(self):
        from alchemy.core.state import AlchemyTradingState
        s = AlchemyTradingState(ticker="TCS", signal="HOLD", position_pct=0.05)
        assert not s.is_actionable()

    def test_is_actionable_true_on_buy(self):
        from alchemy.core.state import AlchemyTradingState
        s = AlchemyTradingState(ticker="TCS", signal="BUY", position_pct=0.05)
        assert s.is_actionable()

    def test_add_error(self):
        from alchemy.core.state import AlchemyTradingState
        s = AlchemyTradingState(ticker="INFY")
        s.add_error("test error")
        assert len(s.errors) == 1
        assert "test error" in s.errors[0]

    def test_to_dict(self):
        from alchemy.core.state import AlchemyTradingState
        s = AlchemyTradingState(ticker="WIPRO")
        d = s.to_dict()
        assert d["ticker"] == "WIPRO"
        assert "signal" in d
        assert "created_at" in d


# ── RiskManager ───────────────────────────────────────────────────────────────

class TestRiskManager:
    def _make_signal(self, signal="BUY", pos=0.05, vol=0.20):
        from alchemy.core.state import TradingSignal
        return TradingSignal(
            ticker="RELIANCE", market="NSE", signal=signal,
            position_pct=pos, stop_loss_pct=0.02, take_profit_pct=0.04,
            sentiment_score=0.5, forecast_vol=vol,
            reasoning="test", run_id="test_001",
        )

    def test_approve_normal_signal(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.update_portfolio_value(100_000)
        veto = rm.evaluate(self._make_signal(), portfolio_value=100_000)
        assert not veto.vetoed
        assert veto.adjusted_position_pct is not None

    def test_emergency_stop_blocks_all(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.trigger_emergency_stop("test")
        veto = rm.evaluate(self._make_signal(), portfolio_value=100_000)
        assert veto.vetoed
        assert "Emergency" in veto.reason

    def test_blocked_ticker(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.block_ticker("RELIANCE")
        veto = rm.evaluate(self._make_signal(), portfolio_value=100_000)
        assert veto.vetoed

    def test_extreme_vol_blocks_buy(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.update_portfolio_value(100_000)
        veto = rm.evaluate(
            self._make_signal(signal="BUY", vol=0.55),
            portfolio_value=100_000
        )
        assert veto.vetoed
        assert "volatility" in veto.reason.lower()

    def test_extreme_vol_allows_sell(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.update_portfolio_value(100_000)
        veto = rm.evaluate(
            self._make_signal(signal="SELL", vol=0.55),
            portfolio_value=100_000
        )
        assert not veto.vetoed

    def test_vol_scaling_reduces_position(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        rm.update_portfolio_value(100_000)
        veto = rm.evaluate(self._make_signal(vol=0.35), portfolio_value=100_000)
        assert not veto.vetoed
        assert veto.adjusted_position_pct < 0.05

    def test_status_dict(self):
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        status = rm.status()
        assert "emergency_stop" in status
        assert "daily_pnl" in status
        assert "open_positions" in status


# ── VolatilityEngine ─────────────────────────────────────────────────────────

class TestVolatilityEngine:
    def _make_returns(self, n=300, seed=42):
        np.random.seed(seed)
        return pd.Series(np.random.normal(0.0005, 0.015, n))

    def test_fit_garch(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine(model="GARCH")
        engine.fit(self._make_returns())
        assert engine._result is not None

    def test_current_vol_annualised(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        engine.fit(self._make_returns())
        vol = engine.get_current_vol()
        assert isinstance(vol, pd.Series)
        assert 0.05 < vol.iloc[-1] < 1.0  # sensible annualised range

    def test_forecast_vol(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        engine.fit(self._make_returns())
        fc = engine.forecast_vol(horizon=5)
        assert isinstance(fc, float)
        assert 0.05 < fc < 1.0

    def test_vol_regime_classification(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        engine.fit(self._make_returns())
        regime = engine.vol_regime()
        assert regime in ("low", "normal", "high", "extreme")

    def test_requires_min_observations(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        with pytest.raises(ValueError, match="at least 30"):
            engine.fit(pd.Series([0.01] * 10))

    def test_error_before_fit(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        with pytest.raises(RuntimeError, match="not fitted"):
            engine.get_current_vol()

    def test_summary_dict(self):
        from alchemy.analytics.volatility import VolatilityEngine
        engine = VolatilityEngine()
        engine.fit(self._make_returns())
        s = engine.summary()
        assert "sharpe" not in s
        assert "current_vol_annualised" in s
        assert "forecast_1d" in s
        assert "vol_regime" in s


# ── PortfolioAnalytics ────────────────────────────────────────────────────────

class TestPortfolioAnalytics:
    def _make_returns(self, n=252, seed=0):
        np.random.seed(seed)
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        return pd.Series(np.random.normal(0.0006, 0.012, n), index=idx)

    def test_fallback_metrics(self):
        from alchemy.analytics.portfolio import PortfolioAnalytics
        pa = PortfolioAnalytics(self._make_returns())
        m = pa._fallback_metrics()
        assert "sharpe_ratio" in m
        assert "max_drawdown" in m
        assert m["n_trading_days"] == 252

    def test_save_tear_sheet(self, tmp_path):
        from alchemy.analytics.portfolio import PortfolioAnalytics
        pa = PortfolioAnalytics(self._make_returns())
        out = pa.save_tear_sheet(tmp_path / "tear.png")
        assert out.exists()
        assert out.stat().st_size > 10_000
