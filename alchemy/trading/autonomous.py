"""
alchemy.trading.autonomous
============================
Autonomous trading engine — runs strategy evaluation on real-time market data
and optionally auto-executes trades via connected exchange gateways.

Features:
  - Configurable evaluation interval (default 60s)
  - Multi-symbol, multi-strategy scanning
  - Real-time OHLCV data from Binance
  - WebSocket broadcast of signals and executions
  - Notification dispatch (Telegram, Gmail) for every event
  - Paper mode safety (no real orders unless explicitly enabled)
  - Trade history with P&L tracking
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class AutoTradeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class TradeRecord:
    """Record of an autonomous trade signal + execution."""
    id: str = ""
    symbol: str = ""
    strategy: str = ""
    direction: str = ""       # long | short
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""
    executed: bool = False
    execution_price: float = 0.0
    execution_error: str = ""
    pnl: float = 0.0
    status: str = "signal"    # signal | executed | closed | cancelled
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "executed": self.executed,
            "execution_price": self.execution_price,
            "execution_error": self.execution_error,
            "pnl": self.pnl,
            "status": self.status,
            "created_at": self.created_at,
        }


async def _fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 100) -> dict:
    """Fetch OHLCV data from Binance public API."""
    import httpx
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()
        if not isinstance(data, list) or not data:
            return {}
        closes = [float(k[4]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        opens = [float(k[1]) for k in data]
        volumes = [float(k[5]) for k in data]
        return {
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "opens": opens,
            "volumes": volumes,
            "raw": data,
        }
    except Exception as e:
        log.error("autonomous.fetch_klines_error", symbol=symbol, error=str(e))
        return {}


class AutonomousTradingEngine:
    """
    Core autonomous trading engine.

    Runs a loop that:
      1. Fetches real-time OHLCV for configured symbols
      2. Runs all enabled strategies
      3. Broadcasts signals via WebSocket
      4. Dispatches notifications (Telegram, Gmail)
      5. Optionally executes trades via exchange gateways
    """

    def __init__(self) -> None:
        self.status: AutoTradeStatus = AutoTradeStatus.IDLE
        self.symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.strategies: list[str] = ["scalping", "momentum", "breakout"]
        self.interval_seconds: int = 60
        self.auto_execute: bool = False  # Safety: paper-only by default
        self.exchange: str = "binance"
        self.timeframe: str = "15m"

        self._task: Optional[asyncio.Task] = None
        self._trade_history: list[TradeRecord] = []
        self._active_signals: list[TradeRecord] = []
        self._total_signals: int = 0
        self._total_executed: int = 0
        self._started_at: Optional[str] = None
        self._last_scan_at: Optional[str] = None
        self._scan_count: int = 0
        self._ws_broadcast = None  # Set by the API layer
        self._user_id: str = ""   # Set when started via API

    def configure(
        self,
        symbols: Optional[list[str]] = None,
        strategies: Optional[list[str]] = None,
        interval_seconds: Optional[int] = None,
        auto_execute: Optional[bool] = None,
        exchange: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> None:
        if symbols is not None:
            self.symbols = symbols
        if strategies is not None:
            self.strategies = strategies
        if interval_seconds is not None:
            self.interval_seconds = max(10, interval_seconds)
        if auto_execute is not None:
            self.auto_execute = auto_execute
        if exchange is not None:
            self.exchange = exchange
        if timeframe is not None:
            self.timeframe = timeframe

    async def start(self, ws_broadcast=None) -> dict:
        """Start the autonomous trading loop."""
        if self.status == AutoTradeStatus.RUNNING:
            return {"ok": False, "error": "Already running"}

        self._ws_broadcast = ws_broadcast
        self.status = AutoTradeStatus.RUNNING
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._scan_count = 0

        self._task = asyncio.create_task(self._run_loop())
        log.info("autonomous.started",
                 symbols=self.symbols,
                 strategies=self.strategies,
                 interval=self.interval_seconds,
                 auto_execute=self.auto_execute)

        return {"ok": True, "status": "running", "symbols": self.symbols}

    async def stop(self) -> dict:
        """Stop the autonomous trading loop."""
        if self.status != AutoTradeStatus.RUNNING:
            return {"ok": False, "error": "Not running"}

        self.status = AutoTradeStatus.STOPPING
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.status = AutoTradeStatus.IDLE
        log.info("autonomous.stopped", scans=self._scan_count, signals=self._total_signals)
        return {"ok": True, "status": "idle", "total_scans": self._scan_count}

    def get_status(self) -> dict:
        return {
            "status": self.status.value,
            "symbols": self.symbols,
            "strategies": self.strategies,
            "interval_seconds": self.interval_seconds,
            "auto_execute": self.auto_execute,
            "exchange": self.exchange,
            "timeframe": self.timeframe,
            "started_at": self._started_at,
            "last_scan_at": self._last_scan_at,
            "scan_count": self._scan_count,
            "total_signals": self._total_signals,
            "total_executed": self._total_executed,
            "active_signals": [s.to_dict() for s in self._active_signals[-10:]],
        }

    def get_history(self, limit: int = 50) -> list[dict]:
        return [t.to_dict() for t in self._trade_history[-limit:]]

    async def _run_loop(self) -> None:
        """Main trading loop."""
        try:
            while self.status == AutoTradeStatus.RUNNING:
                try:
                    await self._scan_markets()
                except Exception as e:
                    log.error("autonomous.scan_error", error=str(e))
                    await self._broadcast_event("autonomous_error", {"error": str(e)})

                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            log.info("autonomous.loop_cancelled")
        except Exception as e:
            log.error("autonomous.loop_fatal", error=str(e))
            self.status = AutoTradeStatus.ERROR

    async def _scan_markets(self) -> None:
        """Run one scan cycle across all symbols and strategies."""
        self._scan_count += 1
        self._last_scan_at = datetime.now(timezone.utc).isoformat()

        log.info("autonomous.scan_start",
                 scan=self._scan_count,
                 symbols=len(self.symbols))

        await self._broadcast_event("autonomous_scan", {
            "scan": self._scan_count,
            "symbols": self.symbols,
            "timestamp": self._last_scan_at,
        })

        from alchemy.trading.strategies.engine import (
            ScalpingStrategy, MomentumStrategy, BreakoutStrategy,
            StrategyType,
        )

        strategy_map = {
            "scalping": ScalpingStrategy(),
            "momentum": MomentumStrategy(),
            "breakout": BreakoutStrategy(),
        }

        for symbol in self.symbols:
            ohlcv = await _fetch_binance_klines(symbol, self.timeframe, 100)
            if not ohlcv:
                log.warning("autonomous.no_data", symbol=symbol)
                continue

            for strategy_name in self.strategies:
                strategy = strategy_map.get(strategy_name)
                if not strategy:
                    continue

                try:
                    idea = strategy.generate(
                        symbol=symbol,
                        ohlcv=ohlcv,
                        market_bias="neutral",
                        emotional_score=0.5,
                    )
                except Exception as e:
                    log.error("autonomous.strategy_error",
                              strategy=strategy_name, symbol=symbol, error=str(e))
                    continue

                if idea:
                    record = TradeRecord(
                        id=str(uuid4())[:8],
                        symbol=symbol,
                        strategy=idea.strategy.value,
                        direction=idea.direction.value,
                        entry_price=idea.entry_price,
                        stop_loss=idea.stop_loss,
                        take_profit=idea.take_profit_2,
                        confidence=idea.confidence,
                        reasoning=idea.reasoning,
                        status="signal",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )

                    self._total_signals += 1
                    self._active_signals.append(record)
                    if len(self._active_signals) > 100:
                        self._active_signals = self._active_signals[-50:]

                    self._trade_history.append(record)
                    if len(self._trade_history) > 500:
                        self._trade_history = self._trade_history[-250:]

                    log.info("autonomous.signal",
                             symbol=symbol,
                             strategy=idea.strategy.value,
                             direction=idea.direction.value,
                             price=idea.entry_price,
                             confidence=idea.confidence)

                    # Broadcast via WebSocket
                    await self._broadcast_event("autonomous_signal", record.to_dict())

                    # Dispatch notification
                    await self._notify_signal(record)

                    # Auto-execute if enabled
                    if self.auto_execute:
                        # Skip if already have an open position for this symbol
                        has_position = False
                        try:
                            from alchemy.paper_trading.engine import get_paper_engine
                            portfolio = get_paper_engine().get_portfolio(self._user_id or "autonomous")
                            pos = portfolio.positions.get(symbol)
                            if pos and pos.side.value != "flat" and pos.quantity > 0:
                                has_position = True
                                log.info("autonomous.skip_existing_position",
                                         symbol=symbol, side=pos.side.value,
                                         qty=pos.quantity, entry=pos.avg_entry_price)
                        except Exception:
                            pass

                        if not has_position:
                            await self._execute_trade(record)
                        else:
                            record.status = "skipped"
                            record.reasoning += " | Skipped: existing position open"

        log.info("autonomous.scan_complete", scan=self._scan_count)
        await self._broadcast_event("autonomous_scan_complete", {
            "scan": self._scan_count,
            "total_signals": self._total_signals,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _execute_trade(self, record: TradeRecord) -> None:
        """Execute a trade via the paper trading engine + exchange gateway."""
        try:
            # ── Record in paper trading engine for dashboard visibility ──
            user_id = self._user_id
            if not user_id:
                # Fallback: look up first admin user from DB
                try:
                    import sqlite3, os, re as _re
                    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
                    db_path = _re.sub(r"^sqlite(\+aiosqlite)?:///", "", url)
                    conn = sqlite3.connect(db_path)
                    row = conn.execute("SELECT id FROM users ORDER BY created_at LIMIT 1").fetchone()
                    conn.close()
                    if row:
                        user_id = str(row[0])
                        self._user_id = user_id
                        log.info("autonomous.user_resolved_from_db", user_id=user_id)
                except Exception as dbe:
                    log.error("autonomous.db_user_lookup_failed", error=str(dbe))

            if not user_id:
                log.error("autonomous.NO_USER_ID — trades will NOT appear in dashboard")
                user_id = "autonomous"

            side = "buy" if record.direction == "long" else "sell"
            price = record.entry_price

            # Calculate meaningful quantity based on portfolio
            quantity = 0.0
            try:
                from alchemy.paper_trading.engine import get_paper_engine
                paper = get_paper_engine()
                portfolio = paper.get_portfolio(user_id)
                # Use 5% of available cash per trade
                trade_budget = portfolio.cash_balance * 0.05
                if price > 0:
                    quantity = round(trade_budget / price, 6)
                else:
                    quantity = 0.001
            except Exception:
                quantity = 0.001

            log.info("autonomous.recording_paper_trade",
                     user_id=user_id[:12], symbol=record.symbol,
                     side=side, quantity=quantity, price=price)

            try:
                from alchemy.paper_trading.engine import get_paper_engine
                paper = get_paper_engine()

                if side == "buy":
                    order = paper.place_order(
                        user_id=user_id,
                        symbol=record.symbol,
                        side="buy",
                        quantity=quantity,
                        current_price=price,
                        order_type="market",
                        strategy=f"auto_{record.strategy}",
                        notes=f"Autonomous LONG: {record.confidence:.0%} confidence | {record.reasoning[:60]}",
                    )
                    log.info("autonomous.paper_order_placed",
                             order_id=order.id, status=order.status.value,
                             symbol=record.symbol, side="buy", qty=quantity, price=price)
                else:
                    # SHORT signal → open short position via place_order(side=sell)
                    order = paper.place_order(
                        user_id=user_id,
                        symbol=record.symbol,
                        side="sell",
                        quantity=quantity,
                        current_price=price,
                        order_type="market",
                        strategy=f"auto_{record.strategy}",
                        notes=f"Autonomous SHORT: {record.confidence:.0%} confidence | {record.reasoning[:60]}",
                    )
                    log.info("autonomous.paper_order_placed",
                             order_id=order.id, status=order.status.value,
                             symbol=record.symbol, side="sell/short", qty=quantity, price=price)

                # Verify it was recorded
                portfolio_after = paper.get_portfolio(user_id)
                log.info("autonomous.paper_portfolio_after",
                         cash=round(portfolio_after.cash_balance, 2),
                         positions=len(portfolio_after.positions),
                         trades=len(portfolio_after.trade_log))

            except Exception as pe:
                log.error("autonomous.PAPER_RECORD_FAILED", error=str(pe),
                          user_id=user_id[:12], symbol=record.symbol)
                import traceback
                traceback.print_exc()

            # ── Execute on exchange if auto_execute is enabled ──
            if self.auto_execute:
                if self.exchange == "binance":
                    from alchemy.execution.crypto.binance_gateway import BinanceGateway
                    gw = BinanceGateway(market="futures_usdm", paper_trading=True, testnet=False)
                elif self.exchange == "delta":
                    from alchemy.execution.crypto.delta_gateway import DeltaGateway
                    gw = DeltaGateway(paper_trading=True, testnet_mode=True)
                else:
                    record.execution_error = f"Unsupported exchange: {self.exchange}"
                    return

                loop = asyncio.get_running_loop()
                if self.exchange == "binance":
                    ex_side = "BUY" if record.direction == "long" else "SELL"
                    result = await loop.run_in_executor(None, lambda: gw.place_order(
                        symbol=record.symbol,
                        side=ex_side,
                        quantity=0.001,
                        order_type="MARKET",
                    ))
                else:
                    ex_side = "buy" if record.direction == "long" else "sell"
                    result = await loop.run_in_executor(None, lambda: gw.place_order(
                        symbol=record.symbol,
                        side=ex_side,
                        size=1,
                        order_type="market_order",
                    ))
                fill = (result.get("avgPrice")
                        or result.get("avg_fill_price")
                        or result.get("price")
                        or record.entry_price)
                record.execution_price = float(fill)

            record.executed = True
            record.status = "executed"
            self._total_executed += 1

            await self._broadcast_event("autonomous_execution", record.to_dict())
            await self._notify_execution(record)

            log.info("autonomous.executed",
                     symbol=record.symbol, direction=record.direction,
                     price=record.execution_price or record.entry_price)

        except Exception as e:
            record.execution_error = str(e)
            record.status = "error"
            log.error("autonomous.execution_error", symbol=record.symbol, error=str(e))
            import traceback
            traceback.print_exc()

    async def _notify_signal(self, record: TradeRecord) -> None:
        """Dispatch notification for a new trade signal."""
        try:
            from alchemy.notifications.dispatcher import get_dispatcher
            from alchemy.notifications.models import (
                NotificationEvent, EventType, EventSeverity,
            )

            direction_emoji = "🟢" if record.direction == "long" else "🔴"
            event = NotificationEvent(
                event_type=EventType.SIGNAL_BUY if record.direction == "long" else EventType.SIGNAL_SELL,
                severity=EventSeverity.INFO,
                title=f"{direction_emoji} {record.direction.upper()} Signal — {record.symbol}",
                message=(
                    f"**{record.symbol}** {record.direction.upper()} ({record.strategy})\n"
                    f"Entry: ${record.entry_price:,.2f}  |  "
                    f"Stop: ${record.stop_loss:,.2f}  |  "
                    f"TP: ${record.take_profit:,.2f}\n"
                    f"Confidence: {record.confidence:.0%}  |  "
                    f"{record.reasoning}"
                ),
                data={
                    "symbol": record.symbol,
                    "strategy": record.strategy,
                    "direction": record.direction,
                    "entry_price": record.entry_price,
                    "stop_loss": record.stop_loss,
                    "take_profit": record.take_profit,
                },
                source="autonomous_engine",
            )
            await get_dispatcher().notify(event)
        except Exception as e:
            log.error("autonomous.notify_error", error=str(e))

    async def _notify_execution(self, record: TradeRecord) -> None:
        """Dispatch notification for a trade execution."""
        try:
            from alchemy.notifications.dispatcher import get_dispatcher
            from alchemy.notifications.models import (
                NotificationEvent, EventType, EventSeverity,
            )

            event = NotificationEvent(
                event_type=EventType.ORDER_FILLED,
                severity=EventSeverity.SUCCESS,
                title=f"✅ Order Executed — {record.symbol}",
                message=(
                    f"**{record.symbol}** {record.direction.upper()} executed\n"
                    f"Price: ${record.execution_price:,.2f}  |  "
                    f"Strategy: {record.strategy}\n"
                    f"Stop: ${record.stop_loss:,.2f}  |  TP: ${record.take_profit:,.2f}"
                ),
                data={
                    "symbol": record.symbol,
                    "fill_price": record.execution_price,
                    "strategy": record.strategy,
                },
                source="autonomous_engine",
            )
            await get_dispatcher().notify(event)
        except Exception as e:
            log.error("autonomous.notify_execution_error", error=str(e))

    async def _broadcast_event(self, event_type: str, data: dict) -> None:
        """Broadcast event via WebSocket."""
        if self._ws_broadcast:
            try:
                await self._ws_broadcast(event_type, data)
            except Exception as e:
                log.error("autonomous.broadcast_error", error=str(e))


# ── Singleton ──────────────────────────────────────────────────────────────────
_engine: Optional[AutonomousTradingEngine] = None


def get_autonomous_engine() -> AutonomousTradingEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousTradingEngine()
    return _engine
