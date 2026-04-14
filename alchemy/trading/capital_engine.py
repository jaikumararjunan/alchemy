"""
alchemy.trading.capital_engine
================================
Enterprise Capital Preservation & Profit Management Engine.

Incorporates best practices from:
  - Old branch: capital_manager.py (reinvestment modes, profit locking)
  - Old branch: intraday_strategies.py (risk/reward gating)
  - Industry: Kelly criterion, anti-martingale, drawdown circuit breakers

Architecture:
  CapitalConfig    → User-configurable risk parameters
  CapitalState     → Live account state (capital, reserves, drawdown)
  CapitalEngine    → Core engine (sizing, reinvestment, drawdown guards)
  StrategyGate     → Pre-trade validation (R:R, confidence, regime)
  ProfitManager    → Profit locking, withdrawal, compounding
  DrawdownGuard    → Circuit breakers, position reduction, recovery mode

Usage:
  engine = get_capital_engine(user_id)
  size = engine.calculate_position_size(symbol, confidence, entry, sl, tp)
  engine.record_trade(symbol, pnl, fee, strategy)
  engine.summary()
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date, timedelta
from enum import Enum
from typing import Optional, Literal

import structlog
log = structlog.get_logger(__name__)

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class ReinvestMode(str, Enum):
    CONSERVATIVE = "conservative"   # 30% of profits reinvested
    MODERATE = "moderate"           # 50% reinvested (default)
    AGGRESSIVE = "aggressive"       # 75% reinvested
    FULL_COMPOUND = "full_compound" # 100% geometric growth
    CAPITAL_PRESERVE = "preserve"   # 0% — never reinvest, protect capital

REINVEST_RATIOS = {
    "conservative": 0.30,
    "moderate": 0.50,
    "aggressive": 0.75,
    "full_compound": 1.00,
    "preserve": 0.0,
}


@dataclass
class CapitalConfig:
    """User-configurable capital management rules."""
    initial_capital: float = 100_000.0

    # Reinvestment
    reinvest_mode: str = "moderate"
    reinvest_cadence: str = "daily"    # per_trade, daily, weekly

    # Position sizing
    base_risk_pct: float = 1.0         # Risk 1% of trading capital per trade
    max_position_pct: float = 10.0     # Max 10% of capital in single position
    min_position_usd: float = 10.0     # Minimum position $10
    kelly_fraction: float = 0.25       # Quarter-Kelly for safety

    # Profit protection
    profit_lock_pct: float = 20.0      # Lock 20% of profits into untouchable reserve
    profit_lock_trigger: float = 5.0   # Start locking after 5% total return

    # Drawdown circuit breakers
    drawdown_warning_pct: float = 5.0  # Yellow alert
    drawdown_reduce_pct: float = 10.0  # Halve position sizes
    drawdown_pause_pct: float = 15.0   # Stop all trading
    drawdown_kill_pct: float = 25.0    # Close all positions + emergency stop

    # Strategy gating
    min_risk_reward: float = 1.5       # Minimum R:R ratio to accept trade
    min_confidence: float = 0.55       # Minimum signal confidence
    max_daily_trades: int = 20         # Rate limit
    max_daily_loss_pct: float = 3.0    # Daily loss limit (% of capital)
    max_concurrent_positions: int = 10 # Position count limit

    # Consecutive loss protection
    consecutive_loss_reduce: int = 3   # After 3 losses, reduce size 50%
    consecutive_loss_pause: int = 5    # After 5 losses, pause trading

    # Recovery mode
    recovery_position_factor: float = 0.5  # Trade at 50% size during recovery


# ═══════════════════════════════════════════════════════════════════════════════
# CAPITAL STATE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CapitalState:
    """Live account state — persisted to disk."""
    initial_capital: float = 100_000.0
    trading_capital: float = 100_000.0   # Capital actively used for sizing
    locked_reserve: float = 0.0          # Profit locked away (untouchable)
    pending_profit: float = 0.0          # Profit not yet reinvested
    reinvested_total: float = 0.0        # Cumulative reinvested amount
    total_gross_pnl: float = 0.0
    total_fees: float = 0.0
    total_net_pnl: float = 0.0
    peak_equity: float = 100_000.0       # High-water mark
    current_equity: float = 100_000.0    # Current account value

    # Drawdown tracking
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    drawdown_mode: str = "normal"        # normal, warning, reduced, paused, killed

    # Daily tracking
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_date: str = ""

    # Streak tracking
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Reinvestment cycle
    last_cycle_date: str = ""
    cycle_count: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY GATE — Pre-Trade Validation
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TradeDecision:
    """Result of strategy gate evaluation."""
    allowed: bool = True
    position_size_usd: float = 0.0
    position_size_pct: float = 0.0
    risk_amount: float = 0.0
    risk_reward_ratio: float = 0.0
    kelly_size: float = 0.0
    size_adjustment: str = "normal"    # normal, reduced, recovery, consecutive_loss
    rejection_reason: str = ""
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# CAPITAL ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class CapitalEngine:
    """
    Core capital preservation and profit management engine.

    Lifecycle:
      1. evaluate_trade(symbol, confidence, entry, sl, tp) → TradeDecision
      2. If allowed → execute trade
      3. record_trade(symbol, pnl, fee, strategy) → updates state
      4. Engine auto-manages reinvestment, profit locking, drawdown protection
    """

    def __init__(self, user_id: str, config: CapitalConfig = None):
        self.user_id = user_id
        self.config = config or CapitalConfig()
        self._reinvest_ratio = REINVEST_RATIOS.get(self.config.reinvest_mode, 0.5)
        self.state = self._load_state()
        self._trade_log: list[dict] = []

    # ── Position Sizing ───────────────────────────────────────────────────────

    def evaluate_trade(self, symbol: str, confidence: float,
                        entry_price: float, stop_loss: float,
                        take_profit: float = 0,
                        strategy: str = "auto") -> TradeDecision:
        """
        Full pre-trade evaluation:
        1. Check drawdown mode (paused/killed → reject)
        2. Check daily limits (trades, loss)
        3. Check R:R ratio and confidence
        4. Calculate position size (risk-based + Kelly + adjustments)
        5. Check position count limit
        """
        decision = TradeDecision()
        state = self.state
        cfg = self.config

        # Reset daily counters
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.daily_date != today:
            state.daily_pnl = 0.0
            state.daily_trades = 0
            state.daily_date = today

        # 1. DRAWDOWN MODE CHECK
        if state.drawdown_mode == "killed":
            decision.allowed = False
            decision.rejection_reason = f"EMERGENCY: Drawdown {state.current_drawdown_pct:.1f}% exceeded kill threshold ({cfg.drawdown_kill_pct}%)"
            return decision

        if state.drawdown_mode == "paused":
            decision.allowed = False
            decision.rejection_reason = f"Trading paused: drawdown {state.current_drawdown_pct:.1f}% exceeds {cfg.drawdown_pause_pct}%"
            return decision

        # 2. DAILY LIMITS
        if state.daily_trades >= cfg.max_daily_trades:
            decision.allowed = False
            decision.rejection_reason = f"Daily trade limit reached ({cfg.max_daily_trades})"
            return decision

        daily_loss_limit = state.trading_capital * (cfg.max_daily_loss_pct / 100)
        if state.daily_pnl < 0 and abs(state.daily_pnl) >= daily_loss_limit:
            decision.allowed = False
            decision.rejection_reason = f"Daily loss limit reached (${abs(state.daily_pnl):.2f} >= ${daily_loss_limit:.2f})"
            return decision

        # 3. RISK:REWARD CHECK
        if entry_price <= 0 or stop_loss <= 0:
            decision.allowed = False
            decision.rejection_reason = "Invalid entry or stop-loss price"
            return decision

        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            decision.allowed = False
            decision.rejection_reason = "Entry and stop-loss are the same"
            return decision

        if take_profit > 0:
            reward_per_unit = abs(take_profit - entry_price)
            rr = reward_per_unit / risk_per_unit
            decision.risk_reward_ratio = round(rr, 2)

            if rr < cfg.min_risk_reward:
                decision.allowed = False
                decision.rejection_reason = f"R:R ratio {rr:.2f} below minimum {cfg.min_risk_reward}"
                return decision

        # 4. CONFIDENCE CHECK
        if confidence < cfg.min_confidence:
            decision.allowed = False
            decision.rejection_reason = f"Confidence {confidence:.0%} below minimum {cfg.min_confidence:.0%}"
            return decision

        # 5. CONSECUTIVE LOSS CHECK
        if state.consecutive_losses >= cfg.consecutive_loss_pause:
            decision.allowed = False
            decision.rejection_reason = f"{state.consecutive_losses} consecutive losses — trading paused until a manual reset"
            return decision

        # 6. CALCULATE POSITION SIZE

        # Base: risk-based sizing (risk X% of trading capital)
        risk_amount = state.trading_capital * (cfg.base_risk_pct / 100)
        quantity = risk_amount / risk_per_unit
        base_size_usd = quantity * entry_price

        # Kelly criterion adjustment
        win_rate = state.winning_trades / max(state.total_trades, 1)
        avg_win = state.total_gross_pnl / max(state.winning_trades, 1) if state.winning_trades else 0
        avg_loss = abs(state.total_gross_pnl - state.total_net_pnl) / max(state.losing_trades, 1) if state.losing_trades else risk_amount
        if avg_loss > 0:
            win_loss_ratio = avg_win / avg_loss if avg_win > 0 else 1.0
            kelly = win_rate - ((1 - win_rate) / win_loss_ratio) if win_loss_ratio > 0 else 0
            kelly = max(0, kelly) * cfg.kelly_fraction
            kelly_size_usd = state.trading_capital * kelly
            decision.kelly_size = round(kelly_size_usd, 2)
        else:
            kelly_size_usd = base_size_usd

        # Use smaller of risk-based and Kelly
        position_size = min(base_size_usd, kelly_size_usd) if kelly_size_usd > 0 else base_size_usd

        # Apply adjustments
        adjustment = "normal"

        # Consecutive loss reduction
        if state.consecutive_losses >= cfg.consecutive_loss_reduce:
            position_size *= 0.5
            adjustment = "consecutive_loss"
            decision.warnings.append(f"{state.consecutive_losses} consecutive losses — size halved")

        # Drawdown reduction
        if state.drawdown_mode == "reduced":
            position_size *= cfg.recovery_position_factor
            adjustment = "drawdown_reduced"
            decision.warnings.append(f"Drawdown {state.current_drawdown_pct:.1f}% — size reduced")

        # Confidence scaling (scale between 50%-100% based on confidence)
        confidence_scale = 0.5 + (confidence * 0.5)
        position_size *= confidence_scale

        # Cap at max position %
        max_size = state.trading_capital * (cfg.max_position_pct / 100)
        if position_size > max_size:
            position_size = max_size
            decision.warnings.append(f"Capped at {cfg.max_position_pct}% of capital")

        # Floor at minimum
        position_size = max(position_size, cfg.min_position_usd)

        decision.allowed = True
        decision.position_size_usd = round(position_size, 2)
        decision.position_size_pct = round(position_size / state.trading_capital * 100, 2) if state.trading_capital else 0
        decision.risk_amount = round(risk_amount, 2)
        decision.size_adjustment = adjustment

        return decision

    # ── Trade Recording ───────────────────────────────────────────────────────

    def record_trade(self, symbol: str, gross_pnl: float, fee: float = 0,
                      strategy: str = "", position_size: float = 0) -> dict:
        """
        Record a closed trade and update all capital accounting.
        Returns summary of capital state changes.
        """
        net_pnl = gross_pnl - fee
        state = self.state
        cfg = self.config

        # Update P&L totals
        state.total_gross_pnl += gross_pnl
        state.total_fees += fee
        state.total_net_pnl += net_pnl
        state.total_trades += 1

        # Win/loss tracking
        if net_pnl > 0:
            state.winning_trades += 1
            state.consecutive_wins += 1
            state.consecutive_losses = 0
        else:
            state.losing_trades += 1
            state.consecutive_losses += 1
            state.consecutive_wins = 0

        # Daily tracking
        state.daily_pnl += net_pnl
        state.daily_trades += 1

        # Update equity
        state.current_equity = state.trading_capital + state.locked_reserve + state.pending_profit + net_pnl

        # Profit handling
        if net_pnl > 0:
            state.pending_profit += net_pnl
        else:
            # Losses come from trading capital
            state.trading_capital = max(0, state.trading_capital + net_pnl)

        # Reinvestment cycle
        self._maybe_reinvest()

        # Profit locking
        self._maybe_lock_profits()

        # Drawdown calculation
        self._update_drawdown()

        # Persist
        self._save_state()

        trade_record = {
            "symbol": symbol, "gross_pnl": round(gross_pnl, 2),
            "fee": round(fee, 2), "net_pnl": round(net_pnl, 2),
            "strategy": strategy, "position_size": round(position_size, 2),
            "equity_after": round(state.current_equity, 2),
            "drawdown_pct": round(state.current_drawdown_pct, 2),
            "drawdown_mode": state.drawdown_mode,
            "consecutive_wins": state.consecutive_wins,
            "consecutive_losses": state.consecutive_losses,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_log.append(trade_record)

        log.info("capital.trade_recorded",
                 user=self.user_id[:8], symbol=symbol,
                 pnl=round(net_pnl, 2), equity=round(state.current_equity, 2),
                 dd=f"{state.current_drawdown_pct:.1f}%", mode=state.drawdown_mode)

        return trade_record

    # ── Reinvestment ──────────────────────────────────────────────────────────

    def _maybe_reinvest(self):
        """Apply reinvestment based on cadence and mode."""
        if self._reinvest_ratio <= 0 or self.state.pending_profit <= 0:
            return

        should_reinvest = False
        today = date.today()

        if self.config.reinvest_cadence == "per_trade":
            should_reinvest = True
        elif self.config.reinvest_cadence == "daily":
            if self.state.last_cycle_date != today.isoformat():
                should_reinvest = True
        elif self.config.reinvest_cadence == "weekly":
            if today.weekday() == 0:  # Monday
                if self.state.last_cycle_date != today.isoformat():
                    should_reinvest = True

        if not should_reinvest:
            return

        # Don't reinvest during drawdown
        if self.state.drawdown_mode in ("reduced", "paused", "killed"):
            return

        reinvest_amount = self.state.pending_profit * self._reinvest_ratio
        keep_amount = self.state.pending_profit - reinvest_amount

        self.state.trading_capital += reinvest_amount
        self.state.reinvested_total += reinvest_amount
        self.state.pending_profit = keep_amount
        self.state.last_cycle_date = today.isoformat()
        self.state.cycle_count += 1

        log.info("capital.reinvested",
                 amount=round(reinvest_amount, 2),
                 trading_capital=round(self.state.trading_capital, 2),
                 cycle=self.state.cycle_count)

    # ── Profit Locking ────────────────────────────────────────────────────────

    def _maybe_lock_profits(self):
        """Lock a fraction of profits into untouchable reserve."""
        state = self.state
        cfg = self.config

        total_return_pct = (state.total_net_pnl / state.initial_capital * 100) if state.initial_capital else 0

        if total_return_pct < cfg.profit_lock_trigger:
            return

        if state.pending_profit <= 0:
            return

        lock_amount = state.pending_profit * (cfg.profit_lock_pct / 100)
        if lock_amount > 0:
            state.locked_reserve += lock_amount
            state.pending_profit -= lock_amount
            log.info("capital.profit_locked",
                     amount=round(lock_amount, 2),
                     reserve=round(state.locked_reserve, 2))

    # ── Drawdown Protection ───────────────────────────────────────────────────

    def _update_drawdown(self):
        """Update drawdown and set circuit breaker mode."""
        state = self.state
        cfg = self.config

        # Update peak
        if state.current_equity > state.peak_equity:
            state.peak_equity = state.current_equity

        # Calculate drawdown
        if state.peak_equity > 0:
            dd = (state.peak_equity - state.current_equity) / state.peak_equity * 100
            state.current_drawdown_pct = max(0, dd)
            state.max_drawdown_pct = max(state.max_drawdown_pct, state.current_drawdown_pct)
        else:
            state.current_drawdown_pct = 0

        # Set mode
        dd = state.current_drawdown_pct
        old_mode = state.drawdown_mode

        if dd >= cfg.drawdown_kill_pct:
            state.drawdown_mode = "killed"
        elif dd >= cfg.drawdown_pause_pct:
            state.drawdown_mode = "paused"
        elif dd >= cfg.drawdown_reduce_pct:
            state.drawdown_mode = "reduced"
        elif dd >= cfg.drawdown_warning_pct:
            state.drawdown_mode = "warning"
        else:
            state.drawdown_mode = "normal"

        if old_mode != state.drawdown_mode:
            log.warning("capital.drawdown_mode_changed",
                        old=old_mode, new=state.drawdown_mode,
                        drawdown=f"{dd:.1f}%")

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Full capital state summary."""
        s = self.state
        win_rate = (s.winning_trades / s.total_trades * 100) if s.total_trades else 0
        total_return = (s.total_net_pnl / s.initial_capital * 100) if s.initial_capital else 0

        return {
            "initial_capital": round(s.initial_capital, 2),
            "trading_capital": round(s.trading_capital, 2),
            "locked_reserve": round(s.locked_reserve, 2),
            "pending_profit": round(s.pending_profit, 2),
            "current_equity": round(s.current_equity, 2),
            "total_net_pnl": round(s.total_net_pnl, 2),
            "total_return_pct": round(total_return, 2),
            "total_fees": round(s.total_fees, 2),
            "peak_equity": round(s.peak_equity, 2),
            "current_drawdown_pct": round(s.current_drawdown_pct, 2),
            "max_drawdown_pct": round(s.max_drawdown_pct, 2),
            "drawdown_mode": s.drawdown_mode,
            "reinvest_mode": self.config.reinvest_mode,
            "reinvested_total": round(s.reinvested_total, 2),
            "cycle_count": s.cycle_count,
            "total_trades": s.total_trades,
            "winning_trades": s.winning_trades,
            "losing_trades": s.losing_trades,
            "win_rate": round(win_rate, 1),
            "consecutive_wins": s.consecutive_wins,
            "consecutive_losses": s.consecutive_losses,
            "daily_pnl": round(s.daily_pnl, 2),
            "daily_trades": s.daily_trades,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_state(self) -> CapitalState:
        """Load capital state from SQLite."""
        try:
            with sqlite3.connect(_DB_FILE) as c:
                c.execute("""CREATE TABLE IF NOT EXISTS capital_state (
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                )""")
                row = c.execute("SELECT state_json FROM capital_state WHERE user_id=?",
                                (self.user_id,)).fetchone()
                if row:
                    d = json.loads(row[0])
                    state = CapitalState(**{k: d[k] for k in d if k in CapitalState.__dataclass_fields__})
                    return state
        except Exception as e:
            log.warning("capital.load_failed", error=str(e))

        state = CapitalState(
            initial_capital=self.config.initial_capital,
            trading_capital=self.config.initial_capital,
            peak_equity=self.config.initial_capital,
            current_equity=self.config.initial_capital,
        )
        return state

    def _save_state(self):
        """Persist capital state to SQLite."""
        try:
            with sqlite3.connect(_DB_FILE) as c:
                c.execute("""CREATE TABLE IF NOT EXISTS capital_state (
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                )""")
                c.execute("""INSERT OR REPLACE INTO capital_state (user_id, state_json, config_json, updated_at)
                    VALUES (?, ?, ?, datetime('now'))""",
                    (self.user_id, json.dumps(asdict(self.state)),
                     json.dumps(asdict(self.config))))
        except Exception as e:
            log.error("capital.save_failed", error=str(e))

    def reset(self, initial_capital: float = None):
        """Reset capital state."""
        cap = initial_capital or self.config.initial_capital
        self.state = CapitalState(
            initial_capital=cap, trading_capital=cap,
            peak_equity=cap, current_equity=cap,
        )
        self._trade_log = []
        self._save_state()


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

_engines: dict[str, CapitalEngine] = {}

def get_capital_engine(user_id: str, config: CapitalConfig = None) -> CapitalEngine:
    """Get or create capital engine for a user."""
    if user_id not in _engines:
        _engines[user_id] = CapitalEngine(user_id, config)
    return _engines[user_id]
