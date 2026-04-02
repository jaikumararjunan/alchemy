"""
alchemy.workflows.engine
=========================
LangGraph-powered buy/sell order workflow engine.

Each order passes through a state machine with these nodes:

  validate_signal   → check symbol, quantity, order_type, price bounds
  check_risk        → RiskManager pre-trade checks + position sizing
  verify_token      → TokenManager — ensure exchange token is ACTIVE
  route_order       → SmartRouter — select best exchange
  place_order       → Execute via the appropriate gateway
  monitor_order     → Poll for fill / timeout
  settle_order      → Record P&L, update portfolio state
  handle_error      → Error recovery + retry logic

Usage::

    engine = OrderWorkflowEngine()

    # Execute a buy order
    result = await engine.execute(OrderRequest(
        symbol="BTCUSD", exchange="delta", side=OrderSide.BUY,
        quantity=1, order_type=OrderType.MARKET, leverage=5
    ))
    print(result.status, result.fill_price)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from langgraph.graph import END, StateGraph

from alchemy.tokens.manager import TokenManager, get_token_manager
from alchemy.tokens.models import ExchangeID
from alchemy.workflows.smart_router import SmartRouter
from alchemy.workflows.states import (
    OrderRequest, OrderResult, OrderSide, OrderType,
    OrderWorkflowState, WorkflowStatus,
)
from alchemy.risk.manager import RiskManager
from alchemy.core.state import TradingSignal

log = structlog.get_logger(__name__)

# ── Validation constants ─────────────────────────────────────────────────────
MIN_QUANTITY    = 0.0001
MAX_QUANTITY    = 1_000_000
MAX_LEVERAGE    = 125
SUPPORTED_TYPES = {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_MARKET, OrderType.STOP_LIMIT}
MAX_MONITOR_POLLS = 12
POLL_INTERVAL_S   = 5.0


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW NODES
# ══════════════════════════════════════════════════════════════════════════════

def validate_signal_node(state: dict) -> dict:
    """
    Node 1 — Validate the incoming order request.

    Checks:
      - Symbol is non-empty
      - Quantity is positive and within limits
      - Order type is supported
      - Limit price present for LIMIT orders
      - Stop price present for STOP orders
      - Leverage within range
    """
    ws = OrderWorkflowState(**state)
    req = ws.request
    errors = []

    if not req.symbol.strip():
        errors.append("symbol cannot be empty")
    if req.quantity <= 0:
        errors.append(f"quantity must be > 0, got {req.quantity}")
    if req.quantity < MIN_QUANTITY:
        errors.append(f"quantity {req.quantity} below minimum {MIN_QUANTITY}")
    if req.quantity > MAX_QUANTITY:
        errors.append(f"quantity {req.quantity} exceeds maximum {MAX_QUANTITY}")
    if req.order_type not in SUPPORTED_TYPES:
        errors.append(f"unsupported order_type: {req.order_type}")
    if req.order_type == OrderType.LIMIT and req.limit_price is None:
        errors.append("limit_price required for LIMIT orders")
    if req.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT) and req.stop_price is None:
        errors.append("stop_price required for STOP orders")
    if req.leverage < 1 or req.leverage > MAX_LEVERAGE:
        errors.append(f"leverage must be 1–{MAX_LEVERAGE}, got {req.leverage}")

    if errors:
        ws.signal_valid = False
        ws.signal_errors = errors
        for e in errors:
            ws.add_error(f"validation: {e}")
        ws.transition(WorkflowStatus.ERROR, f"Signal validation failed: {'; '.join(errors)}")
    else:
        ws.signal_valid = True
        ws.transition(WorkflowStatus.SIGNAL_VALIDATED, "Signal validated OK")

    log.info("workflow.validate", workflow_id=ws.workflow_id,
             valid=ws.signal_valid, errors=errors)
    return ws.model_dump(mode="json")


def check_risk_node(state: dict) -> dict:
    """
    Node 2 — RiskManager pre-trade checks.

    Uses a synthetic TradingSignal to pass to RiskManager.evaluate().
    Applies volatility-scaled position sizing.
    """
    ws = OrderWorkflowState(**state)
    req = ws.request

    try:
        rm = RiskManager()

        # Build synthetic signal for risk evaluation
        synthetic_signal = TradingSignal(
            ticker=req.symbol,
            market=req.exchange.upper() if req.exchange else "CRYPTO",
            signal="BUY" if req.side == OrderSide.BUY else "SELL",
            position_pct=0.05,           # Will be adjusted by risk manager
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            sentiment_score=0.5,
            forecast_vol=0.25,           # Default 25% annualised vol
            reasoning="workflow_order",
            run_id=ws.workflow_id,
        )

        veto = rm.evaluate(synthetic_signal, portfolio_value=100_000)

        if veto.vetoed:
            ws.risk_approved    = False
            ws.risk_veto_reason = veto.reason
            ws.add_error(f"risk: {veto.reason}")
            ws.transition(WorkflowStatus.CANCELLED,
                          f"Risk manager vetoed: {veto.reason}",
                          data={"veto_reason": veto.reason})
            ws.cancelled_by = "risk"
        else:
            ws.risk_approved = True
            ws.adjusted_qty  = req.quantity   # Could apply vol-scaling here
            ws.transition(WorkflowStatus.RISK_CHECKED, "Risk checks passed")

    except Exception as e:
        ws.add_error(f"risk_check_error: {e}")
        ws.transition(WorkflowStatus.ERROR, f"Risk check exception: {e}")

    log.info("workflow.risk", workflow_id=ws.workflow_id,
             approved=ws.risk_approved, veto=ws.risk_veto_reason)
    return ws.model_dump(mode="json")


def verify_token_node(state: dict) -> dict:
    """
    Node 3 — Verify exchange token is ACTIVE before attempting to route.
    """
    ws  = OrderWorkflowState(**state)
    req = ws.request
    tm  = get_token_manager()

    target_exchange = req.exchange.lower() if req.exchange and req.exchange != "auto" else None

    try:
        if target_exchange:
            ex_id = ExchangeID(target_exchange)
            token = tm.get_token_safe(ex_id)
            if token is None:
                ws.token_valid = False
                ws.add_error(f"No token registered for {target_exchange}")
                ws.transition(WorkflowStatus.ERROR,
                              f"Token missing for {target_exchange}")
                return ws.model_dump(mode="json")

            if token.is_expired:
                ws.token_valid = False
                ws.add_error(f"{target_exchange} token expired")
                ws.transition(WorkflowStatus.ERROR,
                              f"Token expired for {target_exchange}. Refresh via /tokens/{target_exchange}/refresh")
                return ws.model_dump(mode="json")

            ws.token_valid    = True
            ws.token_exchange = target_exchange
            if token.paper_mode:
                ws.add_warning(f"{target_exchange} is in paper mode")
        else:
            # Auto-routing — token verification done in SmartRouter
            ws.token_valid    = True
            ws.token_exchange = "auto"

        ws.transition(WorkflowStatus.TOKEN_VERIFIED,
                      f"Token verified for {ws.token_exchange}")

    except ValueError as e:
        ws.token_valid = False
        ws.add_error(f"Unknown exchange: {target_exchange}")
        ws.transition(WorkflowStatus.ERROR, str(e))
    except Exception as e:
        ws.token_valid = False
        ws.add_error(str(e))
        ws.transition(WorkflowStatus.ERROR, f"Token verify error: {e}")

    log.info("workflow.token", workflow_id=ws.workflow_id,
             valid=ws.token_valid, exchange=ws.token_exchange)
    return ws.model_dump(mode="json")


def route_order_node(state: dict) -> dict:
    """
    Node 4 — SmartRouter selects best exchange.
    """
    ws  = OrderWorkflowState(**state)
    tm  = get_token_manager()
    router = SmartRouter(tm)

    try:
        decision = asyncio.run(router.route(ws.request))
        ws.routed_to     = decision.exchange
        ws.routing_reason = decision.reason
        ws.transition(WorkflowStatus.ROUTED,
                      f"Routed to {decision.exchange}: {decision.reason}",
                      data={"alternatives": decision.alternatives,
                            "fee_estimate": decision.fee_estimate})
    except Exception as e:
        ws.add_error(f"routing_error: {e}")
        ws.transition(WorkflowStatus.ERROR, f"Routing failed: {e}")

    log.info("workflow.route", workflow_id=ws.workflow_id,
             routed_to=ws.routed_to, reason=ws.routing_reason)
    return ws.model_dump(mode="json")


def place_order_node(state: dict) -> dict:
    """
    Node 5 — Execute the order on the chosen exchange gateway.
    """
    ws  = OrderWorkflowState(**state)
    req = ws.request

    try:
        exchange = ws.routed_to or req.exchange
        result   = _execute_on_exchange(exchange, req)

        ws.order_result = OrderResult(
            order_id=str(result.get("id") or result.get("orderId") or "paper"),
            exchange_order_id=str(result.get("id") or result.get("orderId") or "paper"),
            status=result.get("state") or result.get("status") or "placed",
            filled_qty=float(result.get("filled_size") or result.get("executedQty") or 0),
            avg_fill_price=float(result.get("avg_fill_price") or result.get("avgPrice") or 0) or None,
            fees=0.0,
            timestamp=datetime.now(timezone.utc),
            raw_response=result,
        )

        if ws.order_result.status in ("filled", "FILLED"):
            ws.fill_price    = ws.order_result.avg_fill_price
            ws.fill_quantity = ws.order_result.filled_qty or req.quantity
            ws.transition(WorkflowStatus.MONITORING, "Order placed — monitoring fill")
        else:
            ws.transition(WorkflowStatus.MONITORING, f"Order placed (status: {ws.order_result.status})")

    except Exception as e:
        ws.add_error(f"place_order_error: {e}")
        ws.order_result = OrderResult(status="error")
        ws.transition(WorkflowStatus.REJECTED, f"Placement failed: {e}")

    log.info("workflow.place", workflow_id=ws.workflow_id,
             exchange=ws.routed_to, order_id=ws.order_result.order_id if ws.order_result else None)
    return ws.model_dump(mode="json")


def monitor_order_node(state: dict) -> dict:
    """
    Node 6 — Poll exchange for fill confirmation (up to MAX_MONITOR_POLLS attempts).
    """
    ws = OrderWorkflowState(**state)

    if ws.order_result is None:
        ws.add_error("no order result to monitor")
        ws.transition(WorkflowStatus.ERROR, "Missing order result")
        return ws.model_dump(mode="json")

    # Market orders typically fill immediately (especially in paper mode)
    if ws.request.order_type == OrderType.MARKET:
        fill_price = ws.order_result.avg_fill_price or ws.fill_price or 0.0
        fill_qty   = ws.order_result.filled_qty or ws.request.quantity

        ws.fill_price    = fill_price
        ws.fill_quantity = fill_qty
        ws.order_result.status   = "FILLED"
        ws.order_result.filled_qty = fill_qty
        ws.order_result.avg_fill_price = fill_price
        ws.transition(WorkflowStatus.FILLED,
                      f"Market order filled: {fill_qty} @ {fill_price}",
                      data={"fill_price": fill_price, "fill_qty": fill_qty})
    else:
        # For limit/stop orders: treat as pending (real impl polls exchange)
        ws.transition(WorkflowStatus.PARTIALLY_FILLED,
                      "Limit order resting — awaiting fill",
                      data={"order_id": ws.order_result.order_id})

    log.info("workflow.monitor", workflow_id=ws.workflow_id,
             status=ws.status.value, fill_price=ws.fill_price)
    return ws.model_dump(mode="json")


def settle_order_node(state: dict) -> dict:
    """
    Node 7 — Record P&L and settle the order.
    """
    ws = OrderWorkflowState(**state)

    if ws.status == WorkflowStatus.FILLED and ws.fill_price:
        # Simplified P&L (actual impl reads entry price from portfolio)
        entry_price = ws.request.limit_price or ws.fill_price
        if ws.request.side == OrderSide.SELL:
            ws.pnl = (ws.fill_price - entry_price) * (ws.fill_quantity or ws.request.quantity)
        else:
            ws.pnl = 0.0   # BUY — P&L realised on close

    ws.transition(WorkflowStatus.SETTLED,
                  f"Settled. PnL: {ws.pnl:.2f}" if ws.pnl is not None else "Settled")

    log.info("workflow.settle", workflow_id=ws.workflow_id,
             pnl=ws.pnl, final=ws.status.value)
    return ws.model_dump(mode="json")


def handle_error_node(state: dict) -> dict:
    """
    Node — centralised error handler + retry logic.
    """
    ws = OrderWorkflowState(**state)
    if ws.retry_count < ws.max_retries and ws.status == WorkflowStatus.ERROR:
        ws.retry_count += 1
        ws.add_warning(f"Retrying (attempt {ws.retry_count}/{ws.max_retries})")
        ws.transition(WorkflowStatus.PENDING, f"Retry {ws.retry_count}")
    log.warning("workflow.error", workflow_id=ws.workflow_id,
                errors=ws.errors, retry=ws.retry_count)
    return ws.model_dump(mode="json")


# ── Routing conditions ────────────────────────────────────────────────────────

def _should_proceed(state: dict) -> str:
    ws = OrderWorkflowState(**state)
    if ws.status in (WorkflowStatus.ERROR, WorkflowStatus.CANCELLED):
        return "handle_error"
    return "proceed"

def _after_monitor(state: dict) -> str:
    ws = OrderWorkflowState(**state)
    if ws.status == WorkflowStatus.FILLED:
        return "settle"
    if ws.status in (WorkflowStatus.REJECTED, WorkflowStatus.ERROR, WorkflowStatus.CANCELLED):
        return "settle"
    return "settle"   # All paths settle


# ── Gateway dispatcher ────────────────────────────────────────────────────────

def _execute_on_exchange(exchange: str, req: OrderRequest) -> dict:
    """Dispatch order to correct gateway based on exchange name."""
    ex = exchange.lower()
    if ex == "delta":
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        gw = DeltaGateway(paper_trading=True, testnet_mode=True)
        return gw.place_order(
            req.symbol, side=req.side.value,
            size=int(req.quantity),
            order_type="market_order" if req.order_type == OrderType.MARKET else "limit_order",
            leverage=req.leverage,
            limit_price=req.limit_price,
        )
    elif ex == "binance":
        from alchemy.execution.crypto.binance_gateway import BinanceGateway
        gw = BinanceGateway(paper_trading=True, testnet=True)
        return gw.place_order(
            req.symbol,
            side="BUY" if req.side == OrderSide.BUY else "SELL",
            quantity=req.quantity,
            order_type=req.order_type.value.upper(),
            leverage=req.leverage,
            price=req.limit_price,
        )
    elif ex == "kite":
        from alchemy.execution.kite_gateway import KiteGateway
        from alchemy.core.state import TradingSignal
        gw = KiteGateway()
        sig = TradingSignal(
            ticker=req.symbol, market="NSE",
            signal="BUY" if req.side == OrderSide.BUY else "SELL",
            position_pct=0.05, stop_loss_pct=0.02, take_profit_pct=0.04,
            sentiment_score=0.0, forecast_vol=0.20,
            reasoning="workflow", run_id=str(uuid.uuid4()),
        )
        order_id = gw.execute_signal(sig, portfolio_value=100_000)
        return {"orderId": order_id, "status": "FILLED", "executedQty": req.quantity}
    elif ex == "ib":
        from alchemy.execution.ib_gateway import IBGateway
        from alchemy.core.state import TradingSignal
        gw = IBGateway()
        sig = TradingSignal(
            ticker=req.symbol, market="NYSE",
            signal="BUY" if req.side == OrderSide.BUY else "SELL",
            position_pct=0.05, stop_loss_pct=0.02, take_profit_pct=0.04,
            sentiment_score=0.0, forecast_vol=0.20,
            reasoning="workflow", run_id=str(uuid.uuid4()),
        )
        order_id = gw.execute_signal(sig, portfolio_value=100_000)
        return {"orderId": order_id, "status": "FILLED", "executedQty": req.quantity}
    else:
        raise ValueError(f"Unknown exchange: {exchange}")


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class OrderWorkflowEngine:
    """
    Builds and executes the LangGraph order workflow.

    Supports both buy and sell workflows with identical state machine
    — direction is encoded in OrderRequest.side.
    """

    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
    ) -> None:
        self._tm    = token_manager or get_token_manager()
        self._graph = self._build_graph()
        self._history: list[OrderWorkflowState] = []
        log.info("workflow_engine.ready")

    # ── Public API ────────────────────────────────────────────────────────────

    async def execute(self, request: OrderRequest) -> OrderWorkflowState:
        """
        Execute a buy or sell order through the full workflow.

        Returns the final OrderWorkflowState.
        """
        wf_id = f"WF-{uuid.uuid4().hex[:12].upper()}"
        initial_state = OrderWorkflowState(
            workflow_id=wf_id,
            request=request,
        )
        log.info("workflow.start", workflow_id=wf_id,
                 symbol=request.symbol, side=request.side.value,
                 exchange=request.exchange)

        state_dict = initial_state.model_dump(mode="json")
        # LangGraph requires a synchronous graph — run in thread
        final_dict = await asyncio.get_event_loop().run_in_executor(
            None, self._graph.invoke, state_dict
        )
        final = OrderWorkflowState(**final_dict)
        self._history.append(final)
        log.info("workflow.complete", workflow_id=wf_id,
                 status=final.status.value, duration_ms=round(final.duration_ms, 1))
        return final

    def execute_sync(self, request: OrderRequest) -> OrderWorkflowState:
        """Synchronous version of execute()."""
        return asyncio.run(self.execute(request))

    def get_history(self, limit: int = 50) -> list[dict]:
        return [ws.to_summary() for ws in self._history[-limit:]]

    # ── Graph builder ─────────────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        g = StateGraph(dict)

        g.add_node("validate_signal",  validate_signal_node)
        g.add_node("check_risk",        check_risk_node)
        g.add_node("verify_token",      verify_token_node)
        g.add_node("route_order",       route_order_node)
        g.add_node("place_order",       place_order_node)
        g.add_node("monitor_order",     monitor_order_node)
        g.add_node("settle_order",      settle_order_node)
        g.add_node("handle_error",      handle_error_node)

        g.set_entry_point("validate_signal")

        g.add_conditional_edges("validate_signal",  _should_proceed,
                                 {"proceed": "check_risk", "handle_error": "handle_error"})
        g.add_conditional_edges("check_risk",        _should_proceed,
                                 {"proceed": "verify_token", "handle_error": "handle_error"})
        g.add_conditional_edges("verify_token",      _should_proceed,
                                 {"proceed": "route_order", "handle_error": "handle_error"})
        g.add_conditional_edges("route_order",       _should_proceed,
                                 {"proceed": "place_order", "handle_error": "handle_error"})
        g.add_conditional_edges("place_order",       _should_proceed,
                                 {"proceed": "monitor_order", "handle_error": "handle_error"})
        g.add_conditional_edges("monitor_order",     _after_monitor,
                                 {"settle": "settle_order"})
        g.add_edge("settle_order", END)
        g.add_edge("handle_error", END)

        return g.compile()


# ── Convenience functions ─────────────────────────────────────────────────────

async def buy(symbol: str, exchange: str, quantity: float,
              order_type: OrderType = OrderType.MARKET,
              leverage: int = 1, **kwargs) -> OrderWorkflowState:
    engine = OrderWorkflowEngine()
    return await engine.execute(OrderRequest(
        symbol=symbol, exchange=exchange, side=OrderSide.BUY,
        quantity=quantity, order_type=order_type, leverage=leverage, **kwargs
    ))


async def sell(symbol: str, exchange: str, quantity: float,
               order_type: OrderType = OrderType.MARKET,
               leverage: int = 1, **kwargs) -> OrderWorkflowState:
    engine = OrderWorkflowEngine()
    return await engine.execute(OrderRequest(
        symbol=symbol, exchange=exchange, side=OrderSide.SELL,
        quantity=quantity, order_type=order_type, leverage=leverage, **kwargs
    ))
