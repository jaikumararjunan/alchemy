"""
Capital & Profit Reinvestment Manager for Alchemy.

Tracks the total trading capital, realized profits, and dynamically adjusts
position sizing as the account grows.  Profits are compounded back into
future positions according to configurable reinvestment rules.

Key concepts
------------
  initial_capital   : Starting USD balance (seed capital, never changes)
  current_capital   : Live account balance (initial + all net profits/losses)
  realized_profit   : Cumulative net profit banked so far
  reinvest_ratio    : Fraction of each realized profit cycle to reinvest (0–1)
  trading_capital   : The slice of capital actively used for sizing trades
                      = initial_capital + reinvested_profit_so_far

Reinvestment modes
------------------
  "conservative"  reinvest_ratio=0.30  — reinvest 30% of profits
  "moderate"      reinvest_ratio=0.50  — reinvest 50% of profits  (default)
  "aggressive"    reinvest_ratio=0.75  — reinvest 75% of profits
  "full_compound" reinvest_ratio=1.00  — reinvest 100% (pure geometric growth)

Profit cycles
-------------
  Profits are harvested and compounded on a configurable cadence:
    - "per_trade"  : reinvest after every closed trade
    - "daily"      : reinvest once per calendar day
    - "weekly"     : reinvest on Monday of each new week

Safety rails
------------
  - Max position size capped at `max_position_pct` of trading capital (default 25%)
  - Drawdown guard: if drawdown ≥ drawdown_pause_pct (default 10%) reinvestment
    is paused and sizes are reduced to `drawdown_size_factor` of normal
  - Profit lock: if total profit ≥ profit_lock_pct, a fixed fraction is moved to
    a "locked" (non-tradeable) reserve to protect gains

Usage
-----
    mgr = CapitalManager(initial_capital=1000.0, mode="moderate")
    size = mgr.position_size(confidence=0.75, current_balance=1120.0)
    mgr.record_trade(profit=25.0, fee=1.5)
    print(mgr.summary())
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Literal, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


ReinvestMode = Literal["conservative", "moderate", "aggressive", "full_compound"]
CycleCadence = Literal["per_trade", "daily", "weekly"]


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class CapitalConfig:
    """Configuration for the CapitalManager."""

    initial_capital: float = 1000.0
    mode: ReinvestMode = "moderate"
    cadence: CycleCadence = "daily"

    # Position sizing
    base_position_pct: float = 0.10    # 10% of trading capital per trade (base)
    max_position_pct: float = 0.25     # hard cap: never exceed 25% per trade
    min_position_usd: float = 10.0     # minimum position regardless of sizing

    # Profit locking
    profit_lock_pct: float = 0.20      # lock 20% of profits into reserve
    profit_lock_trigger_pct: float = 0.15  # trigger locking once total profit ≥ 15%

    # Drawdown guard
    drawdown_pause_pct: float = 10.0   # pause reinvestment if drawdown ≥ 10%
    drawdown_size_factor: float = 0.50 # halve position sizes during drawdown

    # Kelly fraction (applied to confidence-scaled sizing)
    kelly_fraction: float = 0.25       # quarter-Kelly for safety


# ── Reinvestment ratios ────────────────────────────────────────────────────────

_MODE_RATIO: Dict[str, float] = {
    "conservative": 0.30,
    "moderate": 0.50,
    "aggressive": 0.75,
    "full_compound": 1.00,
}


# ── Trade snapshot ─────────────────────────────────────────────────────────────


@dataclass
class CapitalTradeRecord:
    """Lightweight record of a closed trade for capital-manager tracking."""

    gross_pnl: float          # profit/loss before fees
    fee_usd: float            # brokerage cost
    net_pnl: float            # gross_pnl - fee_usd
    position_size_usd: float  # margin committed
    strategy_name: str = ""
    symbol: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Equity snapshot ───────────────────────────────────────────────────────────


@dataclass
class EquitySnapshot:
    """Periodic account snapshot for drawdown calculation."""

    balance: float
    trading_capital: float
    locked_reserve: float
    realized_profit: float
    reinvested_profit: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Main manager ──────────────────────────────────────────────────────────────


class CapitalManager:
    """
    Manages total capital with profit reinvestment.

    Call flow:
      1. Instantiate with initial_capital and reinvestment mode.
      2. Call `position_size(confidence, current_balance)` before every trade.
      3. Call `record_trade(gross_pnl, fee_usd, ...)` after every close.
      4. The manager automatically compounds profits per the chosen cadence.
      5. Call `summary()` to inspect the current state.
    """

    def __init__(
        self,
        initial_capital: float = 1000.0,
        mode: ReinvestMode = "moderate",
        cadence: CycleCadence = "daily",
        config: Optional[CapitalConfig] = None,
    ):
        self.cfg = config or CapitalConfig(
            initial_capital=initial_capital,
            mode=mode,
            cadence=cadence,
        )
        self._reinvest_ratio = _MODE_RATIO[self.cfg.mode]

        # Capital accounting
        self._initial_capital = self.cfg.initial_capital
        self._trading_capital = self.cfg.initial_capital   # grows with reinvestment
        self._locked_reserve = 0.0                         # profit locked away
        self._pending_profit = 0.0                         # profit not yet compounded
        self._reinvested_total = 0.0                       # cumulative reinvested amount
        self._total_gross_profit = 0.0
        self._total_fees = 0.0
        self._total_net_profit = 0.0
        self._peak_balance = self.cfg.initial_capital

        # Cycle tracking
        self._last_cycle_date: Optional[date] = None
        self._last_cycle_week: Optional[int] = None
        self._cycle_count = 0

        # Trade history
        self._trades: List[CapitalTradeRecord] = []
        self._snapshots: List[EquitySnapshot] = []

        logger.info(
            "CapitalManager: initial=$%.2f mode=%s cadence=%s reinvest_ratio=%.0f%%",
            self._initial_capital,
            self.cfg.mode,
            self.cfg.cadence,
            self._reinvest_ratio * 100,
        )

    # ── Position sizing ───────────────────────────────────────────────────────

    def position_size(
        self,
        confidence: float,
        current_balance: float,
        win_rate: Optional[float] = None,
        avg_win_loss_ratio: Optional[float] = None,
    ) -> float:
        """
        Calculate USD margin to commit for the next trade.

        Sizing layers:
          1. Base: `base_position_pct` × trading_capital
          2. Confidence scaling: Kelly-inspired multiplier based on signal confidence
          3. Optional full Kelly if win_rate and win/loss ratio are provided
          4. Drawdown guard: halve size if account is in significant drawdown
          5. Hard cap: never exceed `max_position_pct` × current_balance
          6. Minimum floor: `min_position_usd`

        Args:
            confidence         : signal confidence 0–1
            current_balance    : live account balance from exchange
            win_rate           : historical win rate (optional, for Kelly calculation)
            avg_win_loss_ratio : average win / average loss ratio (optional)

        Returns:
            position size in USD (margin)
        """
        self._peak_balance = max(self._peak_balance, current_balance)
        drawdown_pct = (
            (self._peak_balance - current_balance) / self._peak_balance * 100
            if self._peak_balance > 0
            else 0.0
        )

        # Base size from trading capital
        base_size = self._trading_capital * self.cfg.base_position_pct

        # Confidence scaling (quarter-Kelly as default)
        if win_rate is not None and avg_win_loss_ratio is not None and avg_win_loss_ratio > 0:
            # Full Kelly fraction: f* = (p * b - q) / b  where b = win/loss ratio, p=win_rate
            kelly_full = (win_rate * avg_win_loss_ratio - (1 - win_rate)) / avg_win_loss_ratio
            kelly_full = max(kelly_full, 0.0)
            kelly_size = self._trading_capital * kelly_full * self.cfg.kelly_fraction
        else:
            # Confidence-weighted Kelly approximation
            kelly_size = base_size * confidence * self.cfg.kelly_fraction * 4  # scales to base at conf=1

        size = min(base_size, kelly_size) if kelly_size > 0 else base_size * confidence

        # Drawdown guard
        if drawdown_pct >= self.cfg.drawdown_pause_pct:
            size *= self.cfg.drawdown_size_factor
            logger.warning(
                "Drawdown guard active: %.1f%% drawdown → size reduced to $%.2f",
                drawdown_pct, size,
            )

        # Hard cap: never risk more than max_position_pct of live balance
        hard_cap = current_balance * self.cfg.max_position_pct
        size = min(size, hard_cap)

        # Minimum floor
        size = max(size, self.cfg.min_position_usd)

        logger.info(
            "CapitalMgr position_size: $%.2f | trading_cap=$%.2f conf=%.2f drawdown=%.1f%%",
            size, self._trading_capital, confidence, drawdown_pct,
        )
        return round(size, 2)

    # ── Trade recording ───────────────────────────────────────────────────────

    def record_trade(
        self,
        gross_pnl: float,
        fee_usd: float,
        position_size_usd: float = 0.0,
        strategy_name: str = "",
        symbol: str = "",
    ) -> None:
        """
        Record the result of a closed trade and trigger compounding if due.

        Args:
            gross_pnl        : profit/loss before fees
            fee_usd          : brokerage cost (entry + exit)
            position_size_usd: margin that was committed
            strategy_name    : name of the strategy that generated the trade
            symbol           : trading symbol
        """
        net_pnl = gross_pnl - fee_usd
        record = CapitalTradeRecord(
            gross_pnl=gross_pnl,
            fee_usd=fee_usd,
            net_pnl=net_pnl,
            position_size_usd=position_size_usd,
            strategy_name=strategy_name,
            symbol=symbol,
        )
        self._trades.append(record)

        # Accumulate totals
        self._total_gross_profit += gross_pnl
        self._total_fees += fee_usd
        self._total_net_profit += net_pnl

        if net_pnl > 0:
            self._pending_profit += net_pnl
            logger.info(
                "CapitalMgr: trade profit=$%.2f (net) | pending_profit=$%.2f",
                net_pnl, self._pending_profit,
            )
        else:
            # Losses reduce pending profit buffer first, then locked reserve, then capital
            self._absorb_loss(abs(net_pnl))
            logger.info(
                "CapitalMgr: trade loss=$%.2f | trading_cap=$%.2f",
                abs(net_pnl), self._trading_capital,
            )

        # Trigger reinvestment cycle if due
        if self.cfg.cadence == "per_trade":
            self._run_reinvestment_cycle()

    def end_of_day(self) -> None:
        """Call this at the end of each trading day for daily/weekly compounding."""
        today = date.today()
        week = today.isocalendar()[1]

        if self.cfg.cadence == "daily":
            if self._last_cycle_date != today:
                self._last_cycle_date = today
                self._run_reinvestment_cycle()

        elif self.cfg.cadence == "weekly":
            if self._last_cycle_week != week:
                self._last_cycle_week = week
                self._run_reinvestment_cycle()

        self._take_snapshot()

    # ── Reinvestment logic ────────────────────────────────────────────────────

    def _run_reinvestment_cycle(self) -> None:
        """
        Compound pending profits back into trading capital.

        Steps:
          1. From pending_profit, lock `profit_lock_pct` into reserve (if triggered).
          2. Of the remainder, reinvest `reinvest_ratio` into trading capital.
          3. The rest is kept as "withdrawn / secured" profit outside trading capital.
        """
        if self._pending_profit <= 0:
            return

        profit = self._pending_profit
        self._pending_profit = 0.0
        self._cycle_count += 1

        # Profit lock — protect gains once threshold is met
        profit_pct_of_initial = self._total_net_profit / self._initial_capital
        lock_amount = 0.0
        if profit_pct_of_initial >= self.cfg.profit_lock_trigger_pct:
            lock_amount = profit * self.cfg.profit_lock_pct
            self._locked_reserve += lock_amount
            profit -= lock_amount

        # Reinvest portion
        reinvest_amount = profit * self._reinvest_ratio
        withdrawn_amount = profit - reinvest_amount

        self._trading_capital += reinvest_amount
        self._reinvested_total += reinvest_amount

        logger.info(
            "Reinvestment cycle #%d: profit=$%.2f lock=$%.2f "
            "reinvest=$%.2f (%.0f%%) withdrawn=$%.2f | new trading_cap=$%.2f",
            self._cycle_count,
            profit + lock_amount,
            lock_amount,
            reinvest_amount,
            self._reinvest_ratio * 100,
            withdrawn_amount,
            self._trading_capital,
        )

    def _absorb_loss(self, loss: float) -> None:
        """Apply a loss: reduce pending profit buffer first, then trading capital."""
        if self._pending_profit >= loss:
            self._pending_profit -= loss
            return
        loss -= self._pending_profit
        self._pending_profit = 0.0
        self._trading_capital = max(self._trading_capital - loss, self.cfg.min_position_usd * 2)

    # ── Compound growth projection ────────────────────────────────────────────

    def project_growth(
        self,
        daily_return_pct: float,
        days: int,
        win_rate: float = 0.55,
    ) -> List[Dict]:
        """
        Project account growth over `days` days assuming a constant daily return.

        Args:
            daily_return_pct : average daily net return as a percentage of trading capital
            days             : number of trading days to project
            win_rate         : assumed win rate (used to estimate daily trade count weight)

        Returns:
            List of {day, trading_capital, total_capital, profit, growth_pct} dicts
        """
        capital = self._trading_capital
        locked = self._locked_reserve
        initial = self._initial_capital
        results = []

        for d in range(1, days + 1):
            daily_profit = capital * (daily_return_pct / 100) * win_rate

            # Lock
            lock = 0.0
            cumulative_profit_pct = (capital + locked - initial) / initial
            if cumulative_profit_pct >= self.cfg.profit_lock_trigger_pct:
                lock = daily_profit * self.cfg.profit_lock_pct
                locked += lock
                daily_profit -= lock

            # Reinvest
            reinvest = daily_profit * self._reinvest_ratio
            capital += reinvest

            total = capital + locked
            results.append({
                "day": d,
                "trading_capital": round(capital, 2),
                "locked_reserve": round(locked, 2),
                "total_capital": round(total, 2),
                "daily_profit": round(daily_profit + lock, 2),
                "growth_pct": round((total - initial) / initial * 100, 2),
                "cagr_annualised": round(
                    ((total / initial) ** (252 / d) - 1) * 100, 2
                ) if d >= 5 else 0.0,
            })

        return results

    # ── Mode switching ────────────────────────────────────────────────────────

    def set_mode(self, mode: ReinvestMode) -> None:
        """Change reinvestment mode at runtime."""
        self._reinvest_ratio = _MODE_RATIO[mode]
        self.cfg.mode = mode
        logger.info(
            "CapitalMgr mode changed to %s (reinvest_ratio=%.0f%%)",
            mode, self._reinvest_ratio * 100,
        )

    # ── Reporting ─────────────────────────────────────────────────────────────

    def summary(self) -> Dict:
        """Return a full snapshot of the current capital state."""
        total_capital = self._trading_capital + self._locked_reserve
        growth_pct = (total_capital - self._initial_capital) / self._initial_capital * 100

        win_trades = [t for t in self._trades if t.net_pnl > 0]
        loss_trades = [t for t in self._trades if t.net_pnl <= 0]
        win_rate = len(win_trades) / len(self._trades) * 100 if self._trades else 0.0
        avg_win = (
            sum(t.net_pnl for t in win_trades) / len(win_trades) if win_trades else 0.0
        )
        avg_loss = (
            sum(t.net_pnl for t in loss_trades) / len(loss_trades) if loss_trades else 0.0
        )
        profit_factor = (
            abs(sum(t.net_pnl for t in win_trades)) /
            max(abs(sum(t.net_pnl for t in loss_trades)), 0.01)
        )

        return {
            # Capital breakdown
            "initial_capital": round(self._initial_capital, 2),
            "trading_capital": round(self._trading_capital, 2),
            "locked_reserve": round(self._locked_reserve, 2),
            "total_capital": round(total_capital, 2),
            "growth_pct": round(growth_pct, 2),

            # Profit accounting
            "total_gross_profit": round(self._total_gross_profit, 2),
            "total_fees_paid": round(self._total_fees, 2),
            "total_net_profit": round(self._total_net_profit, 2),
            "reinvested_total": round(self._reinvested_total, 2),
            "pending_profit": round(self._pending_profit, 2),

            # Reinvestment config
            "mode": self.cfg.mode,
            "reinvest_ratio_pct": round(self._reinvest_ratio * 100, 1),
            "cadence": self.cfg.cadence,
            "cycle_count": self._cycle_count,

            # Trade performance
            "total_trades": len(self._trades),
            "wins": len(win_trades),
            "losses": len(loss_trades),
            "win_rate_pct": round(win_rate, 1),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),

            # Risk
            "peak_balance": round(self._peak_balance, 2),
        }

    def _take_snapshot(self) -> None:
        self._snapshots.append(EquitySnapshot(
            balance=self._trading_capital + self._locked_reserve,
            trading_capital=self._trading_capital,
            locked_reserve=self._locked_reserve,
            realized_profit=self._total_net_profit,
            reinvested_profit=self._reinvested_total,
        ))

    @property
    def trading_capital(self) -> float:
        """Current active trading capital (includes reinvested profits)."""
        return self._trading_capital

    @property
    def total_capital(self) -> float:
        """Total capital including locked reserve."""
        return self._trading_capital + self._locked_reserve

    @property
    def growth_pct(self) -> float:
        """Total percentage growth from initial capital."""
        return (self.total_capital - self._initial_capital) / self._initial_capital * 100
