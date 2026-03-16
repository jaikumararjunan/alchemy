"""
Decision Store
==============
CRUD operations for AI decisions and equity snapshots.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict

from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DecisionStore:
    """Read / write AI decisions and equity snapshots."""

    def __init__(self, db: Database):
        self.db = db

    # ── Decisions ─────────────────────────────────────────────────────────────

    def record_decision(
        self,
        symbol: str,
        action: str,
        cycle: int = 0,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        emotion_score: Optional[float] = None,
        geo_risk: Optional[float] = None,
        forecast_score: Optional[float] = None,
        market_regime: Optional[str] = None,
        adx: Optional[float] = None,
        signal_score: Optional[float] = None,
        dry_run: bool = True,
        ts: Optional[str] = None,
    ) -> int:
        ts = ts or datetime.now(timezone.utc).isoformat()
        cur = self.db.execute(
            """INSERT INTO decisions
               (ts, symbol, cycle, action, confidence, reasoning,
                emotion_score, geo_risk, forecast_score, market_regime,
                adx, signal_score, dry_run)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ts,
                symbol,
                cycle,
                action,
                confidence,
                reasoning,
                emotion_score,
                geo_risk,
                forecast_score,
                market_regime,
                adx,
                signal_score,
                int(dry_run),
            ),
        )
        logger.debug(f"Decision recorded: {action} {symbol} cycle={cycle}")
        return cur.lastrowid

    def get_recent_decisions(
        self, limit: int = 50, symbol: Optional[str] = None
    ) -> List[Dict]:
        if symbol:
            return self.db.fetchall(
                "SELECT * FROM decisions WHERE symbol=? ORDER BY ts DESC LIMIT ?",
                (symbol, limit),
            )
        return self.db.fetchall(
            "SELECT * FROM decisions ORDER BY ts DESC LIMIT ?", (limit,)
        )

    def get_decision_counts(self) -> Dict[str, int]:
        rows = self.db.fetchall(
            "SELECT action, COUNT(*) AS n FROM decisions GROUP BY action"
        )
        return {r["action"]: r["n"] for r in rows}

    # ── Equity snapshots ──────────────────────────────────────────────────────

    def snapshot_equity(
        self,
        balance: float,
        total_equity: Optional[float] = None,
        unrealized_pnl: float = 0.0,
        open_positions: int = 0,
        cycle: int = 0,
        dry_run: bool = True,
        ts: Optional[str] = None,
    ) -> int:
        ts = ts or datetime.now(timezone.utc).isoformat()
        equity = total_equity if total_equity is not None else balance + unrealized_pnl
        cur = self.db.execute(
            """INSERT INTO equity_snapshots
               (ts, balance, unrealized_pnl, total_equity, open_positions, cycle, dry_run)
               VALUES (?,?,?,?,?,?,?)""",
            (ts, balance, unrealized_pnl, equity, open_positions, cycle, int(dry_run)),
        )
        return cur.lastrowid

    def get_equity_history(self, limit: int = 200) -> List[Dict]:
        return self.db.fetchall(
            "SELECT * FROM equity_snapshots ORDER BY ts DESC LIMIT ?", (limit,)
        )

    def get_latest_equity(self) -> Optional[Dict]:
        return self.db.fetchone(
            "SELECT * FROM equity_snapshots ORDER BY ts DESC LIMIT 1"
        )

    def count_decisions(self) -> int:
        row = self.db.fetchone("SELECT COUNT(*) AS n FROM decisions")
        return row["n"] if row else 0

    def count_snapshots(self) -> int:
        row = self.db.fetchone("SELECT COUNT(*) AS n FROM equity_snapshots")
        return row["n"] if row else 0
