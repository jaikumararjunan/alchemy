"""
Trade Store
===========
CRUD operations for the trade_log table.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradeStore:
    """Read / write trades to the trade_log table."""

    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        leverage: int = 1,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        pnl_usd: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        fee_usd: float = 0.0,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        exit_reason: Optional[str] = None,
        order_type: str = "market",
        dry_run: bool = True,
        notes: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> int:
        """Insert a trade record. Returns the new row id."""
        ts = ts or datetime.now(timezone.utc).isoformat()
        cur = self.db.execute(
            """INSERT INTO trade_log
               (ts, symbol, side, order_type, entry_price, exit_price,
                size_usd, leverage, pnl_usd, pnl_pct, fee_usd,
                stop_loss_pct, take_profit_pct, exit_reason, dry_run, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, symbol, side, order_type, entry_price, exit_price,
             size_usd, leverage, pnl_usd, pnl_pct, fee_usd,
             stop_loss_pct, take_profit_pct, exit_reason,
             int(dry_run), notes),
        )
        logger.debug(f"Trade recorded: {side} {symbol} pnl={pnl_usd}")
        return cur.lastrowid

    def get_recent(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict]:
        if symbol:
            rows = self.db.fetchall(
                "SELECT * FROM trade_log WHERE symbol=? ORDER BY ts DESC LIMIT ?",
                (symbol, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM trade_log ORDER BY ts DESC LIMIT ?", (limit,)
            )
        return rows

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate trade statistics."""
        row = self.db.fetchone(
            """SELECT
                COUNT(*)                              AS total_trades,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS winning_trades,
                SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) AS losing_trades,
                COALESCE(SUM(pnl_usd), 0)            AS total_pnl_usd,
                COALESCE(SUM(fee_usd), 0)            AS total_fees_usd,
                COALESCE(AVG(pnl_usd), 0)            AS avg_pnl_usd,
                COALESCE(MAX(pnl_usd), 0)            AS best_trade_usd,
                COALESCE(MIN(pnl_usd), 0)            AS worst_trade_usd
               FROM trade_log"""
        )
        if not row or row.get("total_trades", 0) == 0:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate_pct": 0.0, "total_pnl_usd": 0.0, "total_fees_usd": 0.0,
                "avg_pnl_usd": 0.0, "best_trade_usd": 0.0, "worst_trade_usd": 0.0,
            }
        n = row["total_trades"] or 1
        row["win_rate_pct"] = round(row["winning_trades"] / n * 100, 2)
        row["total_pnl_usd"]   = round(row["total_pnl_usd"], 4)
        row["total_fees_usd"]  = round(row["total_fees_usd"], 4)
        row["avg_pnl_usd"]     = round(row["avg_pnl_usd"], 4)
        row["best_trade_usd"]  = round(row["best_trade_usd"], 4)
        row["worst_trade_usd"] = round(row["worst_trade_usd"], 4)
        return row

    def count(self) -> int:
        row = self.db.fetchone("SELECT COUNT(*) AS n FROM trade_log")
        return row["n"] if row else 0
