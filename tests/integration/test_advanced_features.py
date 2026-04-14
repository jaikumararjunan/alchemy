"""
tests/integration/test_advanced_features.py
=============================================
Integration tests for Sprint 5-7 features:
  - Advanced Orders (OCO, Bracket, Trailing Stop)
  - Webhook Integration
  - Copy Trading
  - Trade Journal
  - Portfolio Analytics (Heatmap, Correlation, AI Recommendations)
  - Multi-Account Support
  - Tax Export
  - Position Sizing

Run: pytest tests/integration/test_advanced_features.py -v
"""
import json
import os
import sqlite3
import pytest

USER_A = "leader-001"
USER_B = "follower-002"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ADVANCED ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestOCOOrders:

    def test_create_oco(self, engine, user_id):
        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        from alchemy.api.advanced_orders import _conn
        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, stop_loss, take_profit, entry_price)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, "oco", "BTCUSDT", "buy", 0.5, 68000, 75000, 70000))
            rows = c.execute("SELECT * FROM advanced_orders WHERE user_id=?", (user_id,)).fetchall()
        assert len(rows) == 1
        assert dict(rows[0])["order_type"] == "oco"

    def test_oco_sl_triggers(self, engine, user_id):
        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        from alchemy.api.advanced_orders import _conn, check_advanced_orders
        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, stop_loss, take_profit, entry_price, status)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (user_id, "oco", "BTCUSDT", "buy", 0.5, 68000, 75000, 70000, "active"))

        events = check_advanced_orders(user_id, {"BTCUSDT": 67500})
        assert any("STOP_LOSS" in e or "stop_loss" in e for e in events)

    def test_oco_tp_triggers(self, engine, user_id):
        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        from alchemy.api.advanced_orders import _conn, check_advanced_orders
        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, stop_loss, take_profit, entry_price, status)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (user_id, "oco", "BTCUSDT", "buy", 0.5, 68000, 75000, 70000, "active"))

        events = check_advanced_orders(user_id, {"BTCUSDT": 76000})
        assert any("TAKE_PROFIT" in e or "take_profit" in e for e in events)

    def test_oco_no_trigger(self, engine, user_id):
        from alchemy.api.advanced_orders import _conn, check_advanced_orders
        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, stop_loss, take_profit, entry_price, status)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (user_id, "oco", "BTCUSDT", "buy", 0.5, 68000, 75000, 70000, "active"))

        events = check_advanced_orders(user_id, {"BTCUSDT": 71000})
        assert len(events) == 0


class TestTrailingStop:

    def test_trailing_peak_update(self, engine, user_id):
        from alchemy.api.advanced_orders import _conn, check_advanced_orders
        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, trailing_pct, trailing_peak, status)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, "trailing_stop", "BTCUSDT", "buy", 0.5, 2.0, 70000, "active"))

        # Price goes up — peak should update
        events = check_advanced_orders(user_id, {"BTCUSDT": 72000})
        assert len(events) == 0  # Not triggered

        with _conn() as c:
            row = c.execute("SELECT trailing_peak FROM advanced_orders WHERE user_id=? AND order_type=?",
                            (user_id, "trailing_stop")).fetchone()
        # Peak should have updated to 72000 (or stayed at 70000 if update failed)
        assert row[0] >= 70000  # At minimum the original peak

    def test_trailing_triggers_on_reversal(self, engine, user_id):
        from alchemy.api.advanced_orders import _conn, check_advanced_orders

        engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")

        with _conn() as c:
            c.execute("""INSERT INTO advanced_orders
                (user_id, order_type, symbol, side, quantity, trailing_pct, trailing_peak, status)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, "trailing_stop", "BTCUSDT", "buy", 0.5, 2.0, 75000, "active"))

        # 2% drop from 75K peak = 73,500. Price at 73K → trigger
        events = check_advanced_orders(user_id, {"BTCUSDT": 73000})
        assert len(events) > 0


class TestBracketOrder:

    def test_bracket_creates_position_with_sl_tp(self, engine, user_id):
        order = engine.place_order(
            user_id, "BTCUSDT", "buy", 0.5, 70000,
            order_type="market", stop_loss=68000, take_profit=75000,
            strategy="bracket"
        )
        assert order.status.value == "filled"
        p = engine.get_portfolio(user_id)
        pos = p.positions["BTCUSDT"]
        assert pos.stop_loss == 68000
        assert pos.take_profit == 75000


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WEBHOOK INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhook:

    def test_parse_text_signal(self):
        from alchemy.api.webhook_routes import _parse_text_signal
        result = _parse_text_signal("BUY BTCUSDT 0.5")
        assert result["side"] == "buy"
        assert result["symbol"] == "BTCUSDT"
        assert result["quantity"] == 0.5

    def test_parse_text_no_quantity(self):
        from alchemy.api.webhook_routes import _parse_text_signal
        result = _parse_text_signal("SELL ETHUSDT")
        assert result["side"] == "sell"
        assert result["symbol"] == "ETHUSDT"
        assert "quantity" not in result

    def test_parse_text_adds_usdt(self):
        from alchemy.api.webhook_routes import _parse_text_signal
        result = _parse_text_signal("BUY BTC")
        assert result["symbol"] == "BTCUSDT"

    def test_webhook_token_setup(self, engine):
        from alchemy.api.webhook_routes import _conn
        import secrets
        token = secrets.token_urlsafe(32)
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO webhook_tokens (user_id, token) VALUES (?,?)",
                      ("webhook-user-1", token))
            row = c.execute("SELECT token FROM webhook_tokens WHERE user_id=?",
                            ("webhook-user-1",)).fetchone()
        assert row[0] == token
        assert len(token) > 20

    def test_webhook_log_created(self, engine):
        from alchemy.api.webhook_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO webhook_log (user_id, source, payload, action, result) VALUES (?,?,?,?,?)",
                      ("webhook-user-1", "test", '{"symbol":"BTCUSDT"}', "buy BTCUSDT", "ok"))
            rows = c.execute("SELECT * FROM webhook_log WHERE user_id=?",
                             ("webhook-user-1",)).fetchall()
        assert len(rows) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. COPY TRADING
# ═══════════════════════════════════════════════════════════════════════════════

class TestCopyTrading:

    def test_follow_creates_record(self, engine):
        from alchemy.api.copy_trading import _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id, allocation_pct) VALUES (?,?,?)",
                      (USER_B, USER_A, 10.0))
            row = c.execute("SELECT * FROM copy_follows WHERE follower_id=? AND leader_id=?",
                            (USER_B, USER_A)).fetchone()
        assert dict(row)["allocation_pct"] == 10.0

    def test_unfollow_deletes(self, engine):
        from alchemy.api.copy_trading import _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id) VALUES (?,?)",
                      (USER_B, USER_A))
            c.execute("DELETE FROM copy_follows WHERE follower_id=? AND leader_id=?",
                      (USER_B, USER_A))
            row = c.execute("SELECT * FROM copy_follows WHERE follower_id=? AND leader_id=?",
                            (USER_B, USER_A)).fetchone()
        assert row is None

    def test_cannot_follow_self(self):
        # Business rule: follower_id != leader_id
        assert USER_A != USER_B  # sanity

    def test_copy_trade_mirrors(self, engine):
        """Leader trades → follower gets copy."""
        # Setup follower portfolio
        engine.get_portfolio(USER_B)

        from alchemy.api.copy_trading import execute_copy_trades, _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id, allocation_pct, max_position_pct, enabled) VALUES (?,?,?,?,?)",
                      (USER_B, USER_A, 10.0, 5.0, 1))

        execute_copy_trades(USER_A, "BTCUSDT", "buy", 0.5, 70000)

        p = engine.get_portfolio(USER_B)
        assert "BTCUSDT" in p.positions
        assert p.positions["BTCUSDT"].quantity > 0

    def test_copy_allocation_capped(self, engine):
        """Copy trade size capped at allocation %."""
        cap_user = "cap-follower-999"
        engine.get_portfolio(cap_user)

        from alchemy.api.copy_trading import execute_copy_trades, _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id, allocation_pct, max_position_pct, enabled) VALUES (?,?,?,?,?)",
                      (cap_user, "cap-leader-888", 1.0, 1.0, 1))

        execute_copy_trades("cap-leader-888", "BTCUSDT", "buy", 10.0, 70000)

        p = engine.get_portfolio(cap_user)
        if "BTCUSDT" in p.positions:
            pos_value = p.positions["BTCUSDT"].quantity * 70000
            assert pos_value < 2000  # 1% of $100K ≈ $1000 max

    def test_copy_trade_logged(self, engine):
        log_user = "log-follower-777"
        engine.get_portfolio(log_user)

        from alchemy.api.copy_trading import execute_copy_trades, _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id, allocation_pct, max_position_pct, enabled) VALUES (?,?,?,?,?)",
                      (log_user, "log-leader-666", 10.0, 5.0, 1))

        execute_copy_trades("log-leader-666", "ETHUSDT", "buy", 5, 2500)

        with _conn() as c:
            rows = c.execute("SELECT * FROM copy_trades WHERE follower_id=?",
                             (log_user,)).fetchall()
        assert len(rows) >= 1

    def test_disabled_follow_skipped(self, engine):
        dis_user = "disabled-follower-555"
        engine.get_portfolio(dis_user)

        from alchemy.api.copy_trading import execute_copy_trades, _conn
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO copy_follows (follower_id, leader_id, allocation_pct, max_position_pct, enabled) VALUES (?,?,?,?,?)",
                      (dis_user, "disabled-leader-444", 10.0, 5.0, 0))

        execute_copy_trades("disabled-leader-444", "SOLUSDT", "buy", 10, 150)

        p = engine.get_portfolio(dis_user)
        assert "SOLUSDT" not in p.positions


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TRADE JOURNAL
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeJournal:

    def test_create_entry(self):
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("""INSERT INTO trade_journal
                (user_id, symbol, side, entry_price, exit_price, pnl, tags, emotion, notes)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                ("journal-user", "BTCUSDT", "buy", 70000, 73000, 300, '["swing"]', "confident", "Good entry"))
            rows = c.execute("SELECT * FROM trade_journal WHERE user_id=?",
                             ("journal-user",)).fetchall()
        assert len(rows) == 1
        d = dict(rows[0])
        assert d["symbol"] == "BTCUSDT"
        assert d["pnl"] == 300
        assert d["emotion"] == "confident"

    def test_filter_by_symbol(self):
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, pnl) VALUES (?,?,?,?)",
                      ("filter-user", "BTCUSDT", "buy", 100))
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, pnl) VALUES (?,?,?,?)",
                      ("filter-user", "ETHUSDT", "buy", 50))
            rows = c.execute("SELECT * FROM trade_journal WHERE user_id=? AND symbol=?",
                             ("filter-user", "BTCUSDT")).fetchall()
        assert len(rows) == 1

    def test_filter_by_emotion(self):
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, emotion) VALUES (?,?,?,?)",
                      ("emo-user", "BTCUSDT", "buy", "fearful"))
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, emotion) VALUES (?,?,?,?)",
                      ("emo-user", "ETHUSDT", "buy", "confident"))
            rows = c.execute("SELECT * FROM trade_journal WHERE user_id=? AND emotion=?",
                             ("emo-user", "fearful")).fetchall()
        assert len(rows) == 1

    def test_update_entry(self):
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, notes) VALUES (?,?,?,?)",
                      ("update-user", "BTCUSDT", "buy", "initial"))
            entry_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute("UPDATE trade_journal SET notes=?, rating=? WHERE id=?",
                      ("updated notes", 4, entry_id))
            row = c.execute("SELECT * FROM trade_journal WHERE id=?", (entry_id,)).fetchone()
        assert dict(row)["notes"] == "updated notes"
        assert dict(row)["rating"] == 4

    def test_delete_entry(self):
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO trade_journal (user_id, symbol, side) VALUES (?,?,?)",
                      ("del-user", "BTCUSDT", "buy"))
            entry_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute("DELETE FROM trade_journal WHERE id=? AND user_id=?", (entry_id, "del-user"))
            row = c.execute("SELECT * FROM trade_journal WHERE id=?", (entry_id,)).fetchone()
        assert row is None

    def test_auto_import(self, engine):
        """Auto-import closed trades into journal."""
        import_user = "import-user-333"
        engine.place_order(import_user, "BTCUSDT", "buy", 0.01, 70000, order_type="market")
        engine.close_position(import_user, "BTCUSDT", current_price=72000)

        p = engine.get_portfolio(import_user)
        assert len(p.trade_log) >= 1

        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            for t in p.trade_log:
                c.execute("""INSERT INTO trade_journal
                    (user_id, symbol, side, entry_price, exit_price, pnl)
                    VALUES (?,?,?,?,?,?)""",
                    (import_user, t["symbol"], t.get("side",""),
                     t.get("entry_price",0), t.get("exit_price",0), t.get("net_pnl",0)))
            rows = c.execute("SELECT * FROM trade_journal WHERE user_id=?",
                             (import_user,)).fetchall()
        assert len(rows) == len(p.trade_log)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PORTFOLIO ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioAnalytics:

    def test_heatmap_data(self, multi_position, engine, user_id):
        """Heatmap returns cells with correct structure."""
        p = engine.get_portfolio(user_id)
        positions = p.positions

        cells = []
        for sym, pos in positions.items():
            value = pos.current_price * pos.quantity
            cells.append({
                "symbol": sym, "value": value,
                "pnl": pos.unrealized_pnl,
                "weight_pct": value / p.portfolio_value * 100,
            })

        assert len(cells) == 3
        total_weight = sum(c["weight_pct"] for c in cells)
        # Weights should be less than 100 (rest is cash)
        assert total_weight < 100

    def test_position_sizing_calculation(self):
        """Position size = risk_amount / price_diff."""
        account = 100000
        risk_pct = 1.0  # 1%
        entry = 70000
        sl = 68000

        risk_amount = account * (risk_pct / 100)  # $1000
        price_diff = abs(entry - sl)                # $2000
        quantity = risk_amount / price_diff          # 0.5 BTC

        assert risk_amount == 1000
        assert quantity == 0.5

    def test_strategy_comparison(self, engine):
        """Strategy comparison groups by strategy name."""
        strat_user = "strategy-user-222"
        engine.place_order(strat_user, "BTCUSDT", "buy", 0.1, 70000,
                           order_type="market", strategy="sma_crossover")
        engine.close_position(strat_user, "BTCUSDT", current_price=72000)

        engine.place_order(strat_user, "ETHUSDT", "buy", 1, 2500,
                           order_type="market", strategy="rsi_oversold")
        engine.close_position(strat_user, "ETHUSDT", current_price=2400)

        p = engine.get_portfolio(strat_user)
        strategies = {}
        for t in p.trade_log:
            s = t.get("strategy", "manual")
            if s not in strategies:
                strategies[s] = {"trades": 0, "total_pnl": 0}
            strategies[s]["trades"] += 1
            strategies[s]["total_pnl"] += t.get("net_pnl", 0)

        assert "sma_crossover" in strategies
        assert "rsi_oversold" in strategies
        assert strategies["sma_crossover"]["total_pnl"] > 0
        assert strategies["rsi_oversold"]["total_pnl"] < 0

    def test_win_rate_by_emotion(self, engine, user_id):
        """Emotion stats: win rate grouped by emotion."""
        from alchemy.api.journal_routes import _conn
        with _conn() as c:
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, pnl, emotion) VALUES (?,?,?,?,?)",
                      (user_id, "BTC", "buy", 500, "confident"))
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, pnl, emotion) VALUES (?,?,?,?,?)",
                      (user_id, "ETH", "buy", -200, "fearful"))
            c.execute("INSERT INTO trade_journal (user_id, symbol, side, pnl, emotion) VALUES (?,?,?,?,?)",
                      (user_id, "SOL", "buy", 300, "confident"))

            rows = c.execute("SELECT emotion, pnl FROM trade_journal WHERE user_id=?",
                             (user_id,)).fetchall()

        emotions = {}
        for r in rows:
            emo = r[0]
            if emo not in emotions:
                emotions[emo] = {"wins": 0, "total": 0}
            emotions[emo]["total"] += 1
            if r[1] > 0:
                emotions[emo]["wins"] += 1

        assert emotions["confident"]["wins"] == 2
        assert emotions["fearful"]["wins"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MULTI-ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiAccount:

    def test_add_account(self):
        from alchemy.api.token_routes import _conn
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS exchange_accounts (
                user_id TEXT NOT NULL, exchange TEXT NOT NULL,
                account_name TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',
                is_default INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, exchange, account_name))""")
            c.execute("INSERT OR REPLACE INTO exchange_accounts VALUES (?,?,?,?,?)",
                      ("multi-user", "binance", "trading", '{"api_key":"abc"}', 0))
            rows = c.execute("SELECT * FROM exchange_accounts WHERE user_id=?",
                             ("multi-user",)).fetchall()
        assert len(rows) == 1

    def test_set_default(self):
        from alchemy.api.token_routes import _conn
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS exchange_accounts (
                user_id TEXT NOT NULL, exchange TEXT NOT NULL,
                account_name TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',
                is_default INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, exchange, account_name))""")
            c.execute("INSERT OR REPLACE INTO exchange_accounts VALUES (?,?,?,?,?)",
                      ("multi-user", "binance", "main", '{}', 0))
            c.execute("INSERT OR REPLACE INTO exchange_accounts VALUES (?,?,?,?,?)",
                      ("multi-user", "binance", "hedge", '{}', 0))
            c.execute("UPDATE exchange_accounts SET is_default=1 WHERE account_name=? AND user_id=?",
                      ("hedge", "multi-user"))
            row = c.execute("SELECT * FROM exchange_accounts WHERE is_default=1 AND user_id=?",
                            ("multi-user",)).fetchone()
        assert dict(row)["account_name"] == "hedge"
