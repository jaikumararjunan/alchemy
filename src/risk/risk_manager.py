"""
Risk Manager for Alchemy trading bot.
Enforces position limits, drawdown controls, and dynamic sizing.

Brokerage integration
---------------------
Delta Exchange charges a taker fee of 0.05 % per side for market orders.
At 5× leverage the round-trip cost on the margin deposited ≈ 0.50 % per trade.
The risk manager:
  1. Deducts the round-trip fee from the expected profit when checking R:R.
  2. Rejects trades whose net (fee-adjusted) take-profit distance is too small
     to justify the risk.
  3. Reports fee cost in USD alongside P&L metrics.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskMetrics:
    """Current risk state of the portfolio."""
    account_balance: float
    used_margin: float
    available_balance: float
    open_positions: int
    daily_pnl: float
    daily_pnl_pct: float
    max_drawdown_pct: float
    risk_level: str              # "green" | "yellow" | "red" | "halt"
    can_trade: bool
    rejection_reason: Optional[str] = None
    # Fee transparency
    round_trip_fee_pct: float = 0.0    # % of margin consumed by fees per trade
    estimated_fee_usd: float = 0.0     # estimated fee cost in USD for next trade


@dataclass
class TradeRecord:
    """Record of a completed trade (including brokerage cost)."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    fee_usd: float = 0.0               # total round-trip brokerage paid
    net_pnl: float = 0.0               # pnl after fee deduction
    emotion_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RiskManager:
    """
    Enforces trading risk rules:
    - Maximum open positions
    - Daily loss limit
    - Per-trade risk percentage
    - Drawdown-based trading halt
    - Dynamic position sizing (confidence, volatility, drawdown, fees)
    """

    DAILY_LOSS_LIMIT_PCT  = 5.0    # halt if daily loss > 5 %
    DRAWDOWN_WARNING_PCT  = 8.0    # reduce size if drawdown > 8 %
    DRAWDOWN_HALT_PCT     = 15.0   # halt if drawdown > 15 %
    MIN_RISK_REWARD_NET   = 1.5    # minimum NET (fee-adjusted) R:R
    MIN_CONFIDENCE        = 0.50

    def __init__(self, config):
        self.config = config
        self.max_positions       = config.trading.max_open_positions
        self.risk_per_trade_pct  = config.trading.risk_per_trade_pct / 100
        self.position_size_usd   = config.trading.position_size_usd
        self.leverage            = getattr(config.trading, "leverage", 5)
        self.taker_fee           = getattr(config.trading, "taker_fee_rate", 0.0005)

        self._peak_balance: Optional[float] = None
        self._daily_start_balance: Optional[float] = None
        self._daily_date: Optional[str] = None
        self._trade_history: List[TradeRecord] = []
        logger.info("RiskManager initialised (taker_fee=%.4f%%, leverage=%d×)",
                    self.taker_fee * 100, self.leverage)

    # ── Brokerage helpers ─────────────────────────────────────────────────────

    def round_trip_fee_pct_of_margin(self) -> float:
        """
        Round-trip taker fee expressed as a percentage of the margin deposited.

        Notional = margin × leverage
        Fee per side = taker_fee × notional = taker_fee × leverage × margin
        Round-trip = 2 × taker_fee × leverage   (as a fraction of margin)
        """
        return self.taker_fee * 2 * self.leverage   # fraction; multiply by 100 for %

    def estimate_fee_usd(self, position_size_usd: float) -> float:
        """
        Dollar cost of opening and closing *position_size_usd* (margin).
        Fee applies to the full notional = margin × leverage.
        """
        notional = position_size_usd * self.leverage
        return round(notional * self.taker_fee * 2, 4)   # entry + exit

    def net_rr(self, signal) -> float:
        """
        Fee-adjusted net R:R for a TradeSignal.
        Returns 0 if signal doesn't support it.
        """
        return getattr(signal, "net_rr_after_fees", signal.risk_reward_ratio)

    # ── Main evaluate ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        signal,
        account_balance: float,
        open_positions: int,
        current_price: float,
    ) -> RiskMetrics:
        """
        Evaluate whether it is safe to execute a trade signal.
        Returns RiskMetrics with can_trade=True/False.
        """
        self._update_daily_tracking(account_balance)

        if self._peak_balance is None:
            self._peak_balance = account_balance
        self._peak_balance = max(self._peak_balance, account_balance)

        daily_pnl     = account_balance - (self._daily_start_balance or account_balance)
        daily_pnl_pct = (
            daily_pnl / self._daily_start_balance * 100
            if self._daily_start_balance else 0.0
        )
        drawdown = (
            (self._peak_balance - account_balance) / self._peak_balance * 100
            if self._peak_balance > 0 else 0.0
        )

        rt_fee_pct   = self.round_trip_fee_pct_of_margin() * 100   # as %
        est_fee_usd  = self.estimate_fee_usd(self.position_size_usd)

        risk_level       = "green"
        can_trade        = True
        rejection_reason = None

        # ── Hard stops ────────────────────────────────────────────────────────

        if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            risk_level       = "halt"
            can_trade        = False
            rejection_reason = (
                f"Daily loss limit reached: {daily_pnl_pct:.2f}% "
                f"(limit: -{self.DAILY_LOSS_LIMIT_PCT}%)"
            )
            logger.warning(rejection_reason)

        elif drawdown >= self.DRAWDOWN_HALT_PCT:
            risk_level       = "halt"
            can_trade        = False
            rejection_reason = (
                f"Max drawdown halt: {drawdown:.2f}% "
                f"(limit: {self.DRAWDOWN_HALT_PCT}%)"
            )
            logger.warning(rejection_reason)

        elif open_positions >= self.max_positions:
            can_trade        = False
            rejection_reason = f"Max positions reached: {open_positions}/{self.max_positions}"
            risk_level       = "yellow"

        elif signal and signal.confidence < self.MIN_CONFIDENCE:
            can_trade        = False
            rejection_reason = (
                f"Signal confidence too low: {signal.confidence:.2f} "
                f"(min: {self.MIN_CONFIDENCE})"
            )

        elif signal:
            net_rr = self.net_rr(signal)
            if net_rr < self.MIN_RISK_REWARD_NET:
                can_trade        = False
                rejection_reason = (
                    f"Net R:R after fees too low: {net_rr:.2f} "
                    f"(need ≥ {self.MIN_RISK_REWARD_NET}, "
                    f"fee cost ≈ {rt_fee_pct:.2f}% of margin)"
                )
                logger.info(rejection_reason)

        # ── Risk-level colouring ──────────────────────────────────────────────
        if can_trade:
            if drawdown >= self.DRAWDOWN_WARNING_PCT:
                risk_level = "red"
                logger.warning("High drawdown: %.2f%%", drawdown)
            elif daily_pnl_pct < -2.0:
                risk_level = "yellow"

        return RiskMetrics(
            account_balance=account_balance,
            used_margin=0.0,
            available_balance=account_balance,
            open_positions=open_positions,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            max_drawdown_pct=drawdown,
            risk_level=risk_level,
            can_trade=can_trade,
            rejection_reason=rejection_reason,
            round_trip_fee_pct=rt_fee_pct,
            estimated_fee_usd=est_fee_usd,
        )

    # ── Position sizing ───────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        signal,
        account_balance: float,
        current_price: float,
        risk_metrics: RiskMetrics,
    ) -> float:
        """
        Dollar margin to commit for this trade.

        Sizing is Kelly-inspired and adjusts for:
          - signal quality multiplier
          - maximum loss constraint (risk_per_trade_pct of balance)
          - drawdown-based reduction
          - brokerage: fee cost is subtracted from the available risk budget
        """
        if not risk_metrics.can_trade:
            return 0.0

        base_size    = self.position_size_usd
        quality      = signal.position_size_multiplier

        # Risk budget per trade (in USD)
        max_loss_usd     = account_balance * self.risk_per_trade_pct
        # Fee is a cost that eats into the risk budget before we even hit SL
        fee_cost_usd     = self.estimate_fee_usd(base_size * quality)
        adjusted_budget  = max(max_loss_usd - fee_cost_usd, max_loss_usd * 0.5)

        stop_dist_pct    = (
            abs(signal.entry_price - signal.stop_loss) / signal.entry_price
            if signal.entry_price else 0.02
        )
        risk_limited_size = (
            adjusted_budget / stop_dist_pct
            if stop_dist_pct > 0 else base_size
        )

        # Drawdown factor
        drawdown_factor = 0.5 if risk_metrics.max_drawdown_pct >= self.DRAWDOWN_WARNING_PCT else 1.0

        final_size = min(base_size * quality, risk_limited_size) * drawdown_factor
        final_size = min(final_size, account_balance * 0.25)   # hard cap 25 % of balance
        final_size = max(final_size, 10.0)                     # minimum $10

        fee_on_final = self.estimate_fee_usd(final_size)
        logger.info(
            "Position size: $%.2f | quality=%.2f | fee≈$%.2f (%.2f%% of margin) "
            "| drawdown_factor=%.2f",
            final_size, quality, fee_on_final,
            fee_on_final / final_size * 100 if final_size else 0,
            drawdown_factor,
        )
        return round(final_size, 2)

    def calculate_contracts(
        self,
        position_size_usd: float,
        current_price: float,
        leverage: int,
        contract_size_usd: float = 1.0,
    ) -> int:
        """Convert USD margin to number of contracts for Delta Exchange."""
        notional  = position_size_usd * leverage
        contracts = int(notional / contract_size_usd)
        return max(contracts, 1)

    # ── Trade recording ───────────────────────────────────────────────────────

    def record_trade(self, record: TradeRecord):
        """Record a completed trade. Auto-calculates net_pnl if not set."""
        if record.net_pnl == 0.0 and record.fee_usd > 0:
            record.net_pnl = record.pnl - record.fee_usd
        self._trade_history.append(record)
        logger.info(
            "Trade recorded: %s %s | gross PnL: $%.2f | fee: $%.2f | net PnL: $%.2f",
            record.side, record.symbol,
            record.pnl, record.fee_usd, record.net_pnl,
        )

    def get_performance_summary(self) -> Dict:
        if not self._trade_history:
            return {
                "trades": 0, "win_rate": 0, "avg_pnl": 0,
                "total_pnl": 0, "total_fees_paid": 0, "total_net_pnl": 0,
            }

        winning    = [t for t in self._trade_history if t.net_pnl > 0]
        total_pnl  = sum(t.pnl     for t in self._trade_history)
        total_fees = sum(t.fee_usd  for t in self._trade_history)
        total_net  = sum(t.net_pnl  for t in self._trade_history)
        avg_pnl    = total_pnl / len(self._trade_history)

        return {
            "trades"        : len(self._trade_history),
            "wins"          : len(winning),
            "losses"        : len(self._trade_history) - len(winning),
            "win_rate"      : len(winning) / len(self._trade_history) * 100,
            "total_pnl"     : round(total_pnl, 4),
            "avg_pnl"       : round(avg_pnl, 4),
            "total_fees_paid": round(total_fees, 4),
            "total_net_pnl" : round(total_net, 4),
            "best_trade"    : max(t.net_pnl for t in self._trade_history),
            "worst_trade"   : min(t.net_pnl for t in self._trade_history),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _update_daily_tracking(self, account_balance: float):
        today = datetime.now(timezone.utc).date().isoformat()
        if self._daily_date != today:
            self._daily_date          = today
            self._daily_start_balance = account_balance
            logger.info("New trading day. Opening balance: $%.2f", account_balance)
