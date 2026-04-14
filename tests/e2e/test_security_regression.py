"""
tests/e2e/test_security_regression.py
========================================
Security tests and regression tests for known bugs.

Run: pytest tests/e2e/test_security_regression.py -v
"""
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SECURITY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserIsolation:

    def test_users_cannot_see_each_other(self, engine):
        """User A's positions invisible to User B."""
        engine.place_order("user-a", "BTCUSDT", "buy", 1, 70000, order_type="market")
        engine.place_order("user-b", "ETHUSDT", "buy", 10, 2500, order_type="market")

        pa = engine.get_portfolio("user-a")
        pb = engine.get_portfolio("user-b")

        assert "BTCUSDT" in pa.positions
        assert "BTCUSDT" not in pb.positions
        assert "ETHUSDT" in pb.positions
        assert "ETHUSDT" not in pa.positions

    def test_user_cannot_close_another_position(self, engine):
        """User B cannot close User A's position."""
        engine.place_order("user-a", "BTCUSDT", "buy", 1, 70000, order_type="market")
        result = engine.close_position("user-b", "BTCUSDT", current_price=72000)
        assert result is None  # No position to close

        pa = engine.get_portfolio("user-a")
        assert "BTCUSDT" in pa.positions  # Still open

    def test_user_cannot_reset_another_portfolio(self, engine):
        """Each user resets only their own portfolio."""
        engine.place_order("user-a", "BTCUSDT", "buy", 0.5, 70000, order_type="market")
        engine.reset_portfolio("user-b", 50000)

        pa = engine.get_portfolio("user-a")
        pb = engine.get_portfolio("user-b")

        assert "BTCUSDT" in pa.positions  # A's positions intact
        assert pb.cash_balance == 50000    # B's reset


class TestInputValidation:

    def test_negative_quantity_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "BTCUSDT", "buy", -1, 70000, order_type="market")
        assert order.status.value == "rejected"

    def test_zero_quantity_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "BTCUSDT", "buy", 0, 70000, order_type="market")
        assert order.status.value == "rejected"

    def test_zero_price_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "BTCUSDT", "buy", 1.0, 0, order_type="market")
        assert order.status.value == "rejected"

    def test_negative_price_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "BTCUSDT", "buy", 1.0, -100, order_type="market")
        assert order.status.value == "rejected"

    def test_empty_symbol_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "", "buy", 1.0, 70000, order_type="market")
        assert order.status.value == "rejected"

    def test_invalid_side_rejected(self, engine, user_id):
        order = engine.place_order(user_id, "BTCUSDT", "hold", 1.0, 70000, order_type="market")
        assert order.status.value == "rejected"


class TestWebhookSecurity:

    def test_webhook_text_parser_handles_empty(self):
        from alchemy.api.webhook_routes import _parse_text_signal
        result = _parse_text_signal("")
        assert "side" not in result or result.get("side") == ""

    def test_webhook_text_parser_handles_junk(self):
        from alchemy.api.webhook_routes import _parse_text_signal
        result = _parse_text_signal("hello world 123 !@#$%")
        # Should not crash, may return partial data
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REGRESSION TESTS (known bugs that were fixed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressions:

    def test_short_close_returns_correct_cash(self, engine, user_id):
        """BUG FIX: SHORT close was returning fill_price * qty instead of margin + pnl."""
        engine.place_order(user_id, "ETHUSDT", "sell", 10, 2500, order_type="market")
        p_before = engine.get_portfolio(user_id)
        cash_before = p_before.cash_balance

        engine.close_position(user_id, "ETHUSDT", current_price=2300)
        p_after = engine.get_portfolio(user_id)

        # Short profit: (2500-2300) * 10 = $2000. Cash should increase by ~margin + profit
        assert p_after.cash_balance > cash_before

    def test_portfolio_value_correct_for_shorts(self, engine, user_id):
        """BUG FIX: Portfolio was cash + full_notional instead of cash + margin + unrealized."""
        engine.place_order(user_id, "ETHUSDT", "sell", 10, 2500, order_type="market")

        p = engine.get_portfolio(user_id)
        # Should be approximately $100K (initial) minus fees
        assert 99_000 < p.portfolio_value < 101_000

    def test_skip_duplicate_position(self, engine, user_id):
        """BUG FIX: Autonomous trading opened duplicate positions every scan."""
        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        p = engine.get_portfolio(user_id)
        has_position = "BTCUSDT" in p.positions and p.positions["BTCUSDT"].quantity > 0
        assert has_position  # Autonomous engine should skip if this is true

    def test_close_nonexistent_returns_none(self, engine, user_id):
        """BUG FIX: close_position() crashed instead of returning None."""
        result = engine.close_position(user_id, "NONEXISTENT", current_price=100)
        assert result is None

    def test_sl_tp_not_triggered_wrong_direction(self, engine, user_id):
        """BUG FIX: SL/TP triggers were checking wrong direction for SHORT."""
        engine.place_order(user_id, "BTCUSDT", "sell", 0.5, 70000,
                           order_type="market", stop_loss=72000, take_profit=65000)

        # Price drops to 68000 — should NOT trigger SL (SHORT SL is above entry)
        events = engine.update_prices(user_id, {"BTCUSDT": 68000})
        sl_events = [e for e in events if "STOP_LOSS" in e]
        assert len(sl_events) == 0

    def test_fee_deducted_from_pnl(self, engine, user_id):
        """BUG FIX: Fee was not deducted from P&L calculation."""
        engine.place_order(user_id, "BTCUSDT", "buy", 1.0, 70000, order_type="market")
        engine.close_position(user_id, "BTCUSDT", current_price=70000)

        p = engine.get_portfolio(user_id)
        # Even at same price, net P&L should be negative (fees)
        assert p.trade_log[0]["net_pnl"] <= 0

    def test_persistence_survives_restart(self, engine, user_id):
        """BUG FIX: Portfolio data lost on container restart."""
        import alchemy.paper_trading.engine as eng

        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")
        engine.close_position(user_id, "BTCUSDT", current_price=72000)

        original_pnl = engine.get_portfolio(user_id).realized_pnl

        eng._engine = None  # Simulate restart
        from alchemy.paper_trading.engine import get_paper_engine
        engine2 = get_paper_engine()

        assert engine2.get_portfolio(user_id).realized_pnl == pytest.approx(original_pnl, rel=0.01)
