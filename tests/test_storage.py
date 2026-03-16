"""
Tests for src/storage — Database, TradeStore, DecisionStore.
Uses an in-memory SQLite database (':memory:') for isolation.
"""

import pytest
from src.storage.database import Database
from src.storage.trade_store import TradeStore
from src.storage.decision_store import DecisionStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Fresh in-memory database for each test."""
    return Database(":memory:")


@pytest.fixture
def trade_store(db):
    return TradeStore(db)


@pytest.fixture
def decision_store(db):
    return DecisionStore(db)


# ── Database tests ────────────────────────────────────────────────────────────


class TestDatabase:
    def test_create_in_memory(self):
        db = Database(":memory:")
        assert db is not None

    def test_schema_creates_tables(self, db):
        rows = db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r["name"] for r in rows}
        assert "trade_log" in names
        assert "decisions" in names
        assert "equity_snapshots" in names

    def test_execute_insert_and_fetchone(self, db):
        db.execute(
            "INSERT INTO equity_snapshots (ts, balance, total_equity, dry_run) VALUES (?,?,?,?)",
            ("2026-01-01T00:00:00Z", 10000.0, 10000.0, 1),
        )
        row = db.fetchone("SELECT balance FROM equity_snapshots")
        assert row["balance"] == 10000.0

    def test_fetchall_returns_list(self, db):
        result = db.fetchall("SELECT * FROM trade_log")
        assert isinstance(result, list)

    def test_fetchone_returns_none_when_empty(self, db):
        row = db.fetchone("SELECT * FROM trade_log WHERE id=999")
        assert row is None


# ── TradeStore tests ──────────────────────────────────────────────────────────


class TestTradeStore:
    def test_record_returns_id(self, trade_store):
        rid = trade_store.record(symbol="BTCUSD", side="buy", size_usd=500.0)
        assert isinstance(rid, int)
        assert rid > 0

    def test_record_with_full_params(self, trade_store):
        rid = trade_store.record(
            symbol="ETHUSD",
            side="sell",
            size_usd=300.0,
            leverage=5,
            entry_price=3500.0,
            exit_price=3650.0,
            pnl_usd=42.5,
            pnl_pct=14.17,
            fee_usd=5.25,
            stop_loss_pct=2.0,
            take_profit_pct=4.5,
            exit_reason="tp",
            dry_run=True,
        )
        assert rid > 0

    def test_count_increments(self, trade_store):
        assert trade_store.count() == 0
        trade_store.record("BTCUSD", "buy", 500)
        assert trade_store.count() == 1
        trade_store.record("ETHUSD", "sell", 300)
        assert trade_store.count() == 2

    def test_get_recent_returns_list(self, trade_store):
        trade_store.record("BTCUSD", "buy", 500, pnl_usd=20.0)
        rows = trade_store.get_recent(limit=10)
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_get_recent_with_symbol_filter(self, trade_store):
        trade_store.record("BTCUSD", "buy", 500)
        trade_store.record("ETHUSD", "sell", 300)
        btc_rows = trade_store.get_recent(symbol="BTCUSD")
        assert all(r["symbol"] == "BTCUSD" for r in btc_rows)

    def test_get_recent_respects_limit(self, trade_store):
        for _ in range(10):
            trade_store.record("BTCUSD", "buy", 500)
        rows = trade_store.get_recent(limit=3)
        assert len(rows) == 3

    def test_get_recent_ordered_desc(self, trade_store):
        trade_store.record("BTCUSD", "buy", 500, ts="2026-01-01T10:00:00Z")
        trade_store.record("BTCUSD", "buy", 500, ts="2026-01-01T12:00:00Z")
        rows = trade_store.get_recent(limit=2)
        assert rows[0]["ts"] > rows[1]["ts"]

    def test_get_stats_empty(self, trade_store):
        stats = trade_store.get_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate_pct"] == 0.0

    def test_get_stats_with_trades(self, trade_store):
        trade_store.record("BTCUSD", "buy", 500, pnl_usd=50.0, fee_usd=5.0)
        trade_store.record("BTCUSD", "sell", 500, pnl_usd=-20.0, fee_usd=5.0)
        trade_store.record("ETHUSD", "buy", 300, pnl_usd=30.0, fee_usd=3.0)
        stats = trade_store.get_stats()
        assert stats["total_trades"] == 3
        assert stats["winning_trades"] == 2
        assert stats["losing_trades"] == 1
        assert round(stats["win_rate_pct"], 2) == 66.67
        assert stats["total_pnl_usd"] == 60.0
        assert stats["total_fees_usd"] == 13.0
        assert stats["best_trade_usd"] == 50.0
        assert stats["worst_trade_usd"] == -20.0

    def test_record_fields_stored_correctly(self, trade_store):
        trade_store.record(
            "SOLUSD",
            "buy",
            200,
            leverage=10,
            entry_price=185.5,
            exit_price=193.2,
            pnl_usd=15.4,
            exit_reason="tp",
            dry_run=False,
        )
        rows = trade_store.get_recent(limit=1)
        r = rows[0]
        assert r["symbol"] == "SOLUSD"
        assert r["side"] == "buy"
        assert r["leverage"] == 10
        assert r["entry_price"] == 185.5
        assert r["exit_price"] == 193.2
        assert r["exit_reason"] == "tp"
        assert r["dry_run"] == 0

    def test_stats_avg_pnl(self, trade_store):
        trade_store.record("BTCUSD", "buy", 500, pnl_usd=100.0)
        trade_store.record("BTCUSD", "sell", 500, pnl_usd=60.0)
        stats = trade_store.get_stats()
        assert stats["avg_pnl_usd"] == 80.0


# ── DecisionStore tests ───────────────────────────────────────────────────────


class TestDecisionStore:
    def test_record_decision_returns_id(self, decision_store):
        rid = decision_store.record_decision("BTCUSD", "BUY")
        assert isinstance(rid, int) and rid > 0

    def test_record_full_decision(self, decision_store):
        rid = decision_store.record_decision(
            symbol="BTCUSD",
            action="BUY",
            cycle=5,
            confidence=0.78,
            reasoning="Strong uptrend detected",
            emotion_score=0.62,
            geo_risk=0.35,
            forecast_score=0.48,
            market_regime="trending",
            adx=32.5,
            signal_score=0.41,
            dry_run=True,
        )
        assert rid > 0

    def test_count_decisions(self, decision_store):
        assert decision_store.count_decisions() == 0
        decision_store.record_decision("BTCUSD", "BUY")
        assert decision_store.count_decisions() == 1
        decision_store.record_decision("ETHUSD", "HOLD")
        assert decision_store.count_decisions() == 2

    def test_get_recent_decisions(self, decision_store):
        decision_store.record_decision("BTCUSD", "BUY")
        decision_store.record_decision("BTCUSD", "HOLD")
        rows = decision_store.get_recent_decisions(limit=10)
        assert len(rows) == 2

    def test_get_recent_with_symbol_filter(self, decision_store):
        decision_store.record_decision("BTCUSD", "BUY")
        decision_store.record_decision("ETHUSD", "SELL")
        rows = decision_store.get_recent_decisions(symbol="ETHUSD")
        assert all(r["symbol"] == "ETHUSD" for r in rows)

    def test_get_decision_counts(self, decision_store):
        decision_store.record_decision("BTCUSD", "BUY")
        decision_store.record_decision("BTCUSD", "BUY")
        decision_store.record_decision("BTCUSD", "HOLD")
        counts = decision_store.get_decision_counts()
        assert counts.get("BUY") == 2
        assert counts.get("HOLD") == 1

    def test_decision_fields_stored(self, decision_store):
        decision_store.record_decision(
            "BTCUSD",
            "SELL",
            cycle=3,
            confidence=0.65,
            reasoning="Bearish divergence",
            market_regime="volatile",
            adx=28.0,
        )
        rows = decision_store.get_recent_decisions(limit=1)
        r = rows[0]
        assert r["symbol"] == "BTCUSD"
        assert r["action"] == "SELL"
        assert r["cycle"] == 3
        assert abs(r["confidence"] - 0.65) < 1e-9
        assert r["reasoning"] == "Bearish divergence"
        assert r["market_regime"] == "volatile"

    def test_snapshot_equity(self, decision_store):
        rid = decision_store.snapshot_equity(
            balance=10000.0,
            unrealized_pnl=250.0,
            open_positions=2,
            cycle=1,
            dry_run=True,
        )
        assert isinstance(rid, int) and rid > 0

    def test_count_snapshots(self, decision_store):
        assert decision_store.count_snapshots() == 0
        decision_store.snapshot_equity(10000.0)
        assert decision_store.count_snapshots() == 1

    def test_get_equity_history(self, decision_store):
        decision_store.snapshot_equity(10000.0, ts="2026-01-01T10:00:00Z")
        decision_store.snapshot_equity(10500.0, ts="2026-01-01T11:00:00Z")
        rows = decision_store.get_equity_history(limit=10)
        assert len(rows) == 2
        # Most recent first
        assert rows[0]["balance"] == 10500.0

    def test_get_latest_equity(self, decision_store):
        decision_store.snapshot_equity(9800.0, ts="2026-01-01T08:00:00Z")
        decision_store.snapshot_equity(10200.0, ts="2026-01-01T09:00:00Z")
        latest = decision_store.get_latest_equity()
        assert latest["balance"] == 10200.0

    def test_get_latest_equity_none_when_empty(self, decision_store):
        assert decision_store.get_latest_equity() is None

    def test_equity_total_computed(self, decision_store):
        decision_store.snapshot_equity(balance=10000.0, unrealized_pnl=300.0)
        latest = decision_store.get_latest_equity()
        assert latest["total_equity"] == 10300.0

    def test_decisions_limited_by_limit(self, decision_store):
        for i in range(10):
            decision_store.record_decision("BTCUSD", "HOLD", cycle=i)
        rows = decision_store.get_recent_decisions(limit=4)
        assert len(rows) == 4
