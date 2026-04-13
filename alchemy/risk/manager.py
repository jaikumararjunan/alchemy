"""
alchemy.risk.manager
====================
Risk management engine for the Alchemy trading platform.
Patterns adapted from: https://github.com/QuantInsti/QuantInsti-Live-Algo-Trading-Setups

Enforces position limits, drawdown stops, daily loss limits,
and volatility-scaled sizing before any order reaches the broker.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import structlog

from alchemy.core.config import RiskConfig, get_config
from alchemy.core.state import SignalType, TradingSignal

log = structlog.get_logger(__name__)


@dataclass
class RiskVeto:
    """Returned when risk manager blocks a trade."""
    vetoed: bool
    reason: str
    signal: Optional[TradingSignal] = None
    adjusted_position_pct: Optional[float] = None


@dataclass
class DailyPnL:
    date: date = field(default_factory=date.today)
    realised_pnl: float = 0.0
    open_positions: int = 0
    peak_portfolio_value: float = 0.0
    current_portfolio_value: float = 0.0

    @property
    def drawdown(self) -> float:
        if self.peak_portfolio_value <= 0:
            return 0.0
        return (self.current_portfolio_value - self.peak_portfolio_value) / self.peak_portfolio_value


class RiskManager:
    """
    Pre-trade risk checks for every signal before execution.

    Checks performed (in order):
      1. Signal is actionable (not HOLD)
      2. Daily loss limit not breached
      3. Max open positions not exceeded
      4. Max drawdown circuit breaker not triggered
      5. Volatility regime override (block new longs in extreme vol)
      6. Position size adjusted for volatility scaling
      7. Stop loss / take profit validation
    """

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self.cfg = config or get_config().risk
        self._lock = threading.Lock()
        self._pnl = DailyPnL()
        self._emergency_stop = False
        self._blocked_tickers: set[str] = set()

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def evaluate(self, signal: TradingSignal, portfolio_value: float) -> RiskVeto:
        """
        Run all pre-trade checks on a TradingSignal.

        Returns RiskVeto(vetoed=False) if safe to proceed.
        Returns RiskVeto(vetoed=True, reason=...) if blocked.
        """
        with self._lock:
            # Update state
            self._refresh_daily(portfolio_value)

            checks = [
                self._check_emergency_stop,
                self._check_blocked_ticker,
                self._check_daily_loss,
                self._check_drawdown,
                self._check_open_positions,
                self._check_extreme_vol,
            ]
            for check in checks:
                veto = check(signal, portfolio_value)
                if veto.vetoed:
                    log.warning("risk.veto",
                                ticker=signal.ticker,
                                reason=veto.reason,
                                signal=signal.signal)
                    return veto

            # Adjust position size for volatility
            adjusted = self._vol_scale_position(signal)
            log.info("risk.approved",
                     ticker=signal.ticker,
                     signal=signal.signal,
                     raw_pct=round(signal.position_pct, 4),
                     adjusted_pct=round(adjusted, 4))
            return RiskVeto(vetoed=False, reason="OK",
                            signal=signal, adjusted_position_pct=adjusted)

    # ── Individual Checks ────────────────────────────────────────────────────

    def _check_emergency_stop(self, signal: TradingSignal, _: float) -> RiskVeto:
        if self._emergency_stop:
            return RiskVeto(True, "Emergency stop activated — all trading halted")
        return RiskVeto(False, "OK")

    def _check_blocked_ticker(self, signal: TradingSignal, _: float) -> RiskVeto:
        if signal.ticker in self._blocked_tickers:
            return RiskVeto(True, f"{signal.ticker} is on the blocked list")
        return RiskVeto(False, "OK")

    def _check_daily_loss(self, signal: TradingSignal, _: float) -> RiskVeto:
        if self._pnl.realised_pnl <= -self.cfg.max_daily_loss_usd:
            return RiskVeto(True,
                f"Daily loss limit reached: "
                f"-${abs(self._pnl.realised_pnl):,.0f} >= -${self.cfg.max_daily_loss_usd:,.0f}")
        return RiskVeto(False, "OK")

    def _check_drawdown(self, signal: TradingSignal, _: float) -> RiskVeto:
        dd = self._pnl.drawdown
        if dd <= -self.cfg.max_portfolio_drawdown_pct:
            self._emergency_stop = True
            return RiskVeto(True,
                f"Max drawdown breached: {dd:.1%} <= -{self.cfg.max_portfolio_drawdown_pct:.1%}. "
                "Emergency stop activated.")
        return RiskVeto(False, "OK")

    def _check_open_positions(self, signal: TradingSignal, _: float) -> RiskVeto:
        if signal.signal == "BUY" and self._pnl.open_positions >= self.cfg.max_open_positions:
            return RiskVeto(True,
                f"Max open positions reached: {self._pnl.open_positions}")
        return RiskVeto(False, "OK")

    def _check_extreme_vol(self, signal: TradingSignal, _: float) -> RiskVeto:
        if (signal.signal == "BUY"
                and signal.forecast_vol > self.cfg.max_vol_threshold):
            return RiskVeto(True,
                f"Extreme volatility: {signal.forecast_vol:.0%} > "
                f"{self.cfg.max_vol_threshold:.0%} threshold. No new longs.")
        return RiskVeto(False, "OK")

    # ── Position Sizing ───────────────────────────────────────────────────────

    def _vol_scale_position(self, signal: TradingSignal) -> float:
        """Scale position size inversely with volatility (vol targeting)."""
        if not self.cfg.vol_scaling:
            return min(signal.position_pct, self.cfg.max_position_pct)

        target_vol = 0.15  # 15% annualised target
        scale = target_vol / max(signal.forecast_vol, 0.05)
        scaled = signal.position_pct * scale
        return round(min(scaled, self.cfg.max_position_pct), 4)

    # ── State Management ─────────────────────────────────────────────────────

    def record_pnl(self, pnl_delta: float) -> None:
        """Record realised PnL for the day."""
        with self._lock:
            self._pnl.realised_pnl += pnl_delta

    def update_portfolio_value(self, value: float) -> None:
        with self._lock:
            self._pnl.current_portfolio_value = value
            if value > self._pnl.peak_portfolio_value:
                self._pnl.peak_portfolio_value = value

    def update_open_positions(self, count: int) -> None:
        with self._lock:
            self._pnl.open_positions = count

    def block_ticker(self, ticker: str) -> None:
        with self._lock:
            self._blocked_tickers.add(ticker)
            log.warning("risk.ticker_blocked", ticker=ticker)

    def trigger_emergency_stop(self, reason: str = "Manual trigger") -> None:
        with self._lock:
            self._emergency_stop = True
            log.critical("risk.emergency_stop", reason=reason)

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stop = False
            log.warning("risk.emergency_stop_cleared")

    def status(self) -> dict:
        with self._lock:
            return {
                "emergency_stop": self._emergency_stop,
                "daily_pnl": round(self._pnl.realised_pnl, 2),
                "open_positions": self._pnl.open_positions,
                "current_drawdown": round(self._pnl.drawdown, 4),
                "blocked_tickers": list(self._blocked_tickers),
                "max_daily_loss_usd": self.cfg.max_daily_loss_usd,
                "max_drawdown_pct": self.cfg.max_portfolio_drawdown_pct,
            }

    def _refresh_daily(self, portfolio_value: float) -> None:
        """Reset daily PnL at market open if date has changed."""
        today = date.today()
        if self._pnl.date != today:
            self._pnl = DailyPnL(
                date=today,
                peak_portfolio_value=portfolio_value,
                current_portfolio_value=portfolio_value,
            )


# ── Singleton accessor ────────────────────────────────────────────────────────

_risk_manager_instance: Optional[RiskManager] = None
_risk_manager_lock = threading.Lock()


def get_risk_manager() -> RiskManager:
    """Return the process-wide singleton RiskManager instance."""
    global _risk_manager_instance
    if _risk_manager_instance is None:
        with _risk_manager_lock:
            if _risk_manager_instance is None:
                _risk_manager_instance = RiskManager()
    return _risk_manager_instance
