"""
alchemy.paper_trading.models
===============================
Data models for paper trading and backtesting.
Each user gets their own isolated paper portfolio.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET     = "market"
    LIMIT      = "limit"
    STOP_LOSS  = "stop_loss"


class OrderStatus(str, Enum):
    PENDING   = "pending"
    FILLED    = "filled"
    CANCELLED = "cancelled"
    REJECTED  = "rejected"
    EXPIRED   = "expired"


class PositionSide(str, Enum):
    LONG  = "long"
    SHORT = "short"
    FLAT  = "flat"


@dataclass
class PaperOrder:
    """A single paper trade order."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    user_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: float = 0.0           # Limit price (0 = market)
    stop_price: float = 0.0      # Stop loss trigger
    filled_price: float = 0.0    # Actual fill price
    filled_at: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    strategy: str = "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""
    slippage_pct: float = 0.05   # Simulated slippage %

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "filled_price": round(self.filled_price, 6),
            "status": self.status.value,
            "strategy": self.strategy,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "notes": self.notes,
        }


@dataclass
class PaperPosition:
    """An open paper trading position."""
    symbol: str = ""
    side: PositionSide = PositionSide.FLAT
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    opened_at: Optional[datetime] = None
    strategy: str = "manual"

    @property
    def unrealized_pnl(self) -> float:
        if self.side == PositionSide.LONG:
            return (self.current_price - self.avg_entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            return (self.avg_entry_price - self.current_price) * self.quantity
        return 0.0

    @property
    def unrealized_pct(self) -> float:
        cost = self.avg_entry_price * self.quantity
        if cost == 0:
            return 0.0
        return (self.unrealized_pnl / cost) * 100

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": round(self.quantity, 8),
            "avg_entry_price": round(self.avg_entry_price, 6),
            "current_price": round(self.current_price, 6),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pct": round(self.unrealized_pct, 2),
            "market_value": round(self.market_value, 2),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "strategy": self.strategy,
        }


@dataclass
class PaperPortfolio:
    """User's complete paper trading portfolio."""
    user_id: str = ""
    initial_balance: float = 100000.0
    cash_balance: float = 100000.0
    positions: dict = field(default_factory=dict)      # symbol → PaperPosition
    order_history: list = field(default_factory=list)   # list[PaperOrder]
    trade_log: list = field(default_factory=list)       # completed trade records
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def portfolio_value(self) -> float:
        return self.cash_balance + sum(p.market_value for p in self.positions.values())

    @property
    def total_return_pct(self) -> float:
        if self.initial_balance == 0:
            return 0.0
        return ((self.portfolio_value - self.initial_balance) / self.initial_balance) * 100

    @property
    def realized_pnl(self) -> float:
        return sum(t.get("net_pnl", 0) for t in self.trade_log)

    def summary(self) -> dict:
        wins = [t for t in self.trade_log if t.get("net_pnl", 0) > 0]
        losses = [t for t in self.trade_log if t.get("net_pnl", 0) <= 0]
        total_trades = len(self.trade_log)
        return {
            "user_id": self.user_id,
            "initial_balance": self.initial_balance,
            "cash_balance": round(self.cash_balance, 2),
            "portfolio_value": round(self.portfolio_value, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "open_positions": len(self.positions),
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / total_trades * 100, 1) if total_trades else 0,
            "positions": {s: p.to_dict() for s, p in self.positions.items()},
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    user_id: str = ""
    strategy: str = "sma_crossover"
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    start_date: str = ""       # "2025-01-01"
    end_date: str = ""         # "2025-12-31"
    initial_capital: float = 100000.0
    position_size_pct: float = 10.0    # % of capital per trade
    stop_loss_pct: float = 2.0         # Stop loss %
    take_profit_pct: float = 4.0       # Take profit %
    commission_pct: float = 0.1        # Fee per trade %
    slippage_pct: float = 0.05         # Simulated slippage
    # Strategy parameters
    fast_period: int = 9       # Fast MA period
    slow_period: int = 21      # Slow MA period
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    config: Optional[BacktestConfig] = None
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    # Performance
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    total_fees: float = 0.0
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    candles_processed: int = 0
    status: str = "pending"   # pending, running, completed, failed
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "config": {
                "strategy": self.config.strategy if self.config else "",
                "symbol": self.config.symbol if self.config else "",
                "interval": self.config.interval if self.config else "",
                "start_date": self.config.start_date if self.config else "",
                "end_date": self.config.end_date if self.config else "",
                "initial_capital": self.config.initial_capital if self.config else 0,
                "position_size_pct": self.config.position_size_pct if self.config else 0,
                "stop_loss_pct": self.config.stop_loss_pct if self.config else 0,
                "take_profit_pct": self.config.take_profit_pct if self.config else 0,
                "fast_period": self.config.fast_period if self.config else 0,
                "slow_period": self.config.slow_period if self.config else 0,
            } if self.config else {},
            "performance": {
                "total_return_pct": round(self.total_return_pct, 2),
                "total_pnl": round(self.total_pnl, 2),
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 1),
                "avg_win": round(self.avg_win, 2),
                "avg_loss": round(self.avg_loss, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 3),
                "profit_factor": round(self.profit_factor, 2),
                "total_fees": round(self.total_fees, 2),
            },
            "candles_processed": self.candles_processed,
            "trade_count": len(self.trades),
            "equity_points": len(self.equity_curve),
            "trades": self.trades[-50:],   # Last 50 trades
            "equity_curve": self.equity_curve,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
