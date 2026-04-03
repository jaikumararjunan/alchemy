"""
alchemy.analytics_db.store
============================
Local SQLite analytics database — per-user trade and intelligence storage.

Tables:
  trades           — All executed trades with full context
  intelligence_signals — Market intelligence signals
  ei_states        — Emotional intelligence readings
  strategy_performance — Per-strategy P&L analytics
  video_summaries  — YouTube market video summaries
  price_alerts     — User-configured price alert history
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import structlog

log = structlog.get_logger(__name__)

DB_PATH = Path("./data/alchemy_analytics.db")


class AnalyticsDB:
    """Thread-safe SQLite analytics store. One DB per deployment (multi-user)."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT,
                strategy TEXT,
                direction TEXT,
                quantity REAL,
                entry_price REAL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                pnl REAL,
                pnl_pct REAL,
                fees REAL DEFAULT 0,
                outcome TEXT,
                status TEXT DEFAULT 'open',
                timeframe TEXT,
                market_bias TEXT,
                fear_greed_index REAL,
                emotional_regime TEXT,
                intelligence_signals TEXT,
                reasoning TEXT,
                notes TEXT,
                opened_at TEXT,
                closed_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                workflow_id TEXT
            );

            CREATE TABLE IF NOT EXISTS intelligence_signals (
                id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                summary TEXT,
                market_impact TEXT,
                impact_score REAL,
                affected_sectors TEXT,
                affected_symbols TEXT,
                geopolitical INTEGER DEFAULT 0,
                urgency TEXT,
                confidence REAL,
                source_url TEXT,
                raw_data TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ei_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                fear_greed_index REAL,
                regime TEXT,
                vix_score REAL,
                momentum_score REAL,
                news_score REAL,
                recommended_sizing REAL,
                trader_emotion TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT,
                exchange TEXT,
                trades_count INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                avg_pnl_pct REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_rr REAL DEFAULT 0,
                best_trade_pnl REAL DEFAULT 0,
                worst_trade_pnl REAL DEFAULT 0,
                month TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS video_summaries (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                channel TEXT,
                duration_s INTEGER,
                market_direction TEXT,
                key_stocks TEXT,
                trading_ideas TEXT,
                confidence REAL,
                processed_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trades_user    ON trades(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol  ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_outcome ON trades(outcome);
            CREATE INDEX IF NOT EXISTS idx_ei_user        ON ei_states(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_intel_impact   ON intelligence_signals(impact_score, created_at);
            """)
        log.info("analytics_db.initialized", path=str(self.db_path))

    # ── Trade recording ───────────────────────────────────────────────────────

    def record_trade(self, trade_data: dict) -> str:
        """Insert or update a trade record."""
        import uuid
        trade_id = trade_data.get("id") or str(uuid.uuid4())[:12]
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades
                (id, user_id, symbol, exchange, strategy, direction, quantity,
                 entry_price, exit_price, stop_loss, take_profit, pnl, pnl_pct,
                 fees, outcome, status, timeframe, market_bias, fear_greed_index,
                 emotional_regime, intelligence_signals, reasoning, notes,
                 opened_at, closed_at, workflow_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade_id, trade_data.get("user_id",""), trade_data.get("symbol",""),
                trade_data.get("exchange",""), trade_data.get("strategy",""),
                trade_data.get("direction",""), trade_data.get("quantity",0),
                trade_data.get("entry_price",0), trade_data.get("exit_price"),
                trade_data.get("stop_loss",0), trade_data.get("take_profit",0),
                trade_data.get("pnl",0), trade_data.get("pnl_pct",0),
                trade_data.get("fees",0), trade_data.get("outcome",""),
                trade_data.get("status","open"), trade_data.get("timeframe",""),
                trade_data.get("market_bias","neutral"),
                trade_data.get("fear_greed_index",50),
                trade_data.get("emotional_regime","neutral"),
                json.dumps(trade_data.get("intelligence_signals",[])),
                trade_data.get("reasoning",""), trade_data.get("notes",""),
                trade_data.get("opened_at", datetime.now(timezone.utc).isoformat()),
                trade_data.get("closed_at"), trade_data.get("workflow_id",""),
            ))
        self._update_strategy_performance(trade_data)
        return trade_id

    def get_user_trades(self, user_id: str, limit: int = 100,
                         symbol: Optional[str] = None,
                         strategy: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            q = "SELECT * FROM trades WHERE user_id=?"
            params: list[Any] = [user_id]
            if symbol:   q += " AND symbol=?";   params.append(symbol)
            if strategy: q += " AND strategy=?"; params.append(strategy)
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def get_user_pnl_summary(self, user_id: str, days: int = 30) -> dict:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT outcome, COUNT(*) as count, SUM(pnl) as total_pnl,
                       AVG(pnl_pct) as avg_pnl_pct,
                       MAX(pnl) as best, MIN(pnl) as worst
                FROM trades
                WHERE user_id=? AND closed_at >= datetime('now', ?)
                GROUP BY outcome
            """, (user_id, f"-{days} days")).fetchall()
            totals = conn.execute("""
                SELECT COUNT(*) as total_trades, SUM(pnl) as net_pnl,
                       SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                       SUM(fees) as total_fees
                FROM trades
                WHERE user_id=? AND closed_at >= datetime('now', ?)
            """, (user_id, f"-{days} days")).fetchone()
        summary = {
            "by_outcome": [dict(r) for r in rows],
            "totals":     dict(totals) if totals else {},
            "period_days": days,
        }
        if totals and totals["total_trades"]:
            summary["win_rate"] = totals["wins"] / totals["total_trades"]
        return summary

    # ── Intelligence signals ──────────────────────────────────────────────────

    def save_signal(self, signal) -> None:
        """Save a MarketSignal to the intelligence table."""
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO intelligence_signals
                (id, source, title, summary, market_impact, impact_score,
                 affected_sectors, affected_symbols, geopolitical, urgency,
                 confidence, source_url, raw_data, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                signal.id, signal.source, signal.title, signal.summary,
                signal.market_impact, signal.impact_score,
                json.dumps(signal.affected_sectors),
                json.dumps(signal.affected_symbols),
                1 if signal.geopolitical else 0,
                signal.urgency, signal.confidence, signal.source_url,
                json.dumps(signal.raw_data),
                signal.created_at.isoformat(),
            ))

    def get_recent_signals(self, limit: int = 50, geo_only: bool = False) -> list[dict]:
        with self._conn() as conn:
            q = "SELECT * FROM intelligence_signals"
            if geo_only: q += " WHERE geopolitical=1"
            q += " ORDER BY created_at DESC LIMIT ?"
            rows = conn.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── EI states ─────────────────────────────────────────────────────────────

    def save_ei_state(self, user_id: str, state: dict) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ei_states
                (user_id, fear_greed_index, regime, vix_score, momentum_score,
                 news_score, recommended_sizing, trader_emotion, notes)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (user_id, state.get("fear_greed_index",50), state.get("regime","neutral"),
                  state.get("vix_score",50), state.get("momentum_score",50),
                  state.get("news_score",50), state.get("recommended_sizing",1.0),
                  state.get("trader_emotion","calm"), state.get("notes","")))

    def get_ei_history(self, user_id: str, limit: int = 30) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM ei_states WHERE user_id=?
                ORDER BY created_at DESC LIMIT ?
            """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── Video summaries ───────────────────────────────────────────────────────

    def save_video_summary(self, video_id: str, data: dict) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO video_summaries
                (id, url, title, channel, market_direction, key_stocks, trading_ideas, confidence)
                VALUES (?,?,?,?,?,?,?,?)
            """, (video_id, data.get("url",""), data.get("title",""),
                  data.get("channel",""), data.get("market_direction","neutral"),
                  json.dumps(data.get("key_stocks",[])),
                  json.dumps(data.get("trading_ideas",[])),
                  data.get("confidence",0.5)))

    # ── Strategy performance ──────────────────────────────────────────────────

    def _update_strategy_performance(self, trade: dict) -> None:
        if not trade.get("closed_at"):
            return
        user_id  = trade.get("user_id","")
        strategy = trade.get("strategy","")
        month    = trade.get("closed_at","")[:7]  # YYYY-MM

        with self._conn() as conn:
            existing = conn.execute("""
                SELECT * FROM strategy_performance
                WHERE user_id=? AND strategy=? AND month=?
            """, (user_id, strategy, month)).fetchone()

            pnl     = trade.get("pnl",0)
            pnl_pct = trade.get("pnl_pct",0)
            is_win  = pnl > 0

            if existing:
                trades = existing["trades_count"] + 1
                wins   = existing["wins"] + (1 if is_win else 0)
                losses = existing["losses"] + (0 if is_win else 1)
                total  = existing["total_pnl"] + pnl
                conn.execute("""
                    UPDATE strategy_performance
                    SET trades_count=?, wins=?, losses=?, total_pnl=?,
                        avg_pnl_pct=?, win_rate=?,
                        best_trade_pnl=MAX(?,?), worst_trade_pnl=MIN(?,?),
                        updated_at=datetime('now')
                    WHERE user_id=? AND strategy=? AND month=?
                """, (trades, wins, losses, total, total/trades, wins/trades,
                      existing["best_trade_pnl"], pnl, existing["worst_trade_pnl"], pnl,
                      user_id, strategy, month))
            else:
                conn.execute("""
                    INSERT INTO strategy_performance
                    (user_id,strategy,trades_count,wins,losses,total_pnl,avg_pnl_pct,win_rate,
                     best_trade_pnl,worst_trade_pnl,month)
                    VALUES (?,?,1,?,?,?,?,?,?,?,?)
                """, (user_id, strategy, 1 if is_win else 0, 0 if is_win else 1,
                      pnl, pnl_pct, 1.0 if is_win else 0.0, pnl, pnl, month))

    def get_strategy_performance(self, user_id: str, months: int = 3) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT strategy,
                       SUM(trades_count) as total_trades,
                       SUM(wins) as total_wins,
                       SUM(total_pnl) as net_pnl,
                       AVG(avg_pnl_pct) as avg_pnl_pct,
                       AVG(win_rate) as avg_win_rate
                FROM strategy_performance
                WHERE user_id=? AND month >= date('now',?)
                GROUP BY strategy ORDER BY net_pnl DESC
            """, (user_id, f"-{months} months")).fetchall()
        return [dict(r) for r in rows]


# Singleton
_db: Optional[AnalyticsDB] = None

def get_analytics_db() -> AnalyticsDB:
    global _db
    if _db is None:
        _db = AnalyticsDB()
    return _db


class IntelligenceStore:
    """Convenience wrapper for signal storage."""
    def __init__(self): self._db = get_analytics_db()
    def save_signal(self, signal): self._db.save_signal(signal)
    def get_recent(self, limit=50): return self._db.get_recent_signals(limit)
