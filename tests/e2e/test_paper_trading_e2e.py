"""
tests/e2e/test_paper_trading_e2e.py
=====================================
End-to-end tests for the paper trading engine.
Covers: LONG, SHORT, SL/TP, P&L, portfolio value, persistence.

Run: pytest tests/e2e/test_paper_trading_e2e.py -v
"""
import os
import json
import shutil
import tempfile
import pytest

# Set test data dir before any imports
TEST_DIR = tempfile.mkdtemp()
os.environ["ALCHEMY_PAPER_DIR"] = TEST_DIR


@pytest.fixture(autouse=True)
def clean_engine():
    """Reset engine singleton between tests."""
    import alchemy.paper_trading.engine as eng
    eng._engine = None
    yield
    eng._engine = None
    # Cleanup
    for f in os.listdir(TEST_DIR):
        os.remove(os.path.join(TEST_DIR, f))


def get_engine():
    from alchemy.paper_trading.engine import get_paper_engine
    return get_paper_engine()


USER = "test-user-001"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PORTFOLIO BASICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioBasics:

    def test_create_portfolio(self):
        engine = get_engine()
        p = engine.get_portfolio(USER)
        assert p.cash_balance == 100_000.0
        assert p.initial_balance == 100_000.0
        assert len(p.positions) == 0
        assert len(p.trade_log) == 0

    def test_portfolio_value_empty(self):
        engine = get_engine()
        p = engine.get_portfolio(USER)
        assert p.portfolio_value == 100_000.0
        assert p.total_return_pct == 0.0

    def test_reset_portfolio(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 50000, order_type="market")
        p = engine.reset_portfolio(USER, 200_000)
        assert p.cash_balance == 200_000.0
        assert len(p.positions) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LONG POSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestLongPositions:

    def test_buy_creates_long(self):
        engine = get_engine()
        order = engine.place_order(USER, "BTCUSDT", "buy", 0.1, 70000, order_type="market")
        assert order.status.value == "filled"

        p = engine.get_portfolio(USER)
        assert "BTCUSDT" in p.positions
        pos = p.positions["BTCUSDT"]
        assert pos.side.value == "long"
        assert pos.quantity == pytest.approx(0.1, abs=0.001)
        assert p.cash_balance < 100_000  # Cash deducted

    def test_long_pnl_profit(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")

        p = engine.get_portfolio(USER)
        pos = p.positions["BTCUSDT"]
        pos.current_price = 75000  # Price goes up

        assert pos.unrealized_pnl > 0  # Profit
        assert pos.unrealized_pct > 0

    def test_long_pnl_loss(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")

        p = engine.get_portfolio(USER)
        pos = p.positions["BTCUSDT"]
        pos.current_price = 65000  # Price goes down

        assert pos.unrealized_pnl < 0  # Loss

    def test_sell_closes_long(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")
        order = engine.close_position(USER, "BTCUSDT", current_price=72000)

        assert order is not None
        p = engine.get_portfolio(USER)
        assert "BTCUSDT" not in p.positions  # Position closed
        assert len(p.trade_log) == 1  # Trade recorded
        assert p.trade_log[0]["net_pnl"] > 0  # Profit (72K > 70K)
        assert p.realized_pnl > 0

    def test_average_into_long(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 72000, order_type="market")

        p = engine.get_portfolio(USER)
        pos = p.positions["BTCUSDT"]
        assert pos.quantity == pytest.approx(2.0, abs=0.01)
        # Average entry should be between 70K and 72K
        assert 70000 < pos.avg_entry_price < 72000

    def test_portfolio_value_with_long(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")

        p = engine.get_portfolio(USER)
        # Portfolio = cash + position market value
        expected = p.cash_balance + p.positions["BTCUSDT"].market_value
        assert p.portfolio_value == pytest.approx(expected, rel=0.01)

    def test_insufficient_balance_rejected(self):
        engine = get_engine()
        # Try to buy way more than cash allows
        order = engine.place_order(USER, "BTCUSDT", "buy", 100, 70000, order_type="market")
        assert order.status.value == "rejected"
        assert "Insufficient" in order.notes


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SHORT POSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestShortPositions:

    def test_sell_creates_short(self):
        engine = get_engine()
        order = engine.place_order(USER, "ETHUSDT", "sell", 10, 2500, order_type="market")
        assert order.status.value == "filled"

        p = engine.get_portfolio(USER)
        assert "ETHUSDT" in p.positions
        pos = p.positions["ETHUSDT"]
        assert pos.side.value == "short"
        assert pos.quantity == pytest.approx(10, abs=0.1)
        # Cash reduced by margin (50%)
        assert p.cash_balance < 100_000

    def test_short_pnl_profit(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500, order_type="market")

        p = engine.get_portfolio(USER)
        pos = p.positions["ETHUSDT"]
        pos.current_price = 2300  # Price drops → profit for short

        assert pos.unrealized_pnl > 0

    def test_short_pnl_loss(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500, order_type="market")

        p = engine.get_portfolio(USER)
        pos = p.positions["ETHUSDT"]
        pos.current_price = 2700  # Price rises → loss for short

        assert pos.unrealized_pnl < 0

    def test_buy_closes_short(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500, order_type="market")
        order = engine.close_position(USER, "ETHUSDT", current_price=2300)

        assert order is not None
        p = engine.get_portfolio(USER)
        assert "ETHUSDT" not in p.positions
        assert len(p.trade_log) == 1
        assert p.trade_log[0]["side"] == "close_short"
        assert p.trade_log[0]["net_pnl"] > 0  # Profit (sold at 2500, bought back at 2300)

    def test_portfolio_value_with_short(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500, order_type="market")

        p = engine.get_portfolio(USER)
        # SHORT: portfolio = cash + margin_locked + unrealized_pnl
        assert p.portfolio_value < 100_100  # Slightly above/below 100K (fees)
        assert p.portfolio_value > 99_000

    def test_insufficient_margin_rejected(self):
        engine = get_engine()
        # Try to short way more than margin allows
        order = engine.place_order(USER, "BTCUSDT", "sell", 100, 70000, order_type="market")
        assert order.status.value == "rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. STOP-LOSS & TAKE-PROFIT
# ═══════════════════════════════════════════════════════════════════════════════

class TestStopLossTakeProfit:

    def test_long_stop_loss_triggers(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000,
                            order_type="market", stop_loss=68000)

        events = engine.update_prices(USER, {"BTCUSDT": 67000})
        assert any("STOP_LOSS" in e for e in events)

        p = engine.get_portfolio(USER)
        assert "BTCUSDT" not in p.positions  # Position closed

    def test_long_take_profit_triggers(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000,
                            order_type="market", take_profit=75000)

        events = engine.update_prices(USER, {"BTCUSDT": 76000})
        assert any("TAKE_PROFIT" in e for e in events)

        p = engine.get_portfolio(USER)
        assert "BTCUSDT" not in p.positions

    def test_short_stop_loss_triggers(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500,
                            order_type="market", stop_loss=2700)

        events = engine.update_prices(USER, {"ETHUSDT": 2750})
        assert any("STOP_LOSS" in e for e in events)

    def test_short_take_profit_triggers(self):
        engine = get_engine()
        engine.place_order(USER, "ETHUSDT", "sell", 10, 2500,
                            order_type="market", take_profit=2300)

        events = engine.update_prices(USER, {"ETHUSDT": 2250})
        assert any("TAKE_PROFIT" in e for e in events)

    def test_sl_not_triggered_above(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000,
                            order_type="market", stop_loss=68000)

        events = engine.update_prices(USER, {"BTCUSDT": 71000})
        assert len(events) == 0
        p = engine.get_portfolio(USER)
        assert "BTCUSDT" in p.positions  # Still open


# ═══════════════════════════════════════════════════════════════════════════════
# 5. TRADE HISTORY & STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeHistory:

    def test_trade_log_on_close(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 1.0, 70000, order_type="market")
        engine.close_position(USER, "BTCUSDT", current_price=72000)

        p = engine.get_portfolio(USER)
        assert len(p.trade_log) == 1
        t = p.trade_log[0]
        assert t["symbol"] == "BTCUSDT"
        assert t["side"] == "close_long"
        assert t["net_pnl"] > 0
        assert "return_pct" in t
        assert "fee" in t

    def test_win_rate_calculation(self):
        engine = get_engine()

        # Winning trade
        engine.place_order(USER, "BTCUSDT", "buy", 0.1, 70000, order_type="market")
        engine.close_position(USER, "BTCUSDT", current_price=72000)

        # Losing trade
        engine.place_order(USER, "ETHUSDT", "buy", 1.0, 2500, order_type="market")
        engine.close_position(USER, "ETHUSDT", current_price=2400)

        p = engine.get_portfolio(USER)
        summary = p.summary()
        assert summary["total_trades"] == 2
        assert summary["winning_trades"] == 1
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 50.0

    def test_realized_pnl_accumulates(self):
        engine = get_engine()

        engine.place_order(USER, "BTCUSDT", "buy", 0.1, 70000, order_type="market")
        engine.close_position(USER, "BTCUSDT", current_price=72000)

        engine.place_order(USER, "ETHUSDT", "buy", 1.0, 2500, order_type="market")
        engine.close_position(USER, "ETHUSDT", current_price=2600)

        p = engine.get_portfolio(USER)
        assert p.realized_pnl > 0  # Both trades profitable


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:

    def test_save_and_load(self):
        import alchemy.paper_trading.engine as eng

        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        p1 = engine.get_portfolio(USER)
        cash1 = p1.cash_balance
        pos_count1 = len(p1.positions)

        # Reset singleton → force reload from disk
        eng._engine = None
        engine2 = get_engine()
        p2 = engine2.get_portfolio(USER)

        assert p2.cash_balance == pytest.approx(cash1, rel=0.001)
        assert len(p2.positions) == pos_count1
        assert "BTCUSDT" in p2.positions

    def test_trade_log_persists(self):
        import alchemy.paper_trading.engine as eng

        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 0.1, 70000, order_type="market")
        engine.close_position(USER, "BTCUSDT", current_price=72000)

        eng._engine = None
        engine2 = get_engine()
        p = engine2.get_portfolio(USER)
        assert len(p.trade_log) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 7. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_zero_quantity_rejected(self):
        engine = get_engine()
        order = engine.place_order(USER, "BTCUSDT", "buy", 0, 70000, order_type="market")
        assert order.status.value == "rejected"

    def test_zero_price_rejected(self):
        engine = get_engine()
        order = engine.place_order(USER, "BTCUSDT", "buy", 1.0, 0, order_type="market")
        assert order.status.value == "rejected"

    def test_close_nonexistent_position(self):
        engine = get_engine()
        order = engine.close_position(USER, "BTCUSDT", current_price=70000)
        assert order is None

    def test_multiple_users_isolated(self):
        engine = get_engine()
        engine.place_order("user-a", "BTCUSDT", "buy", 1.0, 70000, order_type="market")
        engine.place_order("user-b", "ETHUSDT", "buy", 10, 2500, order_type="market")

        pa = engine.get_portfolio("user-a")
        pb = engine.get_portfolio("user-b")

        assert "BTCUSDT" in pa.positions
        assert "BTCUSDT" not in pb.positions
        assert "ETHUSDT" in pb.positions
        assert "ETHUSDT" not in pa.positions

    def test_partial_close(self):
        engine = get_engine()
        engine.place_order(USER, "BTCUSDT", "buy", 2.0, 70000, order_type="market")
        engine.close_position(USER, "BTCUSDT", current_price=72000, quantity=1.0)

        p = engine.get_portfolio(USER)
        assert "BTCUSDT" in p.positions
        assert p.positions["BTCUSDT"].quantity == pytest.approx(1.0, abs=0.01)
        assert len(p.trade_log) == 1  # Partial close recorded
