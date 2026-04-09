"""
alchemy.analytics.pnl_segregation
====================================
Investment Profit & Loss Segregation Engine.

Tracks and segregates P&L across multiple dimensions:
  - By exchange (Binance, Delta, Angel, Kite)
  - By strategy (SMA Crossover, ML Ensemble, Manual, etc.)
  - By asset class (crypto_spot, crypto_futures, equity, derivatives, commodity)
  - By time period (daily, weekly, monthly, quarterly, yearly)
  - By trade type (long, short)
  - By symbol (individual instrument P&L)

Tax-ready:
  - Indian tax segregation: STCG vs LTCG (equity >12 months, crypto >12 months)
  - Realized vs Unrealized P&L
  - Fee/commission tracking for net P&L
  - Exportable reports for CA/tax filing

Usage::

    engine = PnLSegregationEngine()

    # Record a completed trade
    engine.record_trade(CompletedTrade(
        symbol="BTCUSDT", exchange="binance", strategy="sma_cross",
        asset_class=AssetClass.CRYPTO_SPOT, side="BUY",
        entry_price=62000, exit_price=64000, quantity=0.1,
        entry_time=..., exit_time=...,
        entry_fee=6.2, exit_fee=6.4,
    ))

    # Get segregated P&L
    report = engine.get_report(period="monthly", group_by="exchange")
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)

TRADE_LOG_DIR = os.environ.get("ALCHEMY_TRADE_LOG_DIR", "data/trades")


class AssetClass(str, Enum):
    CRYPTO_SPOT    = "crypto_spot"
    CRYPTO_FUTURES = "crypto_futures"
    CRYPTO_OPTIONS = "crypto_options"
    EQUITY         = "equity"
    EQUITY_FUTURES = "equity_futures"
    EQUITY_OPTIONS = "equity_options"
    COMMODITY      = "commodity"
    FOREX          = "forex"


class TaxCategory(str, Enum):
    STCG = "short_term_capital_gain"   # <12 months for equity, <12 months crypto
    LTCG = "long_term_capital_gain"    # >12 months
    SPECULATIVE = "speculative"        # Intraday equity
    BUSINESS    = "business_income"    # Frequent F&O trading
    NA          = "not_applicable"


# Indian tax rates (FY 2025-26)
INDIA_TAX_RATES = {
    TaxCategory.STCG: {
        AssetClass.EQUITY: 0.20,           # 20% STCG on listed equity
        AssetClass.CRYPTO_SPOT: 0.30,      # 30% flat on crypto
        AssetClass.CRYPTO_FUTURES: 0.30,
        AssetClass.EQUITY_FUTURES: 0.30,   # Business income / speculative
        AssetClass.EQUITY_OPTIONS: 0.30,
    },
    TaxCategory.LTCG: {
        AssetClass.EQUITY: 0.125,          # 12.5% LTCG on listed equity (>1.25L exempt)
        AssetClass.CRYPTO_SPOT: 0.30,      # 30% flat regardless of holding period
        AssetClass.CRYPTO_FUTURES: 0.30,
    },
}

LTCG_THRESHOLD_DAYS = {
    AssetClass.EQUITY: 365,
    AssetClass.CRYPTO_SPOT: 365,
    AssetClass.CRYPTO_FUTURES: 365,
    AssetClass.EQUITY_FUTURES: 365,
    AssetClass.EQUITY_OPTIONS: 365,
    AssetClass.COMMODITY: 365,
}


@dataclass
class CompletedTrade:
    """A single completed (closed) trade."""
    id: str = ""
    symbol: str = ""
    exchange: str = ""
    strategy: str = "manual"
    asset_class: AssetClass = AssetClass.CRYPTO_SPOT
    side: str = "BUY"            # Entry side
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    slippage: float = 0.0
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def gross_pnl(self) -> float:
        """Gross P&L before fees."""
        if self.side.upper() == "BUY":
            return (self.exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - self.exit_price) * self.quantity

    @property
    def total_fees(self) -> float:
        return self.entry_fee + self.exit_fee + self.slippage

    @property
    def net_pnl(self) -> float:
        """Net P&L after fees and slippage."""
        return self.gross_pnl - self.total_fees

    @property
    def return_pct(self) -> float:
        """Return as percentage of entry capital."""
        capital = self.entry_price * self.quantity
        if capital == 0:
            return 0.0
        return (self.net_pnl / capital) * 100

    @property
    def holding_days(self) -> int:
        """Days between entry and exit."""
        if self.entry_time and self.exit_time:
            return (self.exit_time - self.entry_time).days
        return 0

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0

    @property
    def tax_category(self) -> TaxCategory:
        """Determine Indian tax category based on asset class and holding period."""
        # Intraday equity = speculative
        if self.asset_class == AssetClass.EQUITY and self.holding_days == 0:
            return TaxCategory.SPECULATIVE
        # F&O always business income
        if self.asset_class in (AssetClass.EQUITY_FUTURES, AssetClass.EQUITY_OPTIONS):
            return TaxCategory.BUSINESS
        # LTCG vs STCG based on holding period
        threshold = LTCG_THRESHOLD_DAYS.get(self.asset_class, 365)
        if self.holding_days > threshold:
            return TaxCategory.LTCG
        return TaxCategory.STCG

    @property
    def estimated_tax(self) -> float:
        """Estimated Indian tax on this trade's profit (0 if loss)."""
        if self.net_pnl <= 0:
            return 0.0
        cat = self.tax_category
        rates = INDIA_TAX_RATES.get(cat, {})
        rate = rates.get(self.asset_class, 0.30)  # Default 30%
        return self.net_pnl * rate

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gross_pnl"] = round(self.gross_pnl, 2)
        d["net_pnl"] = round(self.net_pnl, 2)
        d["total_fees"] = round(self.total_fees, 2)
        d["return_pct"] = round(self.return_pct, 4)
        d["holding_days"] = self.holding_days
        d["is_winner"] = self.is_winner
        d["tax_category"] = self.tax_category.value
        d["estimated_tax"] = round(self.estimated_tax, 2)
        if self.entry_time:
            d["entry_time"] = self.entry_time.isoformat()
        if self.exit_time:
            d["exit_time"] = self.exit_time.isoformat()
        return d


@dataclass
class OpenPosition:
    """A currently open (unrealized) position."""
    symbol: str = ""
    exchange: str = ""
    strategy: str = "manual"
    asset_class: AssetClass = AssetClass.CRYPTO_SPOT
    side: str = "BUY"
    entry_price: float = 0.0
    quantity: float = 0.0
    current_price: float = 0.0
    entry_time: Optional[datetime] = None
    entry_fee: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        if self.side.upper() == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pct(self) -> float:
        capital = self.entry_price * self.quantity
        if capital == 0:
            return 0.0
        return (self.unrealized_pnl / capital) * 100


@dataclass
class PnLBucket:
    """Aggregated P&L for a single group (exchange, strategy, etc.)."""
    key: str = ""
    label: str = ""
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    total_volume: float = 0.0
    estimated_tax: float = 0.0
    avg_holding_days: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return (self.winning_trades / self.trade_count) * 100

    @property
    def avg_pnl_per_trade(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.net_pnl / self.trade_count

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss. >1 = profitable."""
        if self.max_loss == 0:
            return float("inf") if self.gross_pnl > 0 else 0.0
        gross_profit = sum(1 for _ in range(self.winning_trades))  # Placeholder
        # We track max_win/loss but not totals; use net approximation
        if self.net_pnl <= 0:
            return 0.0
        return abs(self.net_pnl / max(abs(self.max_loss), 0.01))

    @property
    def net_after_tax(self) -> float:
        return self.net_pnl - self.estimated_tax

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "gross_pnl": round(self.gross_pnl, 2),
            "total_fees": round(self.total_fees, 2),
            "net_pnl": round(self.net_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "max_win": round(self.max_win, 2),
            "max_loss": round(self.max_loss, 2),
            "avg_pnl_per_trade": round(self.avg_pnl_per_trade, 2),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "total_volume": round(self.total_volume, 2),
            "estimated_tax": round(self.estimated_tax, 2),
            "net_after_tax": round(self.net_after_tax, 2),
        }


class PnLSegregationEngine:
    """
    Central P&L tracking and segregation engine.

    Records completed trades and open positions, then provides
    segregated reports across any dimension.
    """

    def __init__(self, trade_log_dir: str = TRADE_LOG_DIR) -> None:
        self._trades: list[CompletedTrade] = []
        self._open_positions: list[OpenPosition] = []
        self._lock = threading.Lock()
        self._log_dir = Path(trade_log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._trade_file = self._log_dir / "completed_trades.jsonl"

        # Load existing trades from file
        self._load_from_file()

        log.info("pnl_engine.initialized", trades=len(self._trades))

    # ── Record Trades ─────────────────────────────────────────────────────────

    def record_trade(self, trade: CompletedTrade) -> None:
        """Record a completed trade."""
        if not trade.id:
            import uuid
            trade.id = str(uuid.uuid4())[:12]

        with self._lock:
            self._trades.append(trade)
            # Persist to file
            try:
                with open(self._trade_file, "a") as f:
                    f.write(json.dumps(trade.to_dict(), default=str) + "\n")
            except Exception as e:
                log.error("pnl_engine.write_error", error=str(e))

        log.info("pnl_engine.trade_recorded",
                 symbol=trade.symbol, net_pnl=round(trade.net_pnl, 2))

    def update_open_position(self, position: OpenPosition) -> None:
        """Update or add an open position."""
        with self._lock:
            # Replace if same symbol+exchange+strategy
            self._open_positions = [
                p for p in self._open_positions
                if not (p.symbol == position.symbol
                        and p.exchange == position.exchange
                        and p.strategy == position.strategy)
            ]
            if position.quantity != 0:
                self._open_positions.append(position)

    def close_position(self, symbol: str, exchange: str, exit_price: float,
                       exit_fee: float = 0.0) -> Optional[CompletedTrade]:
        """Close an open position and record as completed trade."""
        with self._lock:
            pos = None
            for p in self._open_positions:
                if p.symbol == symbol and p.exchange == exchange:
                    pos = p
                    break
            if not pos:
                return None

            trade = CompletedTrade(
                symbol=pos.symbol,
                exchange=pos.exchange,
                strategy=pos.strategy,
                asset_class=pos.asset_class,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                entry_time=pos.entry_time,
                exit_time=datetime.now(timezone.utc),
                entry_fee=pos.entry_fee,
                exit_fee=exit_fee,
            )
            self._open_positions.remove(pos)

        self.record_trade(trade)
        return trade

    # ── Reports ───────────────────────────────────────────────────────────────

    def get_report(
        self,
        group_by: str = "exchange",
        period: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exchange: Optional[str] = None,
        strategy: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> dict:
        """
        Get segregated P&L report.

        Args:
            group_by: "exchange", "strategy", "asset_class", "symbol",
                      "tax_category", "month", "week", "side"
            period: "today", "week", "month", "quarter", "year", "all"
            start_date/end_date: Custom date range
            exchange/strategy/asset_class: Filters
        """
        trades = self._filter_trades(
            period=period,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
            strategy=strategy,
            asset_class=asset_class,
        )

        buckets = self._aggregate(trades, group_by)

        # Add unrealized P&L
        for pos in self._open_positions:
            key = self._get_group_key(pos, group_by)
            if key in buckets:
                buckets[key].unrealized_pnl += pos.unrealized_pnl

        # Summary
        total = PnLBucket(key="total", label="Total")
        for b in buckets.values():
            total.trade_count += b.trade_count
            total.winning_trades += b.winning_trades
            total.losing_trades += b.losing_trades
            total.gross_pnl += b.gross_pnl
            total.total_fees += b.total_fees
            total.net_pnl += b.net_pnl
            total.unrealized_pnl += b.unrealized_pnl
            total.estimated_tax += b.estimated_tax
            total.total_volume += b.total_volume

        return {
            "group_by": group_by,
            "period": period or "all",
            "trade_count": total.trade_count,
            "summary": total.to_dict(),
            "breakdown": [b.to_dict() for b in sorted(
                buckets.values(), key=lambda x: x.net_pnl, reverse=True
            )],
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "strategy": p.strategy,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "quantity": p.quantity,
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                    "unrealized_pct": round(p.unrealized_pct, 2),
                }
                for p in self._open_positions
            ],
        }

    def get_tax_report(
        self,
        financial_year: Optional[str] = None,
    ) -> dict:
        """
        Generate Indian tax-ready P&L report for a financial year.

        Default: current FY (April to March).
        """
        now = datetime.now()
        if financial_year:
            # Parse "2025-26" or "2025"
            fy_start_year = int(financial_year.split("-")[0])
        else:
            fy_start_year = now.year if now.month >= 4 else now.year - 1

        fy_start = date(fy_start_year, 4, 1)
        fy_end = date(fy_start_year + 1, 3, 31)

        trades = self._filter_trades(start_date=fy_start, end_date=fy_end)

        # Group by tax category
        tax_buckets: dict[str, dict] = {}
        for cat in TaxCategory:
            cat_trades = [t for t in trades if t.tax_category == cat]
            if not cat_trades:
                continue

            profit = sum(t.net_pnl for t in cat_trades if t.net_pnl > 0)
            loss = sum(t.net_pnl for t in cat_trades if t.net_pnl < 0)
            net = profit + loss
            tax = sum(t.estimated_tax for t in cat_trades)

            tax_buckets[cat.value] = {
                "category": cat.value,
                "trade_count": len(cat_trades),
                "gross_profit": round(profit, 2),
                "gross_loss": round(loss, 2),
                "net_pnl": round(net, 2),
                "estimated_tax": round(tax, 2),
                "tax_rate": INDIA_TAX_RATES.get(cat, {}).get(
                    AssetClass.EQUITY, 0.30) * 100,
                "trades": [t.to_dict() for t in cat_trades],
            }

        total_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
        total_loss = sum(t.net_pnl for t in trades if t.net_pnl < 0)
        total_tax = sum(t.estimated_tax for t in trades)
        total_fees = sum(t.total_fees for t in trades)

        return {
            "financial_year": f"{fy_start_year}-{str(fy_start_year + 1)[-2:]}",
            "period": {"start": fy_start.isoformat(), "end": fy_end.isoformat()},
            "total_trades": len(trades),
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "net_pnl": round(total_profit + total_loss, 2),
            "total_fees_paid": round(total_fees, 2),
            "estimated_total_tax": round(total_tax, 2),
            "net_after_tax": round(total_profit + total_loss - total_tax, 2),
            "tax_breakdown": tax_buckets,
            "notes": [
                "STCG on equity: 20% (listed shares held <12 months)",
                "LTCG on equity: 12.5% (above Rs 1.25 lakh exemption)",
                "Crypto: 30% flat tax, no loss set-off, 1% TDS on transfers",
                "F&O: treated as business income, taxed at slab rate",
                "Consult a CA for accurate filing — these are estimates only",
            ],
        }

    def get_daily_pnl_series(
        self,
        days: int = 30,
        exchange: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> list[dict]:
        """Get daily P&L time series for charting."""
        end = date.today()
        start = end - timedelta(days=days)
        trades = self._filter_trades(
            start_date=start, end_date=end,
            exchange=exchange, strategy=strategy,
        )

        daily: dict[str, float] = defaultdict(float)
        for t in trades:
            if t.exit_time:
                day_key = t.exit_time.strftime("%Y-%m-%d")
                daily[day_key] += t.net_pnl

        series = []
        cumulative = 0.0
        current = start
        while current <= end:
            key = current.isoformat()
            day_pnl = daily.get(key, 0.0)
            cumulative += day_pnl
            series.append({
                "date": key,
                "pnl": round(day_pnl, 2),
                "cumulative_pnl": round(cumulative, 2),
            })
            current += timedelta(days=1)

        return series

    # ── Internals ─────────────────────────────────────────────────────────────

    def _filter_trades(
        self,
        period: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exchange: Optional[str] = None,
        strategy: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> list[CompletedTrade]:
        """Filter trades by various criteria."""
        trades = list(self._trades)

        # Period filter
        if period and not start_date:
            today = date.today()
            if period == "today":
                start_date = today
            elif period == "week":
                start_date = today - timedelta(days=today.weekday())
            elif period == "month":
                start_date = today.replace(day=1)
            elif period == "quarter":
                q_month = ((today.month - 1) // 3) * 3 + 1
                start_date = today.replace(month=q_month, day=1)
            elif period == "year":
                start_date = today.replace(month=1, day=1)

        if start_date:
            trades = [
                t for t in trades
                if t.exit_time and t.exit_time.date() >= start_date
            ]
        if end_date:
            trades = [
                t for t in trades
                if t.exit_time and t.exit_time.date() <= end_date
            ]
        if exchange:
            trades = [t for t in trades if t.exchange.lower() == exchange.lower()]
        if strategy:
            trades = [t for t in trades if t.strategy.lower() == strategy.lower()]
        if asset_class:
            trades = [t for t in trades if t.asset_class.value == asset_class]

        return trades

    def _aggregate(
        self, trades: list[CompletedTrade], group_by: str,
    ) -> dict[str, PnLBucket]:
        """Aggregate trades into buckets by group_by dimension."""
        buckets: dict[str, PnLBucket] = {}

        for trade in trades:
            key = self._get_group_key(trade, group_by)
            if key not in buckets:
                buckets[key] = PnLBucket(key=key, label=key)

            b = buckets[key]
            b.trade_count += 1
            b.gross_pnl += trade.gross_pnl
            b.total_fees += trade.total_fees
            b.net_pnl += trade.net_pnl
            b.estimated_tax += trade.estimated_tax
            b.total_volume += trade.entry_price * trade.quantity

            if trade.is_winner:
                b.winning_trades += 1
                b.max_win = max(b.max_win, trade.net_pnl)
            else:
                b.losing_trades += 1
                b.max_loss = min(b.max_loss, trade.net_pnl)

            b.avg_holding_days = (
                (b.avg_holding_days * (b.trade_count - 1) + trade.holding_days)
                / b.trade_count
            )

        return buckets

    def _get_group_key(self, item, group_by: str) -> str:
        """Extract group key from a trade or position."""
        if group_by == "exchange":
            return getattr(item, "exchange", "unknown")
        elif group_by == "strategy":
            return getattr(item, "strategy", "unknown")
        elif group_by == "asset_class":
            ac = getattr(item, "asset_class", AssetClass.CRYPTO_SPOT)
            return ac.value if isinstance(ac, AssetClass) else str(ac)
        elif group_by == "symbol":
            return getattr(item, "symbol", "unknown")
        elif group_by == "side":
            return getattr(item, "side", "unknown").upper()
        elif group_by == "tax_category":
            if isinstance(item, CompletedTrade):
                return item.tax_category.value
            return "unknown"
        elif group_by == "month":
            t = getattr(item, "exit_time", None) or getattr(item, "entry_time", None)
            if t:
                return t.strftime("%Y-%m")
            return "unknown"
        elif group_by == "week":
            t = getattr(item, "exit_time", None) or getattr(item, "entry_time", None)
            if t:
                return t.strftime("%Y-W%W")
            return "unknown"
        return "unknown"

    def _load_from_file(self) -> None:
        """Load existing trades from JSONL file."""
        if not self._trade_file.exists():
            return
        try:
            with open(self._trade_file) as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        trade = CompletedTrade(
                            id=data.get("id", ""),
                            symbol=data.get("symbol", ""),
                            exchange=data.get("exchange", ""),
                            strategy=data.get("strategy", "manual"),
                            asset_class=AssetClass(data.get("asset_class", "crypto_spot")),
                            side=data.get("side", "BUY"),
                            entry_price=float(data.get("entry_price", 0)),
                            exit_price=float(data.get("exit_price", 0)),
                            quantity=float(data.get("quantity", 0)),
                            entry_fee=float(data.get("entry_fee", 0)),
                            exit_fee=float(data.get("exit_fee", 0)),
                            slippage=float(data.get("slippage", 0)),
                            notes=data.get("notes", ""),
                            tags=data.get("tags", []),
                        )
                        if data.get("entry_time"):
                            trade.entry_time = datetime.fromisoformat(data["entry_time"])
                        if data.get("exit_time"):
                            trade.exit_time = datetime.fromisoformat(data["exit_time"])
                        self._trades.append(trade)
                    except (json.JSONDecodeError, ValueError):
                        continue
            log.info("pnl_engine.loaded_trades", count=len(self._trades))
        except Exception as e:
            log.error("pnl_engine.load_error", error=str(e))

    def stats(self) -> dict:
        """Quick stats summary."""
        with self._lock:
            return {
                "total_completed_trades": len(self._trades),
                "open_positions": len(self._open_positions),
                "exchanges": list(set(t.exchange for t in self._trades)),
                "strategies": list(set(t.strategy for t in self._trades)),
                "asset_classes": list(set(t.asset_class.value for t in self._trades)),
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[PnLSegregationEngine] = None


def get_pnl_engine() -> PnLSegregationEngine:
    global _instance
    if _instance is None:
        _instance = PnLSegregationEngine()
    return _instance
