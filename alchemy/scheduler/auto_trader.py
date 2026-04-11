"""
alchemy.scheduler.auto_trader — Auto-Trade Scheduler + Trailing SL + DCA
==========================================================================
Features 1, 8, 9 from the roadmap.
"""
from __future__ import annotations
import json, os, uuid, threading, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
DATA_DIR = os.environ.get("ALCHEMY_SCHEDULER_DIR", "data/scheduler")


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1: Auto-Trade Scheduler
# ══════════════════════════════════════════════════════════════════════════════

class Schedule:
    def __init__(self, **kw):
        self.id = kw.get("id", str(uuid.uuid4())[:8])
        self.user_id = kw.get("user_id", "")
        self.name = kw.get("name", "")
        self.strategy = kw.get("strategy", "sma_crossover")
        self.symbol = kw.get("symbol", "BTCUSDT")
        self.exchange = kw.get("exchange", "binance")
        self.interval_minutes = kw.get("interval_minutes", 60)
        self.start_hour = kw.get("start_hour", 9)
        self.end_hour = kw.get("end_hour", 21)
        self.position_size_pct = kw.get("position_size_pct", 10)
        self.mode = kw.get("mode", "paper")
        self.active = kw.get("active", True)
        self.last_run = kw.get("last_run")
        self.run_count = kw.get("run_count", 0)
        self.total_pnl = kw.get("total_pnl", 0.0)
        self.created_at = kw.get("created_at", datetime.now(timezone.utc).isoformat())
        self.history = kw.get("history", [])

    def to_dict(self):
        return self.__dict__.copy()


class AutoTradeScheduler:
    def __init__(self):
        self._schedules: dict[str, list[Schedule]] = {}
        self._lock = threading.Lock()
        self._dir = Path(DATA_DIR); self._dir.mkdir(parents=True, exist_ok=True)
        self._load_all()

    def get_schedules(self, uid): return [s.to_dict() for s in self._schedules.get(uid, [])]

    def add_schedule(self, uid, **kw):
        s = Schedule(user_id=uid, **kw)
        with self._lock:
            self._schedules.setdefault(uid, []).append(s)
            self._save(uid)
        return s

    def remove_schedule(self, uid, sid):
        with self._lock:
            self._schedules[uid] = [s for s in self._schedules.get(uid, []) if s.id != sid]
            self._save(uid)
        return True

    def toggle_schedule(self, uid, sid):
        for s in self._schedules.get(uid, []):
            if s.id == sid:
                s.active = not s.active
                self._save(uid)
                return s.to_dict()
        return None

    def _save(self, uid):
        try:
            with open(self._dir / f"{uid}.json", "w") as f:
                json.dump([s.__dict__ for s in self._schedules.get(uid, [])], f, default=str)
        except: pass

    def _load_all(self):
        for p in self._dir.glob("*.json"):
            try:
                with open(p) as f:
                    self._schedules[p.stem] = [Schedule(**d) for d in json.load(f)]
            except: pass


_scheduler = None
def get_scheduler():
    global _scheduler
    if not _scheduler: _scheduler = AutoTradeScheduler()
    return _scheduler


# ══════════════════════════════════════════════════════════════════════════════
# Feature 8: Trailing Stop-Loss
# ══════════════════════════════════════════════════════════════════════════════

class TrailingStop:
    def __init__(self, symbol, side, trail_pct, trail_amount=0, activated_price=0):
        self.id = str(uuid.uuid4())[:8]
        self.symbol = symbol
        self.side = side           # "long" or "short"
        self.trail_pct = trail_pct  # e.g., 2.0 = 2%
        self.trail_amount = trail_amount  # Fixed $ amount (alternative)
        self.highest_price = activated_price
        self.lowest_price = activated_price if activated_price else float('inf')
        self.stop_price = 0.0
        self.triggered = False
        self.created_at = datetime.now(timezone.utc).isoformat()

    def update(self, current_price: float) -> dict:
        """Update with latest price. Returns trigger info."""
        if self.triggered:
            return {"triggered": True, "stop_price": self.stop_price}

        if self.side == "long":
            if current_price > self.highest_price:
                self.highest_price = current_price
            if self.trail_amount > 0:
                self.stop_price = self.highest_price - self.trail_amount
            else:
                self.stop_price = self.highest_price * (1 - self.trail_pct / 100)
            if current_price <= self.stop_price:
                self.triggered = True
                return {"triggered": True, "stop_price": self.stop_price,
                        "highest": self.highest_price, "pnl_locked_pct": round(
                            (self.stop_price / self.highest_price - 1) * 100, 2)}
        else:  # short
            if current_price < self.lowest_price:
                self.lowest_price = current_price
            if self.trail_amount > 0:
                self.stop_price = self.lowest_price + self.trail_amount
            else:
                self.stop_price = self.lowest_price * (1 + self.trail_pct / 100)
            if current_price >= self.stop_price:
                self.triggered = True
                return {"triggered": True, "stop_price": self.stop_price,
                        "lowest": self.lowest_price}

        return {"triggered": False, "stop_price": round(self.stop_price, 2),
                "highest": self.highest_price, "current": current_price}

    def to_dict(self):
        return {
            "id": self.id, "symbol": self.symbol, "side": self.side,
            "trail_pct": self.trail_pct, "trail_amount": self.trail_amount,
            "stop_price": round(self.stop_price, 2),
            "highest_price": self.highest_price, "lowest_price": self.lowest_price,
            "triggered": self.triggered, "created_at": self.created_at,
        }


# Trailing stop manager per user
_trailing_stops: dict[str, list[TrailingStop]] = {}

def add_trailing_stop(user_id, symbol, side, trail_pct, trail_amount=0, price=0):
    ts = TrailingStop(symbol, side, trail_pct, trail_amount, price)
    _trailing_stops.setdefault(user_id, []).append(ts)
    return ts.to_dict()

def get_trailing_stops(user_id):
    return [t.to_dict() for t in _trailing_stops.get(user_id, [])]

def update_trailing_stops(user_id, prices: dict):
    events = []
    for ts in _trailing_stops.get(user_id, []):
        if ts.symbol in prices and not ts.triggered:
            result = ts.update(prices[ts.symbol])
            if result.get("triggered"):
                events.append({"type": "trailing_stop", "symbol": ts.symbol, **result})
    return events


# ══════════════════════════════════════════════════════════════════════════════
# Feature 9: Dollar-Cost Averaging (DCA)
# ══════════════════════════════════════════════════════════════════════════════

class DCAConfig:
    def __init__(self, **kw):
        self.id = kw.get("id", str(uuid.uuid4())[:8])
        self.user_id = kw.get("user_id", "")
        self.symbol = kw.get("symbol", "BTCUSDT")
        self.amount_usd = kw.get("amount_usd", 100)
        self.frequency = kw.get("frequency", "weekly")  # daily, weekly, biweekly, monthly
        self.day_of_week = kw.get("day_of_week", 0)     # 0=Monday
        self.hour = kw.get("hour", 9)                    # 9 AM
        self.mode = kw.get("mode", "paper")
        self.active = kw.get("active", True)
        self.total_invested = kw.get("total_invested", 0.0)
        self.total_units = kw.get("total_units", 0.0)
        self.avg_price = kw.get("avg_price", 0.0)
        self.buy_count = kw.get("buy_count", 0)
        self.history = kw.get("history", [])
        self.created_at = kw.get("created_at", datetime.now(timezone.utc).isoformat())

    @property
    def current_value(self):
        return 0  # Would be calculated with live price

    def record_buy(self, price, qty):
        self.total_invested += price * qty
        self.total_units += qty
        self.avg_price = self.total_invested / self.total_units if self.total_units > 0 else 0
        self.buy_count += 1
        self.history.append({
            "date": datetime.now(timezone.utc).isoformat(),
            "price": round(price, 2), "qty": round(qty, 8),
            "invested": round(price * qty, 2), "avg": round(self.avg_price, 2),
        })

    def to_dict(self):
        return {
            "id": self.id, "symbol": self.symbol, "amount_usd": self.amount_usd,
            "frequency": self.frequency, "day_of_week": self.day_of_week,
            "hour": self.hour, "mode": self.mode, "active": self.active,
            "total_invested": round(self.total_invested, 2),
            "total_units": round(self.total_units, 8),
            "avg_price": round(self.avg_price, 2),
            "buy_count": self.buy_count,
            "recent_history": self.history[-10:],
            "created_at": self.created_at,
        }


_dca_configs: dict[str, list[DCAConfig]] = {}

def add_dca(user_id, **kw):
    d = DCAConfig(user_id=user_id, **kw)
    _dca_configs.setdefault(user_id, []).append(d)
    return d.to_dict()

def get_dcas(user_id):
    return [d.to_dict() for d in _dca_configs.get(user_id, [])]

def remove_dca(user_id, dca_id):
    _dca_configs[user_id] = [d for d in _dca_configs.get(user_id, []) if d.id != dca_id]
    return True
