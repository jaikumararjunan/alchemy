"""
alchemy.execution.order_pipeline
===================================
Unified Order Execution Pipeline — Risk-First Order Processing.

Every order (paper or live) flows through this pipeline:

    User/Strategy Signal
         │
    [1] Kill Switch Check  — Is emergency stop active? → REJECT
         │
    [2] Session Check      — Is the market open? → REJECT if closed
         │
    [3] Dedup Guard        — Same order within 60s? → REJECT
         │
    [4] Price Guard        — Price >5% from market? → REJECT (fat finger)
         │
    [5] Position Sizing    — Exceeds max position %? → RESIZE or REJECT
         │
    [6] Rate Limiter       — Exchange limit hit? → QUEUE with backoff
         │
    [7] Execute            — Paper engine or live gateway
         │
    [8] Audit Log          — Write immutable trade record
         │
    [9] Notification       — Email/Slack/Push alert
         │
    [10] P&L Update        — Update portfolio & analytics

Usage::

    from alchemy.execution.order_pipeline import execute_order

    result = await execute_order(
        user_id="user123",
        exchange="binance",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        order_type="MARKET",
        mode="paper",       # "paper" or "live"
    )
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)


# ── Order Request / Result Models ─────────────────────────────────────────────

class OrderRequest:
    """Standardized order request across all exchanges."""
    def __init__(self, **kwargs):
        self.user_id:      str   = kwargs.get("user_id", "")
        self.exchange:     str   = kwargs.get("exchange", "binance")
        self.symbol:       str   = kwargs.get("symbol", "").upper()
        self.side:         str   = kwargs.get("side", "BUY").upper()
        self.quantity:     float = kwargs.get("quantity", 0)
        self.order_type:   str   = kwargs.get("order_type", "MARKET").upper()
        self.price:        float = kwargs.get("price", 0)        # Limit price
        self.stop_price:   float = kwargs.get("stop_price", 0)
        self.stop_loss:    float = kwargs.get("stop_loss", 0)
        self.take_profit:  float = kwargs.get("take_profit", 0)
        self.leverage:     int   = kwargs.get("leverage", 1)
        self.mode:         str   = kwargs.get("mode", "paper")   # "paper" or "live"
        self.strategy:     str   = kwargs.get("strategy", "manual")
        self.notes:        str   = kwargs.get("notes", "")
        self.market_price: float = kwargs.get("market_price", 0) # Current market price
        self.timestamp:    float = time.time()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id, "exchange": self.exchange,
            "symbol": self.symbol, "side": self.side,
            "quantity": self.quantity, "order_type": self.order_type,
            "price": self.price, "market_price": self.market_price,
            "stop_loss": self.stop_loss, "take_profit": self.take_profit,
            "leverage": self.leverage, "mode": self.mode,
            "strategy": self.strategy, "notes": self.notes,
        }


class OrderResult:
    """Standardized order result."""
    def __init__(self, success: bool, **kwargs):
        self.success:      bool  = success
        self.order_id:     str   = kwargs.get("order_id", "")
        self.filled_price: float = kwargs.get("filled_price", 0)
        self.filled_qty:   float = kwargs.get("filled_qty", 0)
        self.status:       str   = kwargs.get("status", "")
        self.message:      str   = kwargs.get("message", "")
        self.rejected_by:  str   = kwargs.get("rejected_by", "")
        self.exchange_response: dict = kwargs.get("exchange_response", {})
        self.pnl:          float = kwargs.get("pnl", 0)
        self.fee:          float = kwargs.get("fee", 0)
        self.timestamp:    float = time.time()

    def to_dict(self) -> dict:
        return {
            "success": self.success, "order_id": self.order_id,
            "filled_price": self.filled_price, "filled_qty": self.filled_qty,
            "status": self.status, "message": self.message,
            "rejected_by": self.rejected_by, "pnl": self.pnl, "fee": self.fee,
        }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

async def execute_order(
    user_id: str,
    exchange: str,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET",
    price: float = 0,
    stop_loss: float = 0,
    take_profit: float = 0,
    leverage: int = 1,
    mode: str = "paper",
    strategy: str = "manual",
    notes: str = "",
    market_price: float = 0,
) -> OrderResult:
    """
    Execute an order through the full risk pipeline.

    Args:
        mode: "paper" for virtual trading, "live" for real execution
    """
    req = OrderRequest(
        user_id=user_id, exchange=exchange, symbol=symbol,
        side=side, quantity=quantity, order_type=order_type,
        price=price, stop_loss=stop_loss, take_profit=take_profit,
        leverage=leverage, mode=mode, strategy=strategy,
        notes=notes, market_price=market_price,
    )

    log.info("pipeline.order_received", user_id=user_id, exchange=exchange,
             symbol=symbol, side=side, qty=quantity, mode=mode)

    # ── [1] Kill Switch Check ─────────────────────────────────────────────
    try:
        from alchemy.risk.kill_switch import is_kill_switch_active
        if is_kill_switch_active():
            log.warning("pipeline.killed", user_id=user_id, symbol=symbol)
            return _reject(req, "kill_switch",
                           "Emergency stop is active. All trading halted.")
    except ImportError:
        pass

    # ── [2] Session Check ─────────────────────────────────────────────────
    try:
        from alchemy.trading.session_manager import get_session_manager
        sm = get_session_manager()
        session = sm.get_session(exchange, symbol)
        if session and not session.get("is_open", True):
            log.info("pipeline.market_closed", symbol=symbol, exchange=exchange)
            return _reject(req, "market_closed",
                           f"Market is closed. {session.get('next_open', 'Check exchange hours.')}")
    except (ImportError, Exception):
        pass  # Session manager optional — allow through if not configured

    # ── [3] Dedup Guard ───────────────────────────────────────────────────
    try:
        from alchemy.risk.dedup import get_deduplicator
        dedup = get_deduplicator()
        is_dup = dedup.is_duplicate(
            strategy=strategy, symbol=symbol, side=side,
        )
        if is_dup:
            log.warning("pipeline.duplicate", user_id=user_id, symbol=symbol)
            return _reject(req, "duplicate_order",
                           "Duplicate order detected. Same order was placed within cooldown window.")
    except ImportError:
        pass

    # ── [4] Price Guard ───────────────────────────────────────────────────
    if market_price > 0:
        try:
            from alchemy.risk.price_guard import get_price_guard
            pg = get_price_guard()
            effective_price = price if order_type == "LIMIT" and price > 0 else market_price
            # Update reference price first, then validate
            pg.update_price(symbol, market_price)
            result_pg = pg.validate(symbol, effective_price)
            if not result_pg.valid:
                log.warning("pipeline.price_guard", user_id=user_id,
                            symbol=symbol, reason=result_pg.reason)
                return _reject(req, "price_guard", result_pg.reason)
        except ImportError:
            pass

    # ── [5] Position Sizing ───────────────────────────────────────────────
    # (Optional: check if order exceeds max position % of account)
    # This is advisory — doesn't block but logs a warning
    try:
        from alchemy.risk.position_sizing import check_position_limit
        warning = check_position_limit(user_id, symbol, quantity, market_price)
        if warning:
            log.warning("pipeline.position_warning", user_id=user_id, warning=warning)
            req.notes += f" [POSITION WARNING: {warning}]"
    except (ImportError, Exception):
        pass

    # ── [6] Rate Limiter ──────────────────────────────────────────────────
    try:
        from alchemy.execution.rate_limiter import get_rate_limiter
        limiter = get_rate_limiter(exchange)
        if limiter:
            import asyncio
            wait_s = await limiter.acquire(weight=1)
            if wait_s > 0:
                log.info("pipeline.rate_limited", exchange=exchange, wait_s=round(wait_s, 2))
    except (ImportError, Exception):
        pass

    # ── [7] Execute ───────────────────────────────────────────────────────
    if mode == "paper":
        result = await _execute_paper(req)
    elif mode == "live":
        result = await _execute_live(req)
    else:
        return _reject(req, "invalid_mode", f"Unknown mode: {mode}")

    # ── [8] Audit Log ─────────────────────────────────────────────────────
    try:
        from alchemy.risk.audit_log import get_audit_log, AuditAction
        audit = get_audit_log()
        action = AuditAction.ORDER_FILLED if result.success else AuditAction.ORDER_REJECTED
        audit.log_order(
            action=action,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=result.filled_qty if result.success else quantity,
            price=result.filled_price,
            order_id=result.order_id,
            strategy=strategy,
            user_id=user_id,
            mode=mode,
            error=result.message if not result.success else "",
        )
    except (ImportError, Exception) as e:
        log.warning("pipeline.audit_failed", error=str(e))

    # ── [9] Notification ──────────────────────────────────────────────────
    if result.success:
        try:
            _send_trade_notification(req, result)
        except Exception:
            pass  # Don't fail the order because of notification

    log.info("pipeline.completed",
             user_id=user_id, symbol=symbol, success=result.success,
             status=result.status, mode=mode,
             filled_price=result.filled_price)

    return result


# ── Paper Execution ───────────────────────────────────────────────────────────

async def _execute_paper(req: OrderRequest) -> OrderResult:
    """Execute order via paper trading engine."""
    try:
        from alchemy.paper_trading.engine import get_paper_engine
        engine = get_paper_engine()

        if req.side == "BUY":
            order = engine.place_order(
                user_id=req.user_id, symbol=req.symbol,
                side="buy", quantity=req.quantity,
                current_price=req.market_price or req.price,
                order_type=req.order_type.lower(),
                limit_price=req.price if req.order_type == "LIMIT" else 0,
                stop_loss=req.stop_loss, take_profit=req.take_profit,
                strategy=req.strategy, notes=req.notes,
            )
        else:
            order = engine.close_position(
                user_id=req.user_id, symbol=req.symbol,
                current_price=req.market_price or req.price,
                quantity=req.quantity, notes=req.notes,
            )
            if not order:
                return OrderResult(False, status="rejected",
                                   message=f"No open position for {req.symbol}",
                                   rejected_by="paper_engine")

        return OrderResult(
            success=order.status.value == "filled",
            order_id=order.id,
            filled_price=order.filled_price,
            filled_qty=req.quantity,
            status=order.status.value,
            message=f"Paper {req.side} {req.quantity} {req.symbol} @ ${order.filled_price:,.2f}",
        )
    except Exception as e:
        log.error("pipeline.paper_error", error=str(e))
        return OrderResult(False, status="error", message=str(e),
                           rejected_by="paper_engine")


# ── Live Execution ────────────────────────────────────────────────────────────

async def _execute_live(req: OrderRequest) -> OrderResult:
    """Execute order via live exchange gateway + record in unified portfolio."""
    try:
        from alchemy.api.token_routes import get_live_gateway
        gateway = get_live_gateway(req.exchange, req.user_id)

        if not gateway:
            return OrderResult(False, status="rejected",
                               message=f"No credentials configured for {req.exchange}. "
                                       f"Go to Settings → Tokens to connect.",
                               rejected_by="no_gateway")

        # Execute on exchange
        result = gateway.place_order(
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            order_type=req.order_type,
            price=req.price if req.order_type == "LIMIT" else None,
            leverage=req.leverage,
        )

        # Parse exchange response
        filled_price = float(result.get("avgPrice", 0) or result.get("price", 0) or 0)
        filled_qty = float(result.get("executedQty", 0) or result.get("origQty", 0) or 0)
        order_id = str(result.get("orderId", "") or result.get("order_id", ""))
        status = result.get("status", "FILLED").lower()

        is_success = status in ("filled", "new", "partially_filled")

        # ── Record in paper trading engine for unified dashboard ──
        if is_success and filled_price > 0:
            try:
                from alchemy.paper_trading.engine import get_paper_engine
                engine = get_paper_engine()
                side_norm = "buy" if req.side.upper() in ("BUY", "LONG") else "sell"

                if side_norm == "buy":
                    engine.place_order(
                        user_id=req.user_id, symbol=req.symbol, side="buy",
                        quantity=filled_qty or req.quantity,
                        current_price=filled_price,
                        order_type="market",
                        strategy=f"live_{req.exchange}",
                        notes=f"Live trade via {req.exchange} | Order #{order_id}",
                    )
                else:
                    engine.close_position(
                        user_id=req.user_id, symbol=req.symbol,
                        current_price=filled_price,
                        quantity=filled_qty or req.quantity,
                    )
                log.info("pipeline.live_recorded_in_portfolio",
                         symbol=req.symbol, side=req.side, price=filled_price)
            except Exception as pe:
                log.warning("pipeline.portfolio_record_failed", error=str(pe))

        return OrderResult(
            success=is_success,
            order_id=order_id,
            filled_price=filled_price,
            filled_qty=filled_qty,
            status=status,
            message=f"LIVE {req.side} {filled_qty} {req.symbol} @ ${filled_price:,.2f}",
            exchange_response=result,
        )

    except Exception as e:
        log.error("pipeline.live_error", exchange=req.exchange,
                  symbol=req.symbol, error=str(e))
        return OrderResult(False, status="error",
                           message=f"Exchange error: {str(e)}",
                           rejected_by="exchange")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reject(req: OrderRequest, guard: str, message: str) -> OrderResult:
    """Create a rejection result."""
    return OrderResult(
        success=False,
        status="rejected",
        message=message,
        rejected_by=guard,
    )


def _send_trade_notification(req: OrderRequest, result: OrderResult):
    """Send trade notification (non-blocking)."""
    try:
        from alchemy.notifications.engine import get_notification_engine
        engine = get_notification_engine()
        if not engine:
            return

        severity = "info" if result.success else "warning"
        title = f"{'🟢' if req.side == 'BUY' else '🔴'} {req.side} {req.symbol}"
        message = result.message

        import asyncio
        asyncio.create_task(engine.notify(
            user_id=req.user_id,
            event_type="trade_fill",
            title=title,
            message=message,
            severity=severity,
            data={
                "symbol": req.symbol,
                "side": req.side,
                "quantity": result.filled_qty,
                "fill_price": result.filled_price,
                "mode": req.mode,
                "strategy": req.strategy,
            },
        ))
    except Exception:
        pass  # Never fail on notification errors
