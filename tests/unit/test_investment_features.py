"""
tests.unit.test_investment_features
======================================
Tests for P&L segregation, portfolio metrics, position sizing, market sessions.
"""
from datetime import datetime, timezone, timedelta, date

import pytest


# ── CompletedTrade P&L Calculation ────────────────────────────────────────────

class TestCompletedTrade:

    def _make_trade(self, **kwargs):
        from alchemy.analytics.pnl_segregation import AssetClass, CompletedTrade
        defaults = dict(
            symbol="BTCUSDT", exchange="binance", strategy="sma",
            asset_class=AssetClass.CRYPTO_SPOT, side="BUY",
            entry_price=60000, exit_price=62000, quantity=0.1,
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2025, 1, 15, tzinfo=timezone.utc),
            entry_fee=6.0, exit_fee=6.2,
        )
        defaults.update(kwargs)
        return CompletedTrade(**defaults)

    def test_gross_pnl_long(self):
        t = self._make_trade()
        assert t.gross_pnl == 200.0  # (62000-60000)*0.1

    def test_gross_pnl_short(self):
        t = self._make_trade(side="SELL", entry_price=62000, exit_price=60000)
        assert t.gross_pnl == 200.0

    def test_net_pnl_after_fees(self):
        t = self._make_trade()
        assert t.net_pnl == 200.0 - 6.0 - 6.2  # 187.8

    def test_return_pct(self):
        t = self._make_trade()
        capital = 60000 * 0.1  # 6000
        expected = (t.net_pnl / capital) * 100
        assert abs(t.return_pct - expected) < 0.01

    def test_holding_days(self):
        t = self._make_trade()
        assert t.holding_days == 14

    def test_is_winner(self):
        t = self._make_trade()
        assert t.is_winner is True
        t2 = self._make_trade(exit_price=59000)
        assert t2.is_winner is False

    def test_tax_category_stcg_crypto(self):
        from alchemy.analytics.pnl_segregation import TaxCategory
        t = self._make_trade()  # 14 days holding
        assert t.tax_category == TaxCategory.STCG

    def test_tax_category_ltcg(self):
        from alchemy.analytics.pnl_segregation import TaxCategory
        t = self._make_trade(
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
        assert t.tax_category == TaxCategory.LTCG

    def test_estimated_tax_crypto(self):
        t = self._make_trade()
        # 30% flat on crypto profit
        assert abs(t.estimated_tax - t.net_pnl * 0.30) < 0.01

    def test_loss_no_tax(self):
        t = self._make_trade(exit_price=59000)
        assert t.estimated_tax == 0.0


# ── PnL Segregation Engine ───────────────────────────────────────────────────

class TestPnLSegregationEngine:

    def setup_method(self):
        import tempfile
        from alchemy.analytics.pnl_segregation import PnLSegregationEngine
        self.tmpdir = tempfile.mkdtemp()
        self.engine = PnLSegregationEngine(trade_log_dir=self.tmpdir)

    def _add_trade(self, **kwargs):
        from alchemy.analytics.pnl_segregation import AssetClass, CompletedTrade
        defaults = dict(
            symbol="BTCUSDT", exchange="binance", strategy="sma",
            asset_class=AssetClass.CRYPTO_SPOT, side="BUY",
            entry_price=60000, exit_price=62000, quantity=0.1,
            exit_time=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        self.engine.record_trade(CompletedTrade(**defaults))

    def test_record_and_report(self):
        self._add_trade()
        report = self.engine.get_report(group_by="exchange")
        assert report["trade_count"] == 1
        assert len(report["breakdown"]) == 1
        assert report["breakdown"][0]["key"] == "binance"

    def test_group_by_strategy(self):
        self._add_trade(strategy="sma")
        self._add_trade(strategy="ml_ensemble")
        report = self.engine.get_report(group_by="strategy")
        assert len(report["breakdown"]) == 2

    def test_group_by_asset_class(self):
        from alchemy.analytics.pnl_segregation import AssetClass
        self._add_trade(asset_class=AssetClass.CRYPTO_SPOT)
        self._add_trade(asset_class=AssetClass.EQUITY)
        report = self.engine.get_report(group_by="asset_class")
        assert len(report["breakdown"]) == 2

    def test_filter_by_exchange(self):
        self._add_trade(exchange="binance")
        self._add_trade(exchange="delta")
        report = self.engine.get_report(exchange="binance")
        assert report["trade_count"] == 1

    def test_tax_report(self):
        self._add_trade()
        report = self.engine.get_tax_report()
        assert "financial_year" in report
        assert "tax_breakdown" in report
        assert "notes" in report

    def test_stats(self):
        self._add_trade()
        stats = self.engine.stats()
        assert stats["total_completed_trades"] == 1


# ── Portfolio Metrics ─────────────────────────────────────────────────────────

class TestPortfolioMetrics:

    def _make_trades(self, pnls):
        from alchemy.analytics.pnl_segregation import CompletedTrade
        trades = []
        t = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i, pnl in enumerate(pnls):
            entry = 100.0
            exit_p = entry + pnl
            trades.append(CompletedTrade(
                symbol="TEST", exchange="test", side="BUY",
                entry_price=entry, exit_price=exit_p, quantity=1.0,
                entry_time=t + timedelta(days=i),
                exit_time=t + timedelta(days=i+1),
            ))
        return trades

    def test_basic_metrics(self):
        from alchemy.analytics.portfolio_metrics import calculate_portfolio_metrics
        trades = self._make_trades([10, -5, 15, -3, 8])
        m = calculate_portfolio_metrics(trades, initial_capital=1000)
        assert m.total_trades == 5
        assert m.winning_trades == 3
        assert m.losing_trades == 2
        assert m.win_rate == 60.0

    def test_all_winners(self):
        from alchemy.analytics.portfolio_metrics import calculate_portfolio_metrics
        trades = self._make_trades([10, 20, 30])
        m = calculate_portfolio_metrics(trades)
        assert m.win_rate == 100.0
        assert m.max_consecutive_wins == 3

    def test_empty_trades(self):
        from alchemy.analytics.portfolio_metrics import calculate_portfolio_metrics
        m = calculate_portfolio_metrics([])
        assert m.total_trades == 0
        assert m.sharpe_ratio == 0


# ── Position Sizing ───────────────────────────────────────────────────────────

class TestPositionSizing:

    def test_kelly(self):
        from alchemy.risk.position_sizing import SizingMethod, calculate_position_size
        r = calculate_position_size(
            method=SizingMethod.KELLY,
            capital=10000, entry_price=100, stop_loss=95,
            win_rate=0.6, avg_win=150, avg_loss=100,
        )
        assert r.quantity > 0
        assert r.kelly_fraction is not None
        assert r.kelly_fraction > 0

    def test_half_kelly_smaller(self):
        from alchemy.risk.position_sizing import SizingMethod, calculate_position_size
        full = calculate_position_size(
            method=SizingMethod.KELLY, capital=10000,
            entry_price=100, stop_loss=95, win_rate=0.6,
            avg_win=150, avg_loss=100,
        )
        half = calculate_position_size(
            method=SizingMethod.HALF_KELLY, capital=10000,
            entry_price=100, stop_loss=95, win_rate=0.6,
            avg_win=150, avg_loss=100,
        )
        assert half.quantity < full.quantity

    def test_fixed_fractional(self):
        from alchemy.risk.position_sizing import SizingMethod, calculate_position_size
        r = calculate_position_size(
            method=SizingMethod.FIXED_FRACTIONAL,
            capital=10000, entry_price=100, stop_loss=95,
            risk_per_trade_pct=2.0,
        )
        assert r.capital_at_risk <= 200.01  # 2% of 10000

    def test_zero_capital_returns_zero(self):
        from alchemy.risk.position_sizing import SizingMethod, calculate_position_size
        r = calculate_position_size(
            method=SizingMethod.KELLY, capital=0, entry_price=100,
        )
        assert r.quantity == 0


# ── Market Session Manager ────────────────────────────────────────────────────

class TestSessionManager:

    def setup_method(self):
        from alchemy.trading.session_manager import SessionManager
        self.mgr = SessionManager()

    def test_crypto_always_open(self):
        assert self.mgr.is_market_open("binance") is True
        assert self.mgr.is_market_open("delta") is True

    def test_crypto_not_pre_market(self):
        assert self.mgr.is_pre_market("binance") is False

    def test_next_open_crypto(self):
        info = self.mgr.next_open("binance")
        assert info["is_open"] is True

    def test_all_sessions_status(self):
        statuses = self.mgr.all_sessions_status()
        assert len(statuses) > 0
        exchanges = [s.get("exchange") for s in statuses]
        assert "binance" in exchanges

    def test_should_trade_crypto(self):
        allowed, reason = self.mgr.should_trade("binance")
        assert allowed is True

    def test_unknown_exchange_assumed_open(self):
        assert self.mgr.is_market_open("unknown_exchange") is True
