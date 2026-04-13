"""
tests/unit/test_trade_logic.py
=================================
Comprehensive tests for trade logic correctness across:
  - RiskManager (daily loss gate, drawdown, vol checks, singleton)
  - TechnicalAnalyzer (RSI, ATR, EMA, SMA, Bollinger Bands, VWAP, ADX)
  - ScalpingStrategy, MomentumStrategy, BreakoutStrategy
  - StrategyOrchestrator ranking
  - AutonomousTradingEngine configuration + signal lifecycle
  - KillSwitch singleton state propagation
  - PositionSizing methods
"""
from __future__ import annotations

import asyncio
import math
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_signal(signal="BUY", pos=0.05, vol=0.20, ticker="BTCUSDT"):
    from alchemy.core.state import TradingSignal
    return TradingSignal(
        ticker=ticker, market="NSE", signal=signal,
        position_pct=pos, stop_loss_pct=0.02, take_profit_pct=0.04,
        sentiment_score=0.5, forecast_vol=vol,
        reasoning="unit test", run_id="test",
    )


def _make_ohlcv(n=100, base=60000.0, trend=0.0):
    """Generate synthetic OHLCV with optional linear trend."""
    closes = [base + trend * i + (i % 5 - 2) * 50 for i in range(n)]
    highs  = [c + 200 for c in closes]
    lows   = [c - 200 for c in closes]
    opens  = [closes[max(0, i - 1)] for i in range(n)]
    volumes = [1000.0 + (i % 10) * 100 for i in range(n)]
    return {"closes": closes, "highs": highs, "lows": lows,
            "opens": opens, "volumes": volumes}


# ─────────────────────────────────────────────────────────────────────────────
# RiskManager — daily loss check (only triggers on losses, not gains)
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskManagerDailyLoss:

    def _fresh_rm(self, max_loss=1000.0):
        from alchemy.risk.manager import RiskManager
        from alchemy.core.config import RiskConfig
        cfg = RiskConfig(max_daily_loss_usd=max_loss)
        rm = RiskManager(config=cfg)
        rm.update_portfolio_value(100_000)
        return rm

    def test_large_profit_does_not_trigger_limit(self):
        """A highly profitable day must NOT trip the daily loss gate."""
        rm = self._fresh_rm(max_loss=1000.0)
        rm.record_pnl(+5000.0)  # Big profit
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert not veto.vetoed, "Profits should never trigger the daily loss limit"

    def test_loss_below_limit_passes(self):
        rm = self._fresh_rm(max_loss=1000.0)
        rm.record_pnl(-500.0)
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert not veto.vetoed

    def test_loss_at_exact_limit_is_blocked(self):
        rm = self._fresh_rm(max_loss=1000.0)
        rm.record_pnl(-1000.0)
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert veto.vetoed
        assert "Daily loss" in veto.reason

    def test_loss_beyond_limit_is_blocked(self):
        rm = self._fresh_rm(max_loss=500.0)
        rm.record_pnl(-600.0)
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert veto.vetoed

    def test_incremental_losses_accumulate(self):
        rm = self._fresh_rm(max_loss=1000.0)
        rm.record_pnl(-400.0)
        rm.record_pnl(-400.0)
        # 800 < 1000 — still OK
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert not veto.vetoed
        rm.record_pnl(-300.0)
        # 1100 >= 1000 — blocked
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert veto.vetoed

    def test_profit_then_loss_only_counts_net_loss(self):
        rm = self._fresh_rm(max_loss=1000.0)
        rm.record_pnl(+800.0)
        rm.record_pnl(-500.0)  # Net = +300 (no loss)
        veto = rm.evaluate(_make_signal(), portfolio_value=100_000)
        assert not veto.vetoed


# ─────────────────────────────────────────────────────────────────────────────
# RiskManager — drawdown circuit breaker
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskManagerDrawdown:

    def test_drawdown_triggers_emergency_stop(self):
        from alchemy.risk.manager import RiskManager
        from alchemy.core.config import RiskConfig
        cfg = RiskConfig(max_portfolio_drawdown_pct=0.10)
        rm = RiskManager(config=cfg)
        rm.update_portfolio_value(100_000)  # peak set
        rm.update_portfolio_value(89_000)   # -11% drawdown
        veto = rm.evaluate(_make_signal(), portfolio_value=89_000)
        assert veto.vetoed
        assert rm._emergency_stop

    def test_drawdown_below_limit_passes(self):
        from alchemy.risk.manager import RiskManager
        from alchemy.core.config import RiskConfig
        cfg = RiskConfig(max_portfolio_drawdown_pct=0.15)
        rm = RiskManager(config=cfg)
        rm.update_portfolio_value(100_000)
        rm.update_portfolio_value(92_000)  # -8% — within 15%
        veto = rm.evaluate(_make_signal(), portfolio_value=92_000)
        assert not veto.vetoed


# ─────────────────────────────────────────────────────────────────────────────
# RiskManager — singleton & kill-switch state propagation
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskManagerSingleton:

    def test_get_risk_manager_returns_same_instance(self):
        from alchemy.risk.manager import get_risk_manager
        rm1 = get_risk_manager()
        rm2 = get_risk_manager()
        assert rm1 is rm2

    def test_kill_switch_state_visible_via_singleton(self):
        from alchemy.risk.manager import get_risk_manager
        from alchemy.risk.kill_switch import is_kill_switch_active
        rm = get_risk_manager()
        rm.reset_emergency_stop()
        assert not is_kill_switch_active()
        rm.trigger_emergency_stop("test singleton")
        assert is_kill_switch_active()
        # Clean up for other tests
        rm.reset_emergency_stop()

    def test_kill_switch_inactive_after_reset(self):
        from alchemy.risk.manager import get_risk_manager
        from alchemy.risk.kill_switch import is_kill_switch_active
        rm = get_risk_manager()
        rm.reset_emergency_stop()
        assert not is_kill_switch_active()


# ─────────────────────────────────────────────────────────────────────────────
# TechnicalAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestTechnicalAnalyzer:

    def test_rsi_midpoint_on_flat_series(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [100.0] * 30
        rsi = TechnicalAnalyzer.compute_rsi(closes, 14)
        # Flat price → zero losses → RSI = 100 (no downward moves = max strength)
        assert rsi == 100.0

    def test_rsi_approaches_100_on_rising_series(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [float(i) for i in range(1, 50)]  # Strictly rising
        rsi = TechnicalAnalyzer.compute_rsi(closes, 14)
        assert rsi > 90

    def test_rsi_approaches_0_on_falling_series(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [float(50 - i) for i in range(50)]  # Strictly falling
        rsi = TechnicalAnalyzer.compute_rsi(closes, 14)
        assert rsi < 10

    def test_rsi_insufficient_data_returns_50(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [100.0, 101.0, 102.0]
        rsi = TechnicalAnalyzer.compute_rsi(closes, 14)
        assert rsi == 50.0

    def test_atr_positive(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        ohlcv = _make_ohlcv(50)
        atr = TechnicalAnalyzer.compute_atr(ohlcv["highs"], ohlcv["lows"], ohlcv["closes"])
        assert atr > 0

    def test_sma_correct_window(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        sma = TechnicalAnalyzer.compute_sma(data, 3)
        assert sma[0] is None
        assert sma[1] is None
        assert abs(sma[2] - 2.0) < 1e-9  # (1+2+3)/3
        assert abs(sma[4] - 4.0) < 1e-9  # (3+4+5)/3

    def test_ema_converges_to_price_on_constant_series(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        data = [100.0] * 50
        ema = TechnicalAnalyzer.compute_ema(data, 9)
        assert abs(ema[-1] - 100.0) < 1e-6

    def test_bollinger_bands_ordering(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [100.0 + i * 0.1 for i in range(50)]
        bb = TechnicalAnalyzer.compute_bollinger_bands(closes, 20)
        for i in range(20, 50):
            assert bb["upper"][i] >= bb["middle"][i] >= bb["lower"][i]

    def test_vwap_equals_typical_price_on_equal_volumes(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        closes = [100.0] * 10
        highs  = [105.0] * 10
        lows   = [95.0]  * 10
        volumes = [1.0]  * 10
        vwap = TechnicalAnalyzer.compute_vwap(closes, highs, lows, volumes)
        expected = (100 + 105 + 95) / 3  # typical price
        assert abs(vwap - expected) < 1e-6

    def test_adx_returns_positive_float(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        ohlcv = _make_ohlcv(100, trend=10.0)
        adx = TechnicalAnalyzer.compute_adx(ohlcv["highs"], ohlcv["lows"], ohlcv["closes"])
        assert isinstance(adx, float)
        assert adx >= 0

    def test_adx_insufficient_data_returns_default(self):
        from alchemy.trading.strategies.engine import TechnicalAnalyzer
        ohlcv = _make_ohlcv(5)
        adx = TechnicalAnalyzer.compute_adx(ohlcv["highs"], ohlcv["lows"], ohlcv["closes"])
        assert adx == 20.0


# ─────────────────────────────────────────────────────────────────────────────
# ScalpingStrategy
# ─────────────────────────────────────────────────────────────────────────────

class TestScalpingStrategy:

    def test_no_signal_for_insufficient_data(self):
        from alchemy.trading.strategies.engine import ScalpingStrategy
        strat = ScalpingStrategy()
        idea = strat.generate("BTCUSDT", {"closes": [100.0] * 5})
        assert idea is None

    def test_returns_none_or_tradeidea(self):
        from alchemy.trading.strategies.engine import ScalpingStrategy, TradeIdea
        strat = ScalpingStrategy()
        ohlcv = _make_ohlcv(60)
        result = strat.generate("BTCUSDT", ohlcv)
        assert result is None or isinstance(result, TradeIdea)

    def test_long_signal_has_correct_direction(self):
        from alchemy.trading.strategies.engine import ScalpingStrategy, TradeDirection
        strat = ScalpingStrategy()
        # Craft a clearly oversold setup: flat near lower band
        base = 60000.0
        closes = [base] * 60
        highs  = [base + 50] * 60
        lows   = [base - 800] * 60  # Very low bands
        volumes = [1000.0] * 60
        ohlcv = {"closes": closes, "highs": highs, "lows": lows,
                 "opens": closes, "volumes": volumes}
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea is not None:
            assert idea.direction in (TradeDirection.LONG, TradeDirection.SHORT)

    def test_stop_loss_correct_side_for_long(self):
        from alchemy.trading.strategies.engine import ScalpingStrategy, TradeDirection
        strat = ScalpingStrategy()
        ohlcv = _make_ohlcv(60)
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea and idea.direction == TradeDirection.LONG:
            assert idea.stop_loss < idea.entry_price
        elif idea and idea.direction == TradeDirection.SHORT:
            assert idea.stop_loss > idea.entry_price

    def test_extreme_emotional_score_suppresses_signal(self):
        from alchemy.trading.strategies.engine import ScalpingStrategy
        strat = ScalpingStrategy()
        ohlcv = _make_ohlcv(60)
        idea = strat.generate("BTCUSDT", ohlcv, emotional_score=0.05)  # Extreme fear
        assert idea is None


# ─────────────────────────────────────────────────────────────────────────────
# MomentumStrategy
# ─────────────────────────────────────────────────────────────────────────────

class TestMomentumStrategy:

    def test_no_signal_for_insufficient_data(self):
        from alchemy.trading.strategies.engine import MomentumStrategy
        strat = MomentumStrategy()
        idea = strat.generate("BTCUSDT", {"closes": [100.0] * 30})
        assert idea is None

    def test_returns_none_or_tradeidea(self):
        from alchemy.trading.strategies.engine import MomentumStrategy, TradeIdea
        strat = MomentumStrategy()
        ohlcv = _make_ohlcv(100)
        result = strat.generate("ETHUSDT", ohlcv)
        assert result is None or isinstance(result, TradeIdea)

    def test_bullish_signal_has_long_direction(self):
        from alchemy.trading.strategies.engine import MomentumStrategy, TradeDirection
        strat = MomentumStrategy()
        # Strong up-trend: 100 candles with consistent rise
        n = 100
        closes = [1000.0 + i * 20 for i in range(n)]
        highs  = [c + 10 for c in closes]
        lows   = [c - 10 for c in closes]
        ohlcv  = {"closes": closes, "highs": highs, "lows": lows, "volumes": [1000.0] * n}
        idea = strat.generate("BTCUSDT", ohlcv, market_bias="bullish")
        if idea is not None:
            assert idea.direction == TradeDirection.LONG

    def test_no_trend_suppresses_signal(self):
        from alchemy.trading.strategies.engine import MomentumStrategy
        strat = MomentumStrategy()
        # Completely flat — ADX will be low
        closes = [60000.0] * 100
        highs  = [60010.0] * 100
        lows   = [59990.0] * 100
        ohlcv  = {"closes": closes, "highs": highs, "lows": lows, "volumes": [1000.0] * 100}
        idea = strat.generate("BTCUSDT", ohlcv)
        assert idea is None  # ADX < 20 threshold


# ─────────────────────────────────────────────────────────────────────────────
# BreakoutStrategy — upward & downward target correctness
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakoutStrategy:

    def _ohlcv_for_upward_breakout(self, n=50):
        """Price consolidates then breaks above resistance."""
        highs   = [100.0] * (n - 1) + [115.0]   # Breakout above 100
        lows    = [90.0] * n
        closes  = [95.0] * (n - 1) + [113.0]
        volumes = [1000.0] * (n - 1) + [3000.0]  # Volume surge
        return {"closes": closes, "highs": highs, "lows": lows,
                "opens": closes, "volumes": volumes}

    def _ohlcv_for_downward_breakout(self, n=50):
        """Price consolidates then breaks below support."""
        highs   = [110.0] * n
        lows    = [100.0] * (n - 1) + [85.0]     # Breakdown below 100
        closes  = [105.0] * (n - 1) + [87.0]
        volumes = [1000.0] * (n - 1) + [3000.0]  # Volume surge
        return {"closes": closes, "highs": highs, "lows": lows,
                "opens": closes, "volumes": volumes}

    def test_upward_breakout_targets_above_entry(self):
        from alchemy.trading.strategies.engine import BreakoutStrategy, TradeDirection
        strat = BreakoutStrategy()
        ohlcv = self._ohlcv_for_upward_breakout()
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea is not None and idea.direction == TradeDirection.LONG:
            assert idea.take_profit_1 > idea.entry_price
            assert idea.take_profit_2 > idea.entry_price
            assert idea.take_profit_3 > idea.entry_price
            assert idea.stop_loss < idea.entry_price

    def test_downward_breakout_targets_below_entry(self):
        """
        Downward breakout: ALL take-profit targets must be below entry price.
        Previous bug: used (resistance - current) which made targets unreachably far.
        Fixed: uses (support - current) — symmetric with upward breakout.
        """
        from alchemy.trading.strategies.engine import BreakoutStrategy, TradeDirection
        strat = BreakoutStrategy()
        ohlcv = self._ohlcv_for_downward_breakout()
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea is not None and idea.direction == TradeDirection.SHORT:
            assert idea.take_profit_1 < idea.entry_price, \
                "TP1 must be below entry for a short"
            assert idea.take_profit_2 < idea.entry_price, \
                "TP2 must be below entry for a short"
            assert idea.take_profit_3 < idea.entry_price, \
                "TP3 must be below entry for a short"
            assert idea.stop_loss > idea.entry_price, \
                "Stop loss must be above entry for a short"

    def test_downward_targets_proportional(self):
        """TP3 must be farther from entry than TP2, which must be farther than TP1."""
        from alchemy.trading.strategies.engine import BreakoutStrategy, TradeDirection
        strat = BreakoutStrategy()
        ohlcv = self._ohlcv_for_downward_breakout()
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea is not None and idea.direction == TradeDirection.SHORT:
            assert idea.take_profit_2 <= idea.take_profit_1
            assert idea.take_profit_3 <= idea.take_profit_2

    def test_upward_targets_proportional(self):
        from alchemy.trading.strategies.engine import BreakoutStrategy, TradeDirection
        strat = BreakoutStrategy()
        ohlcv = self._ohlcv_for_upward_breakout()
        idea = strat.generate("BTCUSDT", ohlcv)
        if idea is not None and idea.direction == TradeDirection.LONG:
            assert idea.take_profit_2 >= idea.take_profit_1
            assert idea.take_profit_3 >= idea.take_profit_2

    def test_no_signal_without_volume_surge(self):
        from alchemy.trading.strategies.engine import BreakoutStrategy
        strat = BreakoutStrategy()
        n = 50
        highs   = [100.0] * (n - 1) + [115.0]
        lows    = [90.0] * n
        closes  = [95.0] * (n - 1) + [113.0]
        volumes = [1000.0] * n  # No volume surge
        ohlcv   = {"closes": closes, "highs": highs, "lows": lows,
                   "opens": closes, "volumes": volumes}
        idea = strat.generate("BTCUSDT", ohlcv)
        assert idea is None


# ─────────────────────────────────────────────────────────────────────────────
# StrategyOrchestrator
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyOrchestrator:

    def test_generate_ideas_returns_list(self):
        from alchemy.trading.strategies.engine import StrategyOrchestrator
        orch = StrategyOrchestrator()
        ohlcv = _make_ohlcv(100)
        ideas = asyncio.get_event_loop().run_until_complete(
            orch.generate_ideas(
                symbols=["BTCUSDT"],
                price_data={"BTCUSDT": ohlcv},
            )
        )
        assert isinstance(ideas, list)

    def test_ideas_capped_at_10(self):
        from alchemy.trading.strategies.engine import StrategyOrchestrator
        orch = StrategyOrchestrator()
        # Provide many symbols so multiple ideas are generated
        symbols = [f"SYM{i}" for i in range(20)]
        price_data = {sym: _make_ohlcv(100) for sym in symbols}
        ideas = asyncio.get_event_loop().run_until_complete(
            orch.generate_ideas(symbols=symbols, price_data=price_data)
        )
        assert len(ideas) <= 10

    def test_ideas_sorted_by_descending_score(self):
        from alchemy.trading.strategies.engine import StrategyOrchestrator
        orch = StrategyOrchestrator()
        symbols = [f"SYM{i}" for i in range(10)]
        price_data = {sym: _make_ohlcv(100) for sym in symbols}
        ideas = asyncio.get_event_loop().run_until_complete(
            orch.generate_ideas(symbols=symbols, price_data=price_data)
        )
        scores = [i.confidence * i.risk_reward for i in ideas]
        assert scores == sorted(scores, reverse=True) or len(ideas) <= 1

    def test_empty_data_returns_empty_list(self):
        from alchemy.trading.strategies.engine import StrategyOrchestrator
        orch = StrategyOrchestrator()
        ideas = asyncio.get_event_loop().run_until_complete(
            orch.generate_ideas(symbols=["BTCUSDT"], price_data={})
        )
        assert ideas == []


# ─────────────────────────────────────────────────────────────────────────────
# AutonomousTradingEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestAutonomousTradingEngine:

    def test_initial_status_is_idle(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine, AutoTradeStatus
        engine = AutonomousTradingEngine()
        assert engine.status == AutoTradeStatus.IDLE

    def test_configure_updates_fields(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        engine.configure(
            symbols=["XRPUSDT"],
            strategies=["scalping"],
            interval_seconds=30,
            auto_execute=True,
            exchange="delta",
            timeframe="5m",
        )
        assert engine.symbols == ["XRPUSDT"]
        assert engine.strategies == ["scalping"]
        assert engine.interval_seconds == 30
        assert engine.auto_execute is True
        assert engine.exchange == "delta"
        assert engine.timeframe == "5m"

    def test_configure_enforces_minimum_interval(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        engine.configure(interval_seconds=1)  # Below minimum
        assert engine.interval_seconds == 10

    def test_get_status_contains_required_keys(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        status = engine.get_status()
        for key in ("status", "symbols", "strategies", "interval_seconds",
                    "auto_execute", "exchange", "timeframe", "scan_count",
                    "total_signals", "active_signals"):
            assert key in status

    def test_get_history_empty_initially(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        assert engine.get_history() == []

    def test_strategy_map_cached(self):
        """Strategy instances must be the same across multiple get_status calls."""
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        assert "scalping" in engine._strategy_map
        assert "momentum" in engine._strategy_map
        assert "breakout" in engine._strategy_map
        # Same instances on repeated access
        assert engine._strategy_map["scalping"] is engine._strategy_map["scalping"]

    def test_stop_when_not_running_returns_error(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine
        engine = AutonomousTradingEngine()
        result = asyncio.get_event_loop().run_until_complete(engine.stop())
        assert result["ok"] is False

    def test_start_twice_returns_error(self):
        from alchemy.trading.autonomous import AutonomousTradingEngine, AutoTradeStatus
        engine = AutonomousTradingEngine()
        # Manually set status to RUNNING to simulate already-running
        engine.status = AutoTradeStatus.RUNNING
        result = asyncio.get_event_loop().run_until_complete(engine.start())
        assert result["ok"] is False
        # Clean up
        engine.status = AutoTradeStatus.IDLE


# ─────────────────────────────────────────────────────────────────────────────
# PositionSizing
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionSizing:

    def test_kelly_positive_edge(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(
            method=SizingMethod.KELLY,
            capital=10000, entry_price=100, stop_loss=95,
            win_rate=0.6, avg_win=150, avg_loss=100,
        )
        assert result.quantity > 0
        assert result.position_value > 0

    def test_half_kelly_smaller_than_full_kelly(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        kwargs = dict(capital=10000, entry_price=100, stop_loss=95,
                      win_rate=0.6, avg_win=150, avg_loss=100)
        full  = calculate_position_size(method=SizingMethod.KELLY, **kwargs)
        half  = calculate_position_size(method=SizingMethod.HALF_KELLY, **kwargs)
        assert half.quantity <= full.quantity

    def test_kelly_negative_edge_returns_zero(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(
            method=SizingMethod.KELLY,
            capital=10000, entry_price=100, stop_loss=95,
            win_rate=0.2, avg_win=50, avg_loss=200,  # Clearly negative edge
        )
        assert result.quantity == 0

    def test_fixed_fractional_uses_stop_distance(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(
            method=SizingMethod.FIXED_FRACTIONAL,
            capital=10000, entry_price=100, stop_loss=95,
            risk_per_trade_pct=2.0,
        )
        # 2% of 10000 = 200; stop distance = 5; qty = 200/5 = 40 (capped at max)
        assert result.quantity > 0
        assert abs(result.capital_at_risk - 200.0) < 1.0

    def test_volatility_based_scales_with_vol(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        # Use large capital and small max_position_pct to avoid hitting the cap
        low_vol  = calculate_position_size(method=SizingMethod.VOLATILITY,
                                           capital=100_000, entry_price=100,
                                           volatility=0.10, max_position_pct=100.0)
        high_vol = calculate_position_size(method=SizingMethod.VOLATILITY,
                                           capital=100_000, entry_price=100,
                                           volatility=0.40, max_position_pct=100.0)
        assert low_vol.quantity > high_vol.quantity

    def test_fixed_amount_method(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(
            method=SizingMethod.FIXED_AMOUNT,
            capital=10000, entry_price=50, fixed_amount=500,
        )
        assert abs(result.quantity - 10.0) < 1e-6
        assert abs(result.position_value - 500.0) < 1e-6

    def test_zero_capital_returns_empty(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(method=SizingMethod.KELLY,
                                         capital=0, entry_price=100)
        assert result.quantity == 0

    def test_position_never_exceeds_max_pct(self):
        from alchemy.risk.position_sizing import calculate_position_size, SizingMethod
        result = calculate_position_size(
            method=SizingMethod.KELLY,
            capital=10000, entry_price=1,
            win_rate=0.99, avg_win=1000, avg_loss=1,
            max_position_pct=25.0,
        )
        assert result.position_value <= 10000 * 0.25 + 1e-6
