"""
alchemy.api.token_routes  — Token Management REST API
alchemy.api.workflow_routes — Order Workflow REST API
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════════════════════
# TOKEN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

token_router = APIRouter(prefix="/tokens", tags=["tokens"])


class RegisterTokenRequest(BaseModel):
    exchange:     Literal["kite","delta","binance","ib"]
    api_key:      str
    api_secret:   str
    paper_mode:   bool = True
    # Kite-specific
    access_token: Optional[str] = None
    # Delta-specific
    testnet:      Optional[bool] = True
    # Binance-specific
    market_type:  Optional[str] = "futures_usdm"
    # IB-specific
    host:         Optional[str] = "127.0.0.1"
    port:         Optional[int] = 7497


def _get_tm():
    from alchemy.tokens.manager import get_token_manager
    return get_token_manager()


@token_router.get("/status")
async def get_all_token_status():
    """Return status of all exchange tokens (no secrets exposed)."""
    return _get_tm().status()


@token_router.get("/status/{exchange}")
async def get_token_status(exchange: str):
    status = _get_tm().status()
    if exchange not in status:
        raise HTTPException(404, f"Unknown exchange: {exchange}")
    return status[exchange]


@token_router.post("/register")
async def register_token(req: RegisterTokenRequest):
    """Register a new exchange token."""
    from alchemy.tokens.models import (
        KiteToken, DeltaToken, BinanceToken, IBToken, ExchangeID
    )
    tm = _get_tm()
    try:
        if req.exchange == "kite":
            token = KiteToken(
                api_key=req.api_key, api_secret=req.api_secret,
                access_token=req.access_token, paper_mode=req.paper_mode,
            )
        elif req.exchange == "delta":
            token = DeltaToken(
                api_key=req.api_key, api_secret=req.api_secret,
                testnet=req.testnet or True, paper_mode=req.paper_mode,
            )
        elif req.exchange == "binance":
            token = BinanceToken(
                api_key=req.api_key, api_secret=req.api_secret,
                market_type=req.market_type or "futures_usdm",
                paper_mode=req.paper_mode,
            )
        elif req.exchange == "ib":
            token = IBToken(
                api_key=req.api_key, api_secret=req.api_secret,
                host=req.host or "127.0.0.1", port=req.port or 7497,
                paper_mode=req.paper_mode,
            )
        else:
            raise HTTPException(400, f"Unknown exchange: {req.exchange}")

        tm.register(token)
        return {"ok": True, "exchange": req.exchange,
                "status": token.to_safe_dict()}
    except Exception as e:
        raise HTTPException(500, str(e))


@token_router.delete("/{exchange}")
async def deregister_token(exchange: str):
    """Remove a token from the vault."""
    from alchemy.tokens.models import ExchangeID
    try:
        ex = ExchangeID(exchange)
        deleted = _get_tm().deregister(ex)
        return {"ok": deleted, "exchange": exchange}
    except ValueError:
        raise HTTPException(404, f"Unknown exchange: {exchange}")


@token_router.post("/{exchange}/validate")
async def validate_token(exchange: str, background_tasks: BackgroundTasks):
    """Trigger async token validation against the live exchange API."""
    from alchemy.tokens.models import ExchangeID
    try:
        ex = ExchangeID(exchange)
        background_tasks.add_task(_get_tm().validate_token, ex)
        return {"ok": True, "message": f"Validation triggered for {exchange}"}
    except ValueError:
        raise HTTPException(404, f"Unknown exchange: {exchange}")


@token_router.post("/{exchange}/refresh")
async def refresh_token(exchange: str):
    """Manually trigger a token refresh."""
    from alchemy.tokens.models import ExchangeID
    try:
        ex = ExchangeID(exchange)
        success = _get_tm().refresh_token(ex, triggered_by="api")
        return {"ok": success, "exchange": exchange}
    except ValueError:
        raise HTTPException(404, f"Unknown exchange: {exchange}")


@token_router.put("/kite/access-token")
async def update_kite_token(body: dict):
    """Update Kite access_token after OAuth callback."""
    access_token = body.get("access_token")
    if not access_token:
        raise HTTPException(400, "access_token required")
    _get_tm().update_kite_access_token(access_token)
    return {"ok": True, "message": "Kite access_token updated"}


@token_router.get("/history")
async def refresh_history(limit: int = 20):
    """Return recent token refresh events."""
    return _get_tm().refresh_history(limit)


@token_router.post("/validate-all")
async def validate_all_tokens():
    """Validate all registered tokens."""
    return _get_tm().validate_all()


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ROUTES
# ══════════════════════════════════════════════════════════════════════════════

workflow_router = APIRouter(prefix="/workflows", tags=["workflows"])


class OrderRequestDTO(BaseModel):
    symbol:        str
    exchange:      str = "auto"
    side:          Literal["buy", "sell"]
    quantity:      float
    order_type:    str = "market"
    limit_price:   Optional[float] = None
    stop_price:    Optional[float] = None
    leverage:      int   = 1
    reduce_only:   bool  = False
    strategy_name: Optional[str] = None


@workflow_router.post("/buy")
async def execute_buy(req: OrderRequestDTO):
    """Execute a buy order through the full workflow pipeline."""
    from alchemy.workflows.engine import OrderWorkflowEngine
    from alchemy.workflows.states import OrderRequest, OrderSide, OrderType
    try:
        engine  = OrderWorkflowEngine()
        request = OrderRequest(
            symbol=req.symbol, exchange=req.exchange,
            side=OrderSide.BUY, quantity=req.quantity,
            order_type=OrderType(req.order_type),
            limit_price=req.limit_price, stop_price=req.stop_price,
            leverage=req.leverage, reduce_only=req.reduce_only,
            strategy_name=req.strategy_name,
        )
        result = await engine.execute(request)
        return result.to_summary()
    except Exception as e:
        raise HTTPException(500, str(e))


@workflow_router.post("/sell")
async def execute_sell(req: OrderRequestDTO):
    """Execute a sell order through the full workflow pipeline."""
    from alchemy.workflows.engine import OrderWorkflowEngine
    from alchemy.workflows.states import OrderRequest, OrderSide, OrderType
    try:
        engine  = OrderWorkflowEngine()
        request = OrderRequest(
            symbol=req.symbol, exchange=req.exchange,
            side=OrderSide.SELL, quantity=req.quantity,
            order_type=OrderType(req.order_type),
            limit_price=req.limit_price, stop_price=req.stop_price,
            leverage=req.leverage, reduce_only=req.reduce_only,
        )
        result = await engine.execute(request)
        return result.to_summary()
    except Exception as e:
        raise HTTPException(500, str(e))


@workflow_router.get("/history")
async def workflow_history(limit: int = 50):
    """Return recent workflow execution history."""
    from alchemy.workflows.engine import OrderWorkflowEngine
    engine = OrderWorkflowEngine()
    return engine.get_history(limit)


@workflow_router.get("/states")
async def workflow_states():
    """Return the workflow state machine definition."""
    from alchemy.workflows.states import TRANSITIONS, WorkflowStatus, TERMINAL_STATES
    return {
        "states": [s.value for s in WorkflowStatus],
        "terminal_states": [s.value for s in TERMINAL_STATES],
        "transitions": {
            k.value: [v.value for v in vs]
            for k, vs in TRANSITIONS.items()
        },
    }


@workflow_router.get("/route-preview")
async def route_preview(symbol: str, exchange: str = "auto", side: str = "buy", quantity: float = 1.0):
    """Preview which exchange an order would be routed to (no execution)."""
    from alchemy.workflows.smart_router import SmartRouter
    from alchemy.workflows.states import OrderRequest, OrderSide, OrderType
    from alchemy.tokens.manager import get_token_manager
    try:
        router   = SmartRouter(get_token_manager())
        decision = await router.route(OrderRequest(
            symbol=symbol, exchange=exchange,
            side=OrderSide(side), quantity=quantity,
            order_type=OrderType.MARKET,
        ))
        return {
            "exchange":     decision.exchange,
            "reason":       decision.reason,
            "fee_estimate": decision.fee_estimate,
            "alternatives": decision.alternatives,
            "score":        decision.score,
        }
    except Exception as e:
        raise HTTPException(400, str(e))
