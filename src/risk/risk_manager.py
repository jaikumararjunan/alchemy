"""
Risk Manager for Alchemy trading bot.
Enforces position limits, drawdown controls, and dynamic sizing.
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
    risk_level: str          # "green", "yellow", "red", "halt"
    can_trade: bool
    rejection_reason: Optional[str] = None


@dataclass
class TradeRecord:
    """Record of a completed trade."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    emotion_score: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RiskManager:
    """
    Enforces trading risk rules:
    - Maximum open positions
    - Daily loss limit
    - Per-trade risk percentage
    - Drawdown-based trading halt
    - Dynamic position sizing based on confidence and volatility
    """

    # Risk thresholds
    DAILY_LOSS_LIMIT_PCT = 5.0       # Halt trading if daily loss > 5%
    DRAWDOWN_WARNING_PCT = 8.0       # Reduce size if drawdown > 8%
    DRAWDOWN_HALT_PCT = 15.0         # Halt trading if drawdown > 15%
    MIN_RISK_REWARD = 1.5            # Minimum R:R ratio to take a trade
    MAX_CORRELATED_POSITIONS = 3     # Max positions in same asset class

    def __init__(self, config):
        self.config = config
        self.max_positions = config.trading.max_open_positions
        self.risk_per_trade_pct = config.trading.risk_per_trade_pct / 100
        self.position_size_usd = config.trading.position_size_usd
        self._peak_balance: Optional[float] = None
        self._daily_start_balance: Optional[float] = None
        self._daily_date: Optional[str] = None
        self._trade_history: List[TradeRecord] = []
        logger.info("RiskManager initialized")

    def evaluate(
        self,
        signal,
        account_balance: float,
        open_positions: int,
        current_price: float,
    ) -> RiskMetrics:
        """
        Evaluate whether it's safe to execute a trade signal.
        Returns RiskMetrics with can_trade=True/False.
        """
        self._update_daily_tracking(account_balance)

        if self._peak_balance is None:
            self._peak_balance = account_balance

        self._peak_balance = max(self._peak_balance, account_balance)

        # Calculate metrics
        daily_pnl = account_balance - (self._daily_start_balance or account_balance)
        daily_pnl_pct = (daily_pnl / self._daily_start_balance * 100) if self._daily_start_balance else 0.0

        drawdown = (self._peak_balance - account_balance) / self._peak_balance * 100 if self._peak_balance > 0 else 0.0
        used_margin = account_balance - account_balance  # simplified

        # Risk level assessment
        risk_level = "green"
        can_trade = True
        rejection_reason = None

        # Check 1: Daily loss limit
        if daily_pnl_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            risk_level = "halt"
            can_trade = False
            rejection_reason = f"Daily loss limit reached: {daily_pnl_pct:.2f}% (limit: {-self.DAILY_LOSS_LIMIT_PCT}%)"
            logger.warning(rejection_reason)

        # Check 2: Drawdown halt
        elif drawdown >= self.DRAWDOWN_HALT_PCT:
            risk_level = "halt"
            can_trade = False
            rejection_reason = f"Max drawdown halt: {drawdown:.2f}% (limit: {self.DRAWDOWN_HALT_PCT}%)"
            logger.warning(rejection_reason)

        # Check 3: Drawdown warning
        elif drawdown >= self.DRAWDOWN_WARNING_PCT:
            risk_level = "red"
            logger.warning(f"High drawdown warning: {drawdown:.2f}%")

        # Check 4: Max open positions
        elif open_positions >= self.max_positions:
            can_trade = False
            rejection_reason = f"Max positions reached: {open_positions}/{self.max_positions}"
            risk_level = "yellow"

        # Check 5: Minimum confidence
        elif signal and signal.confidence < 0.5:
            can_trade = False
            rejection_reason = f"Signal confidence too low: {signal.confidence:.2f} (min: 0.5)"

        # Check 6: Risk-reward ratio
        elif signal and signal.risk_reward_ratio < self.MIN_RISK_REWARD:
            can_trade = False
            rejection_reason = f"R:R ratio too low: {signal.risk_reward_ratio:.2f} (min: {self.MIN_RISK_REWARD})"

        # Check 7: Drawdown warning reduces position allowance
        elif drawdown >= self.DRAWDOWN_WARNING_PCT:
            risk_level = "red"
            # Still allow trading but reduce sizing

        if can_trade and risk_level == "green":
            if daily_pnl_pct < -2.0:
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
        )

    def calculate_position_size(
        self,
        signal,
        account_balance: float,
        current_price: float,
        risk_metrics: RiskMetrics,
    ) -> float:
        """
        Calculate the dollar position size for a trade.
        Uses Kelly-inspired sizing adjusted for signal confidence and risk level.

        Returns: position size in USD
        """
        if not risk_metrics.can_trade:
            return 0.0

        # Base size from config
        base_size = self.position_size_usd

        # Scale by signal quality multiplier (from strategy)
        quality_factor = signal.position_size_multiplier

        # Risk per trade constraint
        max_loss_usd = account_balance * self.risk_per_trade_pct
        stop_distance_pct = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
        risk_limited_size = max_loss_usd / stop_distance_pct if stop_distance_pct > 0 else base_size

        # Drawdown-based reduction
        drawdown_factor = 1.0
        if risk_metrics.max_drawdown_pct >= self.DRAWDOWN_WARNING_PCT:
            drawdown_factor = 0.5

        # Final size: minimum of base, risk-limited, and drawdown-adjusted
        final_size = min(base_size * quality_factor, risk_limited_size) * drawdown_factor

        # Never exceed account balance
        final_size = min(final_size, account_balance * 0.25)  # Max 25% of balance per trade
        final_size = max(final_size, 10.0)  # Minimum $10 trade

        logger.info(
            f"Position size: ${final_size:.2f} | base=${base_size:.2f} | "
            f"quality={quality_factor:.2f} | drawdown_factor={drawdown_factor:.2f}"
        )
        return round(final_size, 2)

    def calculate_contracts(
        self,
        position_size_usd: float,
        current_price: float,
        leverage: int,
        contract_size_usd: float = 1.0,
    ) -> int:
        """
        Convert USD position size to number of contracts for Delta Exchange.
        For BTC perpetuals: 1 contract = $1 USD notional.
        """
        notional_value = position_size_usd * leverage
        contracts = int(notional_value / contract_size_usd)
        return max(contracts, 1)

    def record_trade(self, record: TradeRecord):
        """Record a completed trade for performance tracking."""
        self._trade_history.append(record)
        logger.info(
            f"Trade recorded: {record.side} {record.symbol} | "
            f"PnL: ${record.pnl:.2f} ({record.pnl_pct:.2f}%)"
        )

    def get_performance_summary(self) -> Dict:
        """Get trading performance statistics."""
        if not self._trade_history:
            return {"trades": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0}

        winning = [t for t in self._trade_history if t.pnl > 0]
        total_pnl = sum(t.pnl for t in self._trade_history)
        avg_pnl = total_pnl / len(self._trade_history)

        return {
            "trades": len(self._trade_history),
            "wins": len(winning),
            "losses": len(self._trade_history) - len(winning),
            "win_rate": len(winning) / len(self._trade_history) * 100,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "best_trade": max(t.pnl for t in self._trade_history),
            "worst_trade": min(t.pnl for t in self._trade_history),
        }

    def _update_daily_tracking(self, account_balance: float):
        today = datetime.now(timezone.utc).date().isoformat()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_start_balance = account_balance
            logger.info(f"New trading day started. Opening balance: ${account_balance:.2f}")
