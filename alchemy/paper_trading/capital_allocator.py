"""
alchemy.paper_trading.capital_allocator
==========================================
Capital Division & Multi-Strategy Allocation Engine.

Lets users split their capital across multiple strategies with
independent tracking, risk limits, and auto-rebalancing.

Concepts:
  - Fund: User's total capital pool
  - Bucket: A slice of capital assigned to one strategy
  - Strategy Layer: Buckets can nest (L1 → L2 → L3)
  - Rebalance: Redistribute capital back to target allocations

Example:
  Total Fund: $100,000
  ├── Bucket "Trend Following" (40% = $40,000)
  │   ├── Sub-bucket "BTC SMA Crossover" (60% of parent = $24,000)
  │   └── Sub-bucket "ETH SMA Crossover" (40% of parent = $16,000)
  ├── Bucket "Mean Reversion" (30% = $30,000)
  │   └── Sub-bucket "RSI Multi-Asset" (100% = $30,000)
  ├── Bucket "High Risk / Moonshot" (20% = $20,000)
  │   └── Sub-bucket "Altcoin Momentum" (100% = $20,000)
  └── Bucket "Cash Reserve" (10% = $10,000)

Usage::

    engine = get_capital_engine()
    fund = engine.create_fund(user_id="user123", total_capital=100000)
    engine.add_bucket(user_id, "trend", allocation_pct=40, strategy="sma_crossover",
                      symbols=["BTCUSDT", "ETHUSDT"])
    engine.add_bucket(user_id, "mean_rev", allocation_pct=30, strategy="rsi_mean_reversion")
    engine.add_bucket(user_id, "reserve", allocation_pct=10, strategy="cash")
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

DATA_DIR = os.environ.get("ALCHEMY_CAPITAL_DIR", "data/capital")


class RiskLevel(str, Enum):
    CONSERVATIVE = "conservative"    # Low risk, low return
    MODERATE     = "moderate"        # Balanced
    AGGRESSIVE   = "aggressive"      # High risk, high return
    ULTRA        = "ultra"           # Maximum risk (moonshots)


class AllocationMethod(str, Enum):
    MANUAL       = "manual"          # User sets exact percentages
    EQUAL_WEIGHT = "equal_weight"    # Split equally across buckets
    RISK_PARITY  = "risk_parity"     # Weight inversely to volatility
    KELLY        = "kelly"           # Kelly criterion based on win rates


class BucketStatus(str, Enum):
    ACTIVE   = "active"
    PAUSED   = "paused"
    STOPPED  = "stopped"


# ── Risk presets ──────────────────────────────────────────────────────────────
RISK_PRESETS = {
    RiskLevel.CONSERVATIVE: {
        "max_position_pct": 5,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3,
        "max_drawdown_pct": 5,
        "position_size_pct": 5,
        "max_open_positions": 3,
        "description": "Small positions, tight stops. Capital preservation priority.",
    },
    RiskLevel.MODERATE: {
        "max_position_pct": 10,
        "stop_loss_pct": 2.5,
        "take_profit_pct": 5,
        "max_drawdown_pct": 10,
        "position_size_pct": 10,
        "max_open_positions": 5,
        "description": "Balanced risk/reward. Suitable for most strategies.",
    },
    RiskLevel.AGGRESSIVE: {
        "max_position_pct": 20,
        "stop_loss_pct": 4,
        "take_profit_pct": 8,
        "max_drawdown_pct": 20,
        "position_size_pct": 15,
        "max_open_positions": 8,
        "description": "Larger positions, wider stops. Higher drawdown tolerance.",
    },
    RiskLevel.ULTRA: {
        "max_position_pct": 40,
        "stop_loss_pct": 8,
        "take_profit_pct": 20,
        "max_drawdown_pct": 40,
        "position_size_pct": 25,
        "max_open_positions": 10,
        "description": "Maximum risk. Only for capital you can afford to lose entirely.",
    },
}


@dataclass
class Bucket:
    """A capital allocation bucket assigned to one strategy."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    parent_id: Optional[str] = None        # For nested buckets
    allocation_pct: float = 0.0            # % of parent (or fund)
    allocated_capital: float = 0.0         # Actual $ allocated
    current_value: float = 0.0             # Current value including P&L
    cash_balance: float = 0.0              # Undeployed cash in this bucket
    strategy: str = "manual"
    symbols: list = field(default_factory=list)    # Tradeable symbols
    risk_level: RiskLevel = RiskLevel.MODERATE
    status: BucketStatus = BucketStatus.ACTIVE
    # Performance
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    max_drawdown: float = 0.0
    peak_value: float = 0.0
    # Settings
    auto_trade: bool = False               # Auto-execute signals
    max_open_positions: int = 5
    rebalance_threshold_pct: float = 5.0   # Drift % to trigger rebalance alert
    # Positions
    positions: dict = field(default_factory=dict)   # symbol → {qty, entry, etc.}
    trade_log: list = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def return_pct(self) -> float:
        if self.allocated_capital == 0:
            return 0.0
        return (self.total_pnl / self.allocated_capital) * 100

    @property
    def drift_pct(self) -> float:
        """How far current value has drifted from target allocation."""
        if self.allocated_capital == 0:
            return 0.0
        return ((self.current_value - self.allocated_capital) / self.allocated_capital) * 100

    def to_dict(self) -> dict:
        risk = RISK_PRESETS.get(self.risk_level, {})
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "allocation_pct": self.allocation_pct,
            "allocated_capital": round(self.allocated_capital, 2),
            "current_value": round(self.current_value, 2),
            "cash_balance": round(self.cash_balance, 2),
            "strategy": self.strategy,
            "symbols": self.symbols,
            "risk_level": self.risk_level.value,
            "risk_settings": risk,
            "status": self.status.value,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "return_pct": round(self.return_pct, 2),
            "drift_pct": round(self.drift_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": round(self.win_rate, 1),
            "max_drawdown": round(self.max_drawdown, 2),
            "auto_trade": self.auto_trade,
            "max_open_positions": self.max_open_positions,
            "open_positions": len(self.positions),
            "positions": self.positions,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Fund:
    """User's total capital fund with allocation buckets."""
    user_id: str = ""
    total_capital: float = 100000.0
    unallocated_capital: float = 0.0       # Capital not assigned to any bucket
    buckets: dict = field(default_factory=dict)   # bucket_id → Bucket
    allocation_method: AllocationMethod = AllocationMethod.MANUAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_rebalanced: Optional[datetime] = None

    @property
    def allocated_capital(self) -> float:
        return sum(b.allocated_capital for b in self.buckets.values() if not b.parent_id)

    @property
    def total_value(self) -> float:
        return self.unallocated_capital + sum(
            b.current_value for b in self.buckets.values() if not b.parent_id
        )

    @property
    def total_pnl(self) -> float:
        return self.total_value - self.total_capital

    @property
    def total_return_pct(self) -> float:
        if self.total_capital == 0:
            return 0.0
        return (self.total_pnl / self.total_capital) * 100

    def get_children(self, parent_id: str) -> list[Bucket]:
        return [b for b in self.buckets.values() if b.parent_id == parent_id]

    def build_tree(self) -> list[dict]:
        """Build hierarchical tree of buckets for UI display."""
        def _node(bucket: Bucket) -> dict:
            d = bucket.to_dict()
            children = self.get_children(bucket.id)
            if children:
                d["children"] = [_node(c) for c in children]
            return d

        roots = [b for b in self.buckets.values() if not b.parent_id]
        return [_node(r) for r in sorted(roots, key=lambda x: -x.allocation_pct)]

    def summary(self) -> dict:
        top_buckets = [b for b in self.buckets.values() if not b.parent_id]
        return {
            "user_id": self.user_id,
            "total_capital": round(self.total_capital, 2),
            "allocated_capital": round(self.allocated_capital, 2),
            "unallocated_capital": round(self.unallocated_capital, 2),
            "total_value": round(self.total_value, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "allocation_method": self.allocation_method.value,
            "bucket_count": len(self.buckets),
            "active_buckets": len([b for b in self.buckets.values() if b.status == BucketStatus.ACTIVE]),
            "total_trades": sum(b.total_trades for b in self.buckets.values()),
            "allocation_tree": self.build_tree(),
            "allocation_chart": [
                {
                    "name": b.name,
                    "allocation_pct": b.allocation_pct,
                    "current_value": round(b.current_value, 2),
                    "return_pct": round(b.return_pct, 2),
                    "strategy": b.strategy,
                    "risk_level": b.risk_level.value,
                    "status": b.status.value,
                }
                for b in top_buckets
            ],
            "needs_rebalance": any(
                abs(b.drift_pct) > b.rebalance_threshold_pct
                for b in top_buckets if b.status == BucketStatus.ACTIVE
            ),
            "created_at": self.created_at.isoformat(),
            "last_rebalanced": self.last_rebalanced.isoformat() if self.last_rebalanced else None,
        }


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class CapitalAllocationEngine:
    """Manages capital funds and bucket allocations per user."""

    def __init__(self, data_dir: str = DATA_DIR) -> None:
        self._funds: dict[str, Fund] = {}
        self._lock = threading.Lock()
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._load_all()
        log.info("capital_engine.initialized", users=len(self._funds))

    # ── Fund Management ───────────────────────────────────────────────────────

    def get_fund(self, user_id: str) -> Fund:
        """Get or create a user's capital fund."""
        with self._lock:
            if user_id not in self._funds:
                self._funds[user_id] = Fund(
                    user_id=user_id,
                    total_capital=100000,
                    unallocated_capital=100000,
                )
                self._save(user_id)
            return self._funds[user_id]

    def setup_fund(
        self,
        user_id: str,
        total_capital: float,
        allocation_method: str = "manual",
    ) -> Fund:
        """Create or reconfigure a user's fund."""
        with self._lock:
            fund = Fund(
                user_id=user_id,
                total_capital=total_capital,
                unallocated_capital=total_capital,
                allocation_method=AllocationMethod(allocation_method),
            )
            self._funds[user_id] = fund
            self._save(user_id)
        log.info("capital.fund_created", user_id=user_id, capital=total_capital)
        return fund

    # ── Bucket Management ─────────────────────────────────────────────────────

    def add_bucket(
        self,
        user_id: str,
        name: str,
        allocation_pct: float,
        strategy: str = "manual",
        symbols: list = None,
        risk_level: str = "moderate",
        parent_id: str = None,
        auto_trade: bool = False,
        notes: str = "",
    ) -> Bucket:
        """Add a new capital allocation bucket."""
        fund = self.get_fund(user_id)

        # Validate allocation
        if parent_id:
            parent = fund.buckets.get(parent_id)
            if not parent:
                raise ValueError(f"Parent bucket {parent_id} not found")
            children = fund.get_children(parent_id)
            used = sum(c.allocation_pct for c in children)
            if used + allocation_pct > 100:
                raise ValueError(
                    f"Cannot allocate {allocation_pct}% — parent has {100-used:.1f}% available"
                )
            base_capital = parent.allocated_capital
        else:
            top_used = sum(
                b.allocation_pct for b in fund.buckets.values() if not b.parent_id
            )
            if top_used + allocation_pct > 100:
                raise ValueError(
                    f"Cannot allocate {allocation_pct}% — {100-top_used:.1f}% available at top level"
                )
            base_capital = fund.total_capital

        allocated = base_capital * (allocation_pct / 100)

        bucket = Bucket(
            name=name,
            parent_id=parent_id,
            allocation_pct=allocation_pct,
            allocated_capital=allocated,
            current_value=allocated,
            cash_balance=allocated,
            strategy=strategy,
            symbols=symbols or [],
            risk_level=RiskLevel(risk_level),
            auto_trade=auto_trade,
            notes=notes,
        )

        with self._lock:
            fund.buckets[bucket.id] = bucket
            fund.unallocated_capital = fund.total_capital - fund.allocated_capital
            self._save(user_id)

        log.info("capital.bucket_added", user_id=user_id, bucket=name,
                 pct=allocation_pct, capital=allocated, strategy=strategy)
        return bucket

    def update_bucket(
        self,
        user_id: str,
        bucket_id: str,
        **kwargs,
    ) -> Bucket:
        """Update bucket settings."""
        fund = self.get_fund(user_id)
        bucket = fund.buckets.get(bucket_id)
        if not bucket:
            raise ValueError(f"Bucket {bucket_id} not found")

        with self._lock:
            for key, val in kwargs.items():
                if key == "risk_level":
                    bucket.risk_level = RiskLevel(val)
                elif key == "status":
                    bucket.status = BucketStatus(val)
                elif key == "allocation_pct":
                    bucket.allocation_pct = val
                    base = fund.total_capital if not bucket.parent_id else \
                           fund.buckets.get(bucket.parent_id, Bucket()).allocated_capital
                    bucket.allocated_capital = base * (val / 100)
                    bucket.current_value = bucket.allocated_capital
                    bucket.cash_balance = bucket.allocated_capital
                    fund.unallocated_capital = fund.total_capital - fund.allocated_capital
                elif hasattr(bucket, key):
                    setattr(bucket, key, val)
            self._save(user_id)

        return bucket

    def remove_bucket(self, user_id: str, bucket_id: str) -> bool:
        """Remove a bucket and return its capital to unallocated."""
        fund = self.get_fund(user_id)
        with self._lock:
            bucket = fund.buckets.pop(bucket_id, None)
            if not bucket:
                return False
            # Remove children
            child_ids = [b.id for b in fund.buckets.values() if b.parent_id == bucket_id]
            for cid in child_ids:
                fund.buckets.pop(cid, None)
            fund.unallocated_capital = fund.total_capital - fund.allocated_capital
            self._save(user_id)
        return True

    # ── Trading Within Buckets ────────────────────────────────────────────────

    def record_trade(
        self,
        user_id: str,
        bucket_id: str,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        fee: float = 0,
    ) -> dict:
        """Record a completed trade in a bucket."""
        fund = self.get_fund(user_id)
        bucket = fund.buckets.get(bucket_id)
        if not bucket:
            raise ValueError(f"Bucket {bucket_id} not found")

        if side.lower() in ("buy", "long"):
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        net_pnl = pnl - fee

        trade = {
            "symbol": symbol,
            "side": side,
            "quantity": round(quantity, 8),
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "gross_pnl": round(pnl, 2),
            "fee": round(fee, 2),
            "net_pnl": round(net_pnl, 2),
            "return_pct": round((pnl / (entry_price * quantity)) * 100, 2) if entry_price * quantity > 0 else 0,
            "bucket": bucket.name,
            "strategy": bucket.strategy,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            bucket.trade_log.append(trade)
            bucket.total_trades += 1
            if net_pnl > 0:
                bucket.winning_trades += 1
            bucket.realized_pnl += net_pnl
            bucket.cash_balance += net_pnl
            bucket.current_value = bucket.cash_balance + sum(
                p.get("value", 0) for p in bucket.positions.values()
            )
            # Track drawdown
            if bucket.current_value > bucket.peak_value:
                bucket.peak_value = bucket.current_value
            dd = ((bucket.peak_value - bucket.current_value) / bucket.peak_value * 100
                  if bucket.peak_value > 0 else 0)
            bucket.max_drawdown = max(bucket.max_drawdown, dd)
            self._save(user_id)

        return trade

    # ── Rebalancing ───────────────────────────────────────────────────────────

    def check_rebalance(self, user_id: str) -> dict:
        """Check if any buckets need rebalancing."""
        fund = self.get_fund(user_id)
        alerts = []
        for b in fund.buckets.values():
            if b.status != BucketStatus.ACTIVE or b.parent_id:
                continue
            if abs(b.drift_pct) > b.rebalance_threshold_pct:
                target = fund.total_capital * (b.allocation_pct / 100)
                diff = b.current_value - target
                action = "reduce" if diff > 0 else "add"
                alerts.append({
                    "bucket_id": b.id,
                    "bucket_name": b.name,
                    "target_allocation_pct": b.allocation_pct,
                    "current_drift_pct": round(b.drift_pct, 2),
                    "target_value": round(target, 2),
                    "current_value": round(b.current_value, 2),
                    "adjustment_needed": round(abs(diff), 2),
                    "action": action,
                })
        return {
            "needs_rebalance": len(alerts) > 0,
            "alerts": alerts,
            "last_rebalanced": fund.last_rebalanced.isoformat() if fund.last_rebalanced else None,
        }

    def rebalance(self, user_id: str) -> dict:
        """Execute rebalancing — reset all buckets to target allocations."""
        fund = self.get_fund(user_id)
        changes = []

        with self._lock:
            for b in fund.buckets.values():
                if b.status != BucketStatus.ACTIVE or b.parent_id:
                    continue
                target = fund.total_capital * (b.allocation_pct / 100)
                old_value = b.current_value
                b.allocated_capital = target
                b.current_value = target
                b.cash_balance = target - sum(
                    p.get("value", 0) for p in b.positions.values()
                )
                changes.append({
                    "bucket": b.name,
                    "old_value": round(old_value, 2),
                    "new_value": round(target, 2),
                    "change": round(target - old_value, 2),
                })

            fund.unallocated_capital = fund.total_capital - fund.allocated_capital
            fund.last_rebalanced = datetime.now(timezone.utc)
            self._save(user_id)

        log.info("capital.rebalanced", user_id=user_id, changes=len(changes))
        return {"ok": True, "changes": changes}

    # ── Quick Templates ───────────────────────────────────────────────────────

    def apply_template(self, user_id: str, template: str, total_capital: float = 0) -> Fund:
        """Apply a predefined allocation template."""
        templates = {
            "conservative": [
                ("Blue Chip Crypto", 30, "sma_crossover", ["BTCUSDT", "ETHUSDT"], "conservative"),
                ("Stablecoin Yield", 30, "cash", [], "conservative"),
                ("Index Follow", 20, "combined_sma_rsi", ["BTCUSDT", "BNBUSDT", "SOLUSDT"], "moderate"),
                ("Cash Reserve", 20, "cash", [], "conservative"),
            ],
            "balanced": [
                ("Trend Following", 35, "sma_crossover", ["BTCUSDT", "ETHUSDT"], "moderate"),
                ("Mean Reversion", 25, "rsi_mean_reversion", ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "moderate"),
                ("Volatility Play", 20, "bollinger_band", ["BTCUSDT"], "aggressive"),
                ("Cash Reserve", 20, "cash", [], "conservative"),
            ],
            "aggressive": [
                ("Momentum", 30, "sma_crossover", ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "aggressive"),
                ("Breakout", 25, "bollinger_band", ["BTCUSDT", "ETHUSDT"], "aggressive"),
                ("Combined Signals", 25, "combined_sma_rsi", ["BTCUSDT", "SOLUSDT", "BNBUSDT"], "aggressive"),
                ("High Risk Alpha", 15, "rsi_mean_reversion", ["DOGEUSDT", "XRPUSDT"], "ultra"),
                ("Emergency Cash", 5, "cash", [], "conservative"),
            ],
            "crypto_diversified": [
                ("BTC Core", 40, "sma_crossover", ["BTCUSDT"], "moderate"),
                ("ETH Growth", 25, "combined_sma_rsi", ["ETHUSDT"], "moderate"),
                ("Alt Rotation", 20, "rsi_mean_reversion", ["SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"], "aggressive"),
                ("Stablecoin Buffer", 15, "cash", [], "conservative"),
            ],
        }

        t = templates.get(template)
        if not t:
            raise ValueError(f"Unknown template: {template}. Available: {list(templates.keys())}")

        fund = self.setup_fund(user_id, total_capital or 100000)
        for name, pct, strategy, symbols, risk in t:
            self.add_bucket(user_id, name, pct, strategy, symbols, risk)

        return self.get_fund(user_id)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self, user_id: str) -> None:
        fund = self._funds.get(user_id)
        if not fund:
            return
        try:
            data = {
                "user_id": fund.user_id,
                "total_capital": fund.total_capital,
                "unallocated_capital": fund.unallocated_capital,
                "allocation_method": fund.allocation_method.value,
                "created_at": fund.created_at.isoformat(),
                "last_rebalanced": fund.last_rebalanced.isoformat() if fund.last_rebalanced else None,
                "buckets": {
                    bid: {
                        "id": b.id, "name": b.name, "parent_id": b.parent_id,
                        "allocation_pct": b.allocation_pct,
                        "allocated_capital": b.allocated_capital,
                        "current_value": b.current_value,
                        "cash_balance": b.cash_balance,
                        "strategy": b.strategy, "symbols": b.symbols,
                        "risk_level": b.risk_level.value,
                        "status": b.status.value,
                        "realized_pnl": b.realized_pnl,
                        "unrealized_pnl": b.unrealized_pnl,
                        "total_trades": b.total_trades,
                        "winning_trades": b.winning_trades,
                        "max_drawdown": b.max_drawdown,
                        "peak_value": b.peak_value,
                        "auto_trade": b.auto_trade,
                        "max_open_positions": b.max_open_positions,
                        "rebalance_threshold_pct": b.rebalance_threshold_pct,
                        "positions": b.positions,
                        "trade_log": b.trade_log[-100:],
                        "notes": b.notes,
                        "created_at": b.created_at.isoformat(),
                    }
                    for bid, b in fund.buckets.items()
                },
            }
            with open(self._dir / f"{user_id}.json", "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error("capital.save_error", user_id=user_id, error=str(e))

    def _load_all(self) -> None:
        for path in self._dir.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                uid = data["user_id"]
                fund = Fund(
                    user_id=uid,
                    total_capital=data.get("total_capital", 100000),
                    unallocated_capital=data.get("unallocated_capital", 0),
                    allocation_method=AllocationMethod(data.get("allocation_method", "manual")),
                )
                if data.get("created_at"):
                    fund.created_at = datetime.fromisoformat(data["created_at"])
                if data.get("last_rebalanced"):
                    fund.last_rebalanced = datetime.fromisoformat(data["last_rebalanced"])

                for bid, bd in data.get("buckets", {}).items():
                    b = Bucket(
                        id=bd.get("id", bid),
                        name=bd.get("name", ""),
                        parent_id=bd.get("parent_id"),
                        allocation_pct=bd.get("allocation_pct", 0),
                        allocated_capital=bd.get("allocated_capital", 0),
                        current_value=bd.get("current_value", 0),
                        cash_balance=bd.get("cash_balance", 0),
                        strategy=bd.get("strategy", "manual"),
                        symbols=bd.get("symbols", []),
                        risk_level=RiskLevel(bd.get("risk_level", "moderate")),
                        status=BucketStatus(bd.get("status", "active")),
                        realized_pnl=bd.get("realized_pnl", 0),
                        unrealized_pnl=bd.get("unrealized_pnl", 0),
                        total_trades=bd.get("total_trades", 0),
                        winning_trades=bd.get("winning_trades", 0),
                        max_drawdown=bd.get("max_drawdown", 0),
                        peak_value=bd.get("peak_value", 0),
                        auto_trade=bd.get("auto_trade", False),
                        max_open_positions=bd.get("max_open_positions", 5),
                        rebalance_threshold_pct=bd.get("rebalance_threshold_pct", 5),
                        positions=bd.get("positions", {}),
                        trade_log=bd.get("trade_log", []),
                        notes=bd.get("notes", ""),
                    )
                    fund.buckets[b.id] = b

                self._funds[uid] = fund
            except Exception as e:
                log.error("capital.load_error", path=str(path), error=str(e))


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine: Optional[CapitalAllocationEngine] = None

def get_capital_engine() -> CapitalAllocationEngine:
    global _engine
    if _engine is None:
        _engine = CapitalAllocationEngine()
    return _engine
