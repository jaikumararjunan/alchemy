"""
alchemy.paper_trading.engine
===============================
Paper Trading Engine — virtual portfolio with simulated order execution.

Each user gets their own isolated portfolio with:
  - Virtual cash balance (default $100,000)
  - Simulated order execution with realistic slippage
  - Position tracking with stop-loss and take-profit
  - Complete trade history and P&L tracking
  - Real-time price updates via exchange feeds

Usage::

    engine = get_paper_engine()

    # Place a paper trade
    order = engine.place_order(
        user_id="user123",
        symbol="BTCUSDT",
        side="buy",
        quantity=0.1,
        order_type="market",
        current_price=62500,
    )

    # Get portfolio
    portfolio = engine.get_portfolio("user123")
"""
from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from alchemy.paper_trading import (
    BacktestConfig, BacktestResult,
    OrderSide, OrderStatus, OrderType,
    PaperOrder, PaperPortfolio, PaperPosition, PositionSide,
)

log = structlog.get_logger(__name__)

DATA_DIR = os.environ.get("ALCHEMY_PAPER_DIR", "/data/paper_trading")
DEFAULT_BALANCE = float(os.environ.get("PAPER_TRADING_BALANCE", "100000"))


class PaperTradingEngine:
    """
    Virtual trading engine with per-user portfolio isolation.
    Thread-safe, file-persisted.
    """

    def __init__(self, data_dir: str = DATA_DIR) -> None:
        self._portfolios: dict[str, PaperPortfolio] = {}
        self._lock = threading.Lock()
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._load_all()
        log.info("paper_engine.initialized", users=len(self._portfolios))

    # ── Portfolio Management ──────────────────────────────────────────────────

    def get_portfolio(self, user_id: str) -> PaperPortfolio:
        """Get or create a user's paper portfolio."""
        with self._lock:
            if user_id not in self._portfolios:
                self._portfolios[user_id] = PaperPortfolio(
                    user_id=user_id,
                    initial_balance=DEFAULT_BALANCE,
                    cash_balance=DEFAULT_BALANCE,
                )
                self._save(user_id)
                log.info("paper.portfolio_created", user_id=user_id,
                         balance=DEFAULT_BALANCE)
            return self._portfolios[user_id]

    def reset_portfolio(self, user_id: str, initial_balance: float = 0) -> PaperPortfolio:
        """Reset a user's portfolio to starting state."""
        balance = initial_balance or DEFAULT_BALANCE
        with self._lock:
            self._portfolios[user_id] = PaperPortfolio(
                user_id=user_id,
                initial_balance=balance,
                cash_balance=balance,
            )
            self._save(user_id)
        log.info("paper.portfolio_reset", user_id=user_id, balance=balance)
        return self._portfolios[user_id]

    # ── Order Placement ───────────────────────────────────────────────────────

    def place_order(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        order_type: str = "market",
        limit_price: float = 0,
        stop_price: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
        strategy: str = "manual",
        notes: str = "",
    ) -> PaperOrder:
        """
        Place a paper trade order.

        For market orders: executes immediately at current_price ± slippage.
        For limit orders: stored as pending, filled when price reaches limit.
        """
        portfolio = self.get_portfolio(user_id)
        order_side = OrderSide(side.lower())
        o_type = OrderType(order_type.lower())

        order = PaperOrder(
            user_id=user_id,
            symbol=symbol.upper(),
            side=order_side,
            order_type=o_type,
            quantity=quantity,
            price=limit_price if o_type == OrderType.LIMIT else current_price,
            stop_price=stop_price,
            strategy=strategy,
            notes=notes,
        )

        # Validate
        rejection = self._validate_order(portfolio, order, current_price)
        if rejection:
            order.status = OrderStatus.REJECTED
            order.notes = rejection
            with self._lock:
                portfolio.order_history.append(order)
                self._save(user_id)
            log.warning("paper.order_rejected", user_id=user_id,
                        symbol=symbol, reason=rejection)
            return order

        # Execute market orders immediately
        if o_type == OrderType.MARKET:
            self._execute_order(portfolio, order, current_price,
                                stop_loss=stop_loss, take_profit=take_profit)
        else:
            order.status = OrderStatus.PENDING
            with self._lock:
                portfolio.order_history.append(order)
                self._save(user_id)

        log.info("paper.order_placed", user_id=user_id, symbol=symbol,
                 side=side, qty=quantity, status=order.status.value)

        # Dispatch copy trades to followers
        if order.status.value == "filled":
            try:
                from alchemy.api.copy_trading import execute_copy_trades
                execute_copy_trades(user_id, symbol, side, quantity, order.filled_price or current_price)
            except Exception:
                pass

        return order

    def close_position(
        self,
        user_id: str,
        symbol: str,
        current_price: float,
        quantity: float = 0,
        notes: str = "",
    ) -> Optional[PaperOrder]:
        """Close an open position (fully or partially)."""
        portfolio = self.get_portfolio(user_id)
        symbol = symbol.upper()

        with self._lock:
            pos = portfolio.positions.get(symbol)
            if not pos or pos.side == PositionSide.FLAT:
                return None

            close_qty = quantity if quantity > 0 else pos.quantity
            close_qty = min(close_qty, pos.quantity)

            # Create closing order
            close_side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
            order = PaperOrder(
                user_id=user_id,
                symbol=symbol,
                side=close_side,
                order_type=OrderType.MARKET,
                quantity=close_qty,
                price=current_price,
                strategy=pos.strategy,
                notes=notes or "Position closed",
            )

            self._execute_close(portfolio, order, pos, current_price, close_qty)
            self._save(user_id)

        return order

    # ── Price Updates (for stop-loss / take-profit) ───────────────────────────

    def update_prices(self, user_id: str, prices: dict[str, float]) -> list[str]:
        """
        Update current prices for a user's positions.
        Triggers stop-loss and take-profit if hit.
        Returns list of triggered events.
        """
        portfolio = self.get_portfolio(user_id)
        events = []

        with self._lock:
            for symbol, price in prices.items():
                symbol = symbol.upper()
                pos = portfolio.positions.get(symbol)
                if not pos or pos.side == PositionSide.FLAT:
                    continue

                pos.current_price = price

                # Check stop-loss
                if pos.stop_loss > 0:
                    if (pos.side == PositionSide.LONG and price <= pos.stop_loss) or \
                       (pos.side == PositionSide.SHORT and price >= pos.stop_loss):
                        self._execute_stop(portfolio, pos, price, "stop_loss")
                        events.append(f"STOP_LOSS: {symbol} @ {price}")

                # Check take-profit
                elif pos.take_profit > 0:
                    if (pos.side == PositionSide.LONG and price >= pos.take_profit) or \
                       (pos.side == PositionSide.SHORT and price <= pos.take_profit):
                        self._execute_stop(portfolio, pos, price, "take_profit")
                        events.append(f"TAKE_PROFIT: {symbol} @ {price}")

            # Check pending limit orders
            for order in portfolio.order_history:
                if order.status != OrderStatus.PENDING:
                    continue
                sym_price = prices.get(order.symbol.upper())
                if not sym_price:
                    continue
                if order.order_type == OrderType.LIMIT:
                    if (order.side == OrderSide.BUY and sym_price <= order.price) or \
                       (order.side == OrderSide.SELL and sym_price >= order.price):
                        self._execute_order(portfolio, order, sym_price)
                        events.append(f"LIMIT_FILL: {order.symbol} {order.side.value} @ {sym_price}")

            if events:
                self._save(user_id)
                log.info("paper.sl_tp_triggered", user_id=user_id, events=events)

        # Always save updated prices (for dashboard freshness)
        self._save(user_id)
        return events

    # ── Internal Execution ────────────────────────────────────────────────────

    def _validate_order(
        self, portfolio: PaperPortfolio, order: PaperOrder, price: float,
    ) -> Optional[str]:
        """Validate order. Returns rejection reason or None if valid."""
        if order.quantity <= 0:
            return "Quantity must be positive"
        if price <= 0:
            return "Price must be positive"

        cost = price * order.quantity
        if order.side == OrderSide.BUY:
            # Check if closing a short position (no cash needed) or opening long
            pos = portfolio.positions.get(order.symbol)
            if pos and pos.side == PositionSide.SHORT:
                return None  # Closing short — no cash check needed
            if cost > portfolio.cash_balance:
                return (f"Insufficient balance. Need ${cost:,.2f}, "
                        f"have ${portfolio.cash_balance:,.2f}")

        if order.side == OrderSide.SELL:
            pos = portfolio.positions.get(order.symbol)
            if pos and pos.side == PositionSide.LONG:
                # Closing long — check quantity
                if pos.quantity < order.quantity:
                    return (f"Insufficient position. Want to sell {order.quantity}, "
                            f"have {pos.quantity}")
            elif pos and pos.side == PositionSide.SHORT:
                # Adding to short — check margin (use 50% as margin requirement)
                margin_needed = cost * 0.5
                if margin_needed > portfolio.cash_balance:
                    return f"Insufficient margin for short. Need ${margin_needed:,.2f}"
            else:
                # Opening new short — check margin
                margin_needed = cost * 0.5
                if margin_needed > portfolio.cash_balance:
                    return f"Insufficient margin for short. Need ${margin_needed:,.2f}"

        return None

    def _execute_order(
        self,
        portfolio: PaperPortfolio,
        order: PaperOrder,
        market_price: float,
        stop_loss: float = 0,
        take_profit: float = 0,
    ) -> None:
        """Execute a paper order at market price with simulated slippage."""
        # Simulate slippage
        slippage = market_price * (order.slippage_pct / 100)
        if order.side == OrderSide.BUY:
            fill_price = market_price + slippage  # Pay slightly more
        else:
            fill_price = market_price - slippage  # Receive slightly less

        order.filled_price = fill_price
        order.filled_at = datetime.now(timezone.utc)
        order.status = OrderStatus.FILLED

        with self._lock:
            if order.side == OrderSide.BUY:
                # Update or create position
                pos = portfolio.positions.get(order.symbol)

                if pos and pos.side == PositionSide.SHORT:
                    # Buying to cover SHORT → close short position
                    self._execute_close(portfolio, order, pos, market_price,
                                        min(order.quantity, pos.quantity))
                else:
                    cost = fill_price * order.quantity
                    portfolio.cash_balance -= cost

                    if pos and pos.side == PositionSide.LONG:
                        # Average up/down existing long
                        total_qty = pos.quantity + order.quantity
                        pos.avg_entry_price = (
                            (pos.avg_entry_price * pos.quantity + fill_price * order.quantity)
                            / total_qty
                        )
                        pos.quantity = total_qty
                    else:
                        pos = PaperPosition(
                            symbol=order.symbol,
                            side=PositionSide.LONG,
                            quantity=order.quantity,
                            avg_entry_price=fill_price,
                            current_price=fill_price,
                            opened_at=datetime.now(timezone.utc),
                            strategy=order.strategy,
                        )
                    if stop_loss:
                        pos.stop_loss = stop_loss
                    if take_profit:
                        pos.take_profit = take_profit
                    pos.current_price = fill_price
                    portfolio.positions[order.symbol] = pos

            elif order.side == OrderSide.SELL:
                pos = portfolio.positions.get(order.symbol)

                if pos and pos.side == PositionSide.LONG:
                    # Closing long position
                    proceeds = fill_price * order.quantity
                    portfolio.cash_balance += proceeds
                    self._record_trade_close(portfolio, order, fill_price)
                else:
                    # Opening or adding to SHORT position
                    margin = fill_price * order.quantity * 0.5  # 50% margin
                    portfolio.cash_balance -= margin

                    if pos and pos.side == PositionSide.SHORT:
                        # Average into existing short
                        total_qty = pos.quantity + order.quantity
                        pos.avg_entry_price = (
                            (pos.avg_entry_price * pos.quantity + fill_price * order.quantity)
                            / total_qty
                        )
                        pos.quantity = total_qty
                    else:
                        pos = PaperPosition(
                            symbol=order.symbol,
                            side=PositionSide.SHORT,
                            quantity=order.quantity,
                            avg_entry_price=fill_price,
                            current_price=fill_price,
                            opened_at=datetime.now(timezone.utc),
                            strategy=order.strategy,
                        )
                    if stop_loss:
                        pos.stop_loss = stop_loss
                    if take_profit:
                        pos.take_profit = take_profit
                    pos.current_price = fill_price
                    portfolio.positions[order.symbol] = pos

            portfolio.order_history.append(order)
            self._save(order.user_id)

    def _execute_close(
        self,
        portfolio: PaperPortfolio,
        order: PaperOrder,
        position: PaperPosition,
        price: float,
        quantity: float,
    ) -> None:
        """Close a position (full or partial)."""
        slippage = price * (order.slippage_pct / 100)
        if position.side == PositionSide.LONG:
            fill_price = price - slippage
        else:
            fill_price = price + slippage

        order.filled_price = fill_price
        order.filled_at = datetime.now(timezone.utc)
        order.status = OrderStatus.FILLED

        # Calculate P&L
        if position.side == PositionSide.LONG:
            pnl = (fill_price - position.avg_entry_price) * quantity
        else:
            pnl = (position.avg_entry_price - fill_price) * quantity

        fee = fill_price * quantity * 0.001  # 0.1% simulated fee

        # Record trade
        portfolio.trade_log.append({
            "symbol": order.symbol,
            "side": "close_" + position.side.value,
            "quantity": quantity,
            "entry_price": round(position.avg_entry_price, 6),
            "exit_price": round(fill_price, 6),
            "gross_pnl": round(pnl, 2),
            "fee": round(fee, 2),
            "net_pnl": round(pnl - fee, 2),
            "return_pct": round((pnl / (position.avg_entry_price * quantity)) * 100, 2),
            "strategy": position.strategy,
            "holding_time": str(datetime.now(timezone.utc) - position.opened_at)
                           if position.opened_at else "",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })

        # Update cash
        if position.side == PositionSide.LONG:
            # Selling long → receive proceeds
            portfolio.cash_balance += fill_price * quantity
        else:
            # Closing short (buy to cover) → return margin + P&L
            margin_locked = position.avg_entry_price * quantity * 0.5
            portfolio.cash_balance += margin_locked + pnl - fee

        # Update position
        position.quantity -= quantity
        if position.quantity <= 0.000001:
            del portfolio.positions[order.symbol]
        else:
            portfolio.positions[order.symbol] = position

        portfolio.order_history.append(order)

    def _execute_stop(
        self, portfolio: PaperPortfolio, pos: PaperPosition,
        price: float, reason: str,
    ) -> None:
        """Execute stop-loss or take-profit."""
        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
        order = PaperOrder(
            user_id=portfolio.user_id,
            symbol=pos.symbol,
            side=side,
            order_type=OrderType.STOP_LOSS,
            quantity=pos.quantity,
            notes=reason,
        )
        self._execute_close(portfolio, order, pos, price, pos.quantity)
        log.info(f"paper.{reason}", user_id=portfolio.user_id,
                 symbol=pos.symbol, price=price)

    def _record_trade_close(
        self, portfolio: PaperPortfolio, order: PaperOrder, fill_price: float,
    ) -> None:
        """Record P&L when closing a position (LONG or SHORT)."""
        pos = portfolio.positions.get(order.symbol)
        if not pos:
            return

        qty = min(order.quantity, pos.quantity)

        # P&L depends on position direction
        if pos.side == PositionSide.LONG:
            pnl = (fill_price - pos.avg_entry_price) * qty
            close_side = "close_long"
        elif pos.side == PositionSide.SHORT:
            pnl = (pos.avg_entry_price - fill_price) * qty
            close_side = "close_short"
        else:
            return

        fee = fill_price * qty * 0.001
        cost = pos.avg_entry_price * qty

        portfolio.trade_log.append({
            "symbol": order.symbol,
            "side": close_side,
            "quantity": qty,
            "entry_price": round(pos.avg_entry_price, 6),
            "exit_price": round(fill_price, 6),
            "gross_pnl": round(pnl, 2),
            "fee": round(fee, 2),
            "net_pnl": round(pnl - fee, 2),
            "return_pct": round((pnl / cost) * 100, 2) if cost > 0 else 0,
            "strategy": pos.strategy or order.strategy,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })

        # Return margin/cash for closed SHORT positions
        if pos.side == PositionSide.SHORT:
            margin_returned = pos.avg_entry_price * qty * 0.5  # Return locked margin
            portfolio.cash_balance += margin_returned + pnl - fee

        pos.quantity -= qty
        if pos.quantity <= 0.000001:
            del portfolio.positions[order.symbol]

    # ── Leaderboard ───────────────────────────────────────────────────────────

    def get_leaderboard(self) -> list[dict]:
        """Get paper trading leaderboard ranked by total return."""
        board = []
        for uid, p in self._portfolios.items():
            board.append({
                "user_id": uid,
                "portfolio_value": round(p.portfolio_value, 2),
                "total_return_pct": round(p.total_return_pct, 2),
                "realized_pnl": round(p.realized_pnl, 2),
                "total_trades": len(p.trade_log),
                "win_rate": round(
                    len([t for t in p.trade_log if t.get("net_pnl", 0) > 0])
                    / max(len(p.trade_log), 1) * 100, 1
                ),
            })
        return sorted(board, key=lambda x: x["total_return_pct"], reverse=True)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self, user_id: str) -> None:
        """Save user portfolio to disk."""
        p = self._portfolios.get(user_id)
        if not p:
            return
        try:
            data = {
                "user_id": p.user_id,
                "initial_balance": p.initial_balance,
                "cash_balance": p.cash_balance,
                "created_at": p.created_at.isoformat(),
                "positions": {s: pos.to_dict() for s, pos in p.positions.items()},
                "order_history": [o.to_dict() for o in p.order_history[-200:]],
                "trade_log": p.trade_log[-500:],
            }
            path = self._dir / f"{user_id}.json"
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error("paper.save_error", user_id=user_id, error=str(e))

    def _load_all(self) -> None:
        """Load all user portfolios from disk."""
        for path in self._dir.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                uid = data["user_id"]
                p = PaperPortfolio(
                    user_id=uid,
                    initial_balance=data.get("initial_balance", DEFAULT_BALANCE),
                    cash_balance=data.get("cash_balance", DEFAULT_BALANCE),
                    trade_log=data.get("trade_log", []),
                )
                if data.get("created_at"):
                    p.created_at = datetime.fromisoformat(data["created_at"])

                # Restore positions
                for sym, pos_data in data.get("positions", {}).items():
                    p.positions[sym] = PaperPosition(
                        symbol=sym,
                        side=PositionSide(pos_data.get("side", "flat")),
                        quantity=pos_data.get("quantity", 0),
                        avg_entry_price=pos_data.get("avg_entry_price", 0),
                        current_price=pos_data.get("current_price", 0),
                        stop_loss=pos_data.get("stop_loss", 0),
                        take_profit=pos_data.get("take_profit", 0),
                        strategy=pos_data.get("strategy", "manual"),
                    )

                self._portfolios[uid] = p
            except Exception as e:
                log.error("paper.load_error", path=str(path), error=str(e))


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine: Optional[PaperTradingEngine] = None

def get_paper_engine() -> PaperTradingEngine:
    global _engine
    if _engine is None:
        _engine = PaperTradingEngine()
    return _engine
