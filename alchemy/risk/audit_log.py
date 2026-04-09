"""
alchemy.risk.audit_log
========================
Immutable trade audit log.

Records every trading decision with full context:
  - Signal received (strategy, symbol, side, confidence)
  - Risk checks passed/failed (which rule, why)
  - Order submitted (exchange, price, quantity)
  - Order filled/rejected/cancelled
  - Kill switch activations
  - Circuit breaker triggers

Designed for:
  - Regulatory compliance (SEBI, exchange audit trails)
  - Tax reporting (complete trade history with timestamps)
  - Post-mortem analysis (why did we enter/exit?)
  - Strategy performance review

Storage: append-only JSONL file + optional SQLite table.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)

AUDIT_DIR  = os.environ.get("ALCHEMY_AUDIT_DIR", "data/audit")
AUDIT_FILE = "trade_audit.jsonl"


class AuditAction(str, Enum):
    """Types of auditable actions."""
    SIGNAL_RECEIVED   = "signal.received"
    SIGNAL_FILTERED   = "signal.filtered"
    RISK_CHECK_PASSED = "risk.check_passed"
    RISK_CHECK_FAILED = "risk.check_failed"
    DEDUP_BLOCKED     = "dedup.blocked"
    PRICE_GUARD_BLOCK = "price_guard.blocked"
    ORDER_SUBMITTED   = "order.submitted"
    ORDER_FILLED      = "order.filled"
    ORDER_PARTIAL     = "order.partial_fill"
    ORDER_REJECTED    = "order.rejected"
    ORDER_CANCELLED   = "order.cancelled"
    POSITION_OPENED   = "position.opened"
    POSITION_CLOSED   = "position.closed"
    STOP_LOSS_HIT     = "stop_loss.hit"
    TAKE_PROFIT_HIT   = "take_profit.hit"
    KILL_SWITCH       = "kill_switch.activated"
    CIRCUIT_BREAKER   = "circuit_breaker.triggered"
    RECONCILIATION    = "reconciliation.run"
    MANUAL_OVERRIDE   = "manual.override"


@dataclass
class AuditEntry:
    """A single audit log entry. Immutable once created."""
    action: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    exchange: str = ""
    symbol: str = ""
    side: str = ""
    strategy: str = ""
    quantity: float = 0.0
    price: float = 0.0
    order_id: str = ""
    pnl: float = 0.0
    user: str = ""
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


class TradeAuditLog:
    """
    Append-only trade audit log.

    Thread-safe. Writes to JSONL file for durability.
    Each entry is one JSON line — easy to parse, grep, and stream.
    """

    def __init__(self, audit_dir: str = AUDIT_DIR) -> None:
        self._dir = Path(audit_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / AUDIT_FILE
        self._lock = threading.Lock()
        self._buffer: list[AuditEntry] = []
        self._entry_count = 0

        # Count existing entries
        if self._file.exists():
            try:
                with open(self._file) as f:
                    self._entry_count = sum(1 for _ in f)
            except Exception:
                pass

        log.info("audit_log.initialized",
                 path=str(self._file), existing=self._entry_count)

    def record(self, entry: AuditEntry) -> None:
        """Append an audit entry (thread-safe, durable)."""
        with self._lock:
            try:
                with open(self._file, "a") as f:
                    f.write(entry.to_json() + "\n")
                self._entry_count += 1
                self._buffer.append(entry)

                # Keep in-memory buffer at 1000 entries
                if len(self._buffer) > 1000:
                    self._buffer = self._buffer[-1000:]

                log.debug("audit_log.recorded",
                          action=entry.action, symbol=entry.symbol)

            except Exception as e:
                log.error("audit_log.write_error", error=str(e))

    def log_signal(
        self,
        strategy: str,
        symbol: str,
        side: str,
        confidence: float = 0.0,
        **kwargs,
    ) -> None:
        """Convenience: log a signal received event."""
        self.record(AuditEntry(
            action=AuditAction.SIGNAL_RECEIVED,
            strategy=strategy,
            symbol=symbol,
            side=side,
            metadata={"confidence": confidence, **kwargs},
        ))

    def log_risk_check(
        self,
        symbol: str,
        passed: bool,
        check_name: str,
        reason: str = "",
        **kwargs,
    ) -> None:
        """Convenience: log a risk check result."""
        action = AuditAction.RISK_CHECK_PASSED if passed else AuditAction.RISK_CHECK_FAILED
        self.record(AuditEntry(
            action=action,
            symbol=symbol,
            reason=f"{check_name}: {reason}",
            metadata=kwargs,
        ))

    def log_order(
        self,
        action: AuditAction,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: str = "",
        strategy: str = "",
        **kwargs,
    ) -> None:
        """Convenience: log an order event."""
        self.record(AuditEntry(
            action=action,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
            strategy=strategy,
            metadata=kwargs,
        ))

    def log_kill_switch(self, user: str, reason: str, **kwargs) -> None:
        """Convenience: log kill switch activation."""
        self.record(AuditEntry(
            action=AuditAction.KILL_SWITCH,
            user=user,
            reason=reason,
            metadata=kwargs,
        ))

    def recent(self, limit: int = 50, action_filter: Optional[str] = None) -> list[dict]:
        """Get recent audit entries from in-memory buffer."""
        with self._lock:
            entries = self._buffer
            if action_filter:
                entries = [e for e in entries if e.action == action_filter]
            return [asdict(e) for e in entries[-limit:]]

    def search(
        self,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Search audit log from file (for historical queries).
        Returns most recent entries matching filters.
        """
        results = []
        try:
            with open(self._file) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if symbol and entry.get("symbol", "").upper() != symbol.upper():
                            continue
                        if action and entry.get("action") != action:
                            continue
                        if since and entry.get("timestamp", "") < since:
                            continue
                        results.append(entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass

        return results[-limit:]

    def stats(self) -> dict:
        """Audit log statistics."""
        return {
            "total_entries": self._entry_count,
            "buffer_size": len(self._buffer),
            "file_path": str(self._file),
            "file_exists": self._file.exists(),
            "file_size_mb": round(self._file.stat().st_size / 1024 / 1024, 2)
                           if self._file.exists() else 0,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[TradeAuditLog] = None


def get_audit_log() -> TradeAuditLog:
    global _instance
    if _instance is None:
        _instance = TradeAuditLog()
    return _instance
