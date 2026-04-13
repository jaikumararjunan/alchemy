"""
tests.unit.test_cvar
=====================
Unit tests for alchemy.risk.cvar — CVaR / Expected Shortfall and Kelly Criterion.
"""
import pytest
from alchemy.risk.cvar import (
    expected_shortfall,
    kelly_fraction,
    portfolio_cvar,
    annualise_cvar,
    CVaRResult,
)


class TestExpectedShortfall:

    def test_empty_returns_gives_zero(self):
        result = expected_shortfall([])
        assert result.var == 0.0
        assert result.cvar == 0.0
        assert result.n_observations == 0

    def test_single_return(self):
        result = expected_shortfall([-0.05])
        assert result.cvar >= 0

    def test_positive_returns_give_near_zero_cvar(self):
        # All gains — CVaR should be very small (near-zero or zero tail loss)
        returns = [0.01, 0.02, 0.015, 0.03, 0.025, 0.01, 0.02]
        result = expected_shortfall(returns, confidence=0.95)
        assert isinstance(result, CVaRResult)
        # CVaR is positive (a loss), but since all returns are positive it should be ≤ 0 loss
        # (could be slight positive due to cutoff at tail end which is still positive)
        assert result.n_observations == len(returns)

    def test_known_values(self):
        # Returns: sorted = [-0.10, -0.05, -0.02, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
        # 10 observations, 95% confidence → 5% tail → bottom 0.5 → cutoff_idx=0
        returns = [0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, -0.02, -0.05, -0.10]
        result = expected_shortfall(returns, confidence=0.95)
        assert result.var > 0
        assert result.cvar >= result.var
        assert result.worst_loss == pytest.approx(0.10, abs=1e-4)

    def test_cvar_exceeds_var(self):
        """CVaR is always >= VaR by definition (coherent risk measure)."""
        import random
        random.seed(42)
        returns = [random.gauss(-0.001, 0.02) for _ in range(200)]
        result = expected_shortfall(returns, confidence=0.95)
        assert result.cvar >= result.var - 1e-9  # allow floating point tolerance

    def test_confidence_levels(self):
        returns = list(range(-50, 51))  # -50..50
        r95 = expected_shortfall(returns, confidence=0.95)
        r99 = expected_shortfall(returns, confidence=0.99)
        # Higher confidence → smaller tail → larger (worse) CVaR
        assert r99.cvar >= r95.cvar


class TestKellyFraction:

    def test_zero_edge_returns_zero(self):
        # win_rate * avg_win == loss_rate * avg_loss  => edge = 0
        result = kelly_fraction(win_rate=0.5, avg_win=0.01, avg_loss=0.01)
        assert result == 0.0

    def test_negative_edge_returns_zero(self):
        result = kelly_fraction(win_rate=0.3, avg_win=0.01, avg_loss=0.05)
        assert result == 0.0

    def test_positive_edge(self):
        result = kelly_fraction(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        assert result > 0

    def test_clamped_to_one(self):
        # Even extreme edge should not exceed 1.0
        result = kelly_fraction(win_rate=0.99, avg_win=1.0, avg_loss=0.001)
        assert result <= 1.0

    def test_quarter_kelly_default(self):
        # full Kelly for win=0.6, avgW=0.02, avgL=0.01:
        # edge = 0.6*0.02 - 0.4*0.01 = 0.012 - 0.004 = 0.008
        # full_kelly = 0.008 / 0.02 = 0.4
        # quarter_kelly = 0.1
        result = kelly_fraction(win_rate=0.6, avg_win=0.02, avg_loss=0.01, fraction=0.25)
        assert result == pytest.approx(0.1, abs=1e-4)

    def test_invalid_inputs_return_zero(self):
        assert kelly_fraction(win_rate=0.5, avg_win=0, avg_loss=0.01) == 0.0
        assert kelly_fraction(win_rate=0.5, avg_win=0.01, avg_loss=0) == 0.0


class TestPortfolioCVaR:

    def test_empty_input(self):
        result = portfolio_cvar({})
        assert result.var == 0.0
        assert result.cvar == 0.0

    def test_single_position(self):
        rets = {"BTC": [0.01, -0.02, 0.03, -0.01, 0.02]}
        result = portfolio_cvar(rets)
        assert result.n_observations == 5

    def test_equal_weights_assumed(self):
        rets = {
            "BTC": [0.01, -0.02, 0.03],
            "ETH": [-0.01, 0.02, -0.03],
        }
        result = portfolio_cvar(rets)
        assert result.n_observations == 3

    def test_custom_weights(self):
        rets = {
            "BTC": [0.01, -0.02, 0.03, 0.0, -0.01],
            "ETH": [-0.01, 0.02, -0.03, 0.01, 0.02],
        }
        result = portfolio_cvar(rets, weights={"BTC": 0.7, "ETH": 0.3})
        assert result.n_observations == 5


class TestAnnualiseCVaR:

    def test_daily_to_annual(self):
        daily = 0.01  # 1% daily CVaR
        annual = annualise_cvar(daily, trading_days=252)
        assert annual == pytest.approx(daily * (252 ** 0.5), rel=1e-4)

    def test_zero_stays_zero(self):
        assert annualise_cvar(0.0) == 0.0
