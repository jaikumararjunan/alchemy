"""
SQLite Database Manager
=======================
Single-file SQLite database for persisting:
  - trade_log     — every executed trade (entry/exit, PnL, fees)
  - decisions     — every AI decision with reasoning and context
  - equity_snapshots — periodic equity/balance snapshots

Thread-safe via check_same_thread=False + a module-level lock.
The database file is created automatically on first use.
"""

import sqlite3
import threading
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)

_LOCK = threading.Lock()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS trade_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,          -- ISO-8601 UTC
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL,          -- 'buy' | 'sell'
    order_type      TEXT    NOT NULL DEFAULT 'market',
    entry_price     REAL,
    exit_price      REAL,
    size_usd        REAL    NOT NULL,
    leverage        INTEGER NOT NULL DEFAULT 1,
    pnl_usd         REAL,
    pnl_pct         REAL,
    fee_usd         REAL    NOT NULL DEFAULT 0,
    stop_loss_pct   REAL,
    take_profit_pct REAL,
    exit_reason     TEXT,                      -- 'tp' | 'sl' | 'manual' | 'signal'
    dry_run         INTEGER NOT NULL DEFAULT 1,-- 0=live, 1=paper
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    cycle           INTEGER NOT NULL DEFAULT 0,
    action          TEXT    NOT NULL,          -- 'BUY' | 'SELL' | 'HOLD' | 'CLOSE'
    confidence      REAL,
    reasoning       TEXT,
    emotion_score   REAL,
    geo_risk        REAL,
    forecast_score  REAL,
    market_regime   TEXT,
    adx             REAL,
    signal_score    REAL,
    dry_run         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    balance         REAL    NOT NULL,
    unrealized_pnl  REAL    NOT NULL DEFAULT 0,
    total_equity    REAL    NOT NULL,
    open_positions  INTEGER NOT NULL DEFAULT 0,
    cycle           INTEGER NOT NULL DEFAULT 0,
    dry_run         INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_trade_ts     ON trade_log(ts);
CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade_log(symbol);
CREATE INDEX IF NOT EXISTS idx_decision_ts  ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_equity_ts    ON equity_snapshots(ts);
"""


class Database:
    """SQLite connection wrapper with automatic schema creation."""

    def __init__(self, db_path: str = "alchemy.db"):
        self.db_path = (
            db_path if db_path == ":memory:" else str(Path(db_path).resolve())
        )
        self._local = threading.local()
        self._init_schema()
        logger.info(f"Database ready: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        """Return a per-thread connection (created on demand)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        with _LOCK:
            conn = self._connect()
            conn.executescript(SCHEMA)
            conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with _LOCK:
            conn = self._connect()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    def fetchall(self, sql: str, params: tuple = ()):
        with _LOCK:
            conn = self._connect()
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()):
        with _LOCK:
            conn = self._connect()
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
