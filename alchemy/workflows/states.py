"""
alchemy.workflows.states
=========================
State schema and models for the buy/sell order workflow.

Order lifecycle state machine:

  PENDING ──► SIGNAL_VALIDATED ──► RISK_CHECKED ──► TOKEN_VERIFIED
                                                          │
                                          ┌───────────────┘
                                          ▼
                                      ROUTED ──► PLACED ──► MONITORING
                                                                 │
                                          ┌──────────────────────┤
                                          ▼                      ▼
                                       FILLED               REJECTED
                                          │                      │
                                          └──────────┬───────────┘
                                                     ▼
                                                  SETTLED
                                  (also: CANCELLED at any pre-PLACED state)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET      = "market"
    LIMIT       = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT  = "stop_limit"


class WorkflowStatus(str, Enum):
    PENDING           = "pending"
    SIGNAL_VALIDATED  = "signal_validated"
    RISK_CHECKED      = "risk_checked"
    TOKEN_VERIFIED    = "token_verified"
    ROUTED            = "routed"
    PLACED            = "placed"
    MONITORING        = "monitoring"
    FILLED            = "filled"
    PARTIALLY_FILLED  = "partially_filled"
    REJECTED          = "rejected"
    CANCELLED         = "cancelled"
    SETTLED           = "settled"
    ERROR             = "error"


TERMINAL_STATES = {
    WorkflowStatus.FILLED,
    WorkflowStatus.REJECTED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.SETTLED,
    WorkflowStatus.ERROR,
}

# Allowed state transitions
TRANSITIONS: dict[WorkflowStatus, list[WorkflowStatus]] = {
    WorkflowStatus.PENDING:          [WorkflowStatus.SIGNAL_VALIDATED, WorkflowStatus.CANCELLED, WorkflowStatus.ERROR],
    WorkflowStatus.SIGNAL_VALIDATED: [WorkflowStatus.RISK_CHECKED,     WorkflowStatus.CANCELLED, WorkflowStatus.ERROR],
    WorkflowStatus.RISK_CHECKED:     [WorkflowStatus.TOKEN_VERIFIED,   WorkflowStatus.CANCELLED, WorkflowStatus.ERROR],
    WorkflowStatus.TOKEN_VERIFIED:   [WorkflowStatus.ROUTED,           WorkflowStatus.CANCELLED, WorkflowStatus.ERROR],
    WorkflowStatus.ROUTED:           [WorkflowStatus.PLACED,           WorkflowStatus.CANCELLED, WorkflowStatus.ERROR],
    WorkflowStatus.PLACED:           [WorkflowStatus.MONITORING,       WorkflowStatus.REJECTED,  WorkflowStatus.ERROR],
    WorkflowStatus.MONITORING:       [WorkflowStatus.FILLED, WorkflowStatus.PARTIALLY_FILLED,
                                      WorkflowStatus.REJECTED, WorkflowStatus.CANCELLED],
    WorkflowStatus.FILLED:           [WorkflowStatus.SETTLED],
    WorkflowStatus.PARTIALLY_FILLED: [WorkflowStatus.FILLED, WorkflowStatus.CANCELLED],
    WorkflowStatus.REJECTED:         [WorkflowStatus.SETTLED],
    WorkflowStatus.CANCELLED:        [WorkflowStatus.SETTLED],
    WorkflowStatus.SETTLED:          [],
    WorkflowStatus.ERROR:            [WorkflowStatus.PENDING],  # Allow retry
}


class OrderRequest(BaseModel):
    """Input order request — what the user or AI agent wants to do."""
    symbol:        str
    exchange:      str                    # kite | delta | binance | ib
    side:          OrderSide
    quantity:      float
    order_type:    OrderType              = OrderType.MARKET
    limit_price:   Optional[float]        = None
    stop_price:    Optional[float]        = None
    leverage:      int                    = 1
    reduce_only:   bool                   = False
    strategy_name: Optional[str]          = None
    signal_run_id: Optional[str]          = None   # Links to AI signal
    metadata:      dict[str, Any]         = Field(default_factory=dict)


class OrderResult(BaseModel):
    """Execution result from the exchange."""
    order_id:      Optional[str]  = None
    exchange_order_id: Optional[str] = None
    status:        str            = "pending"
    filled_qty:    float          = 0.0
    avg_fill_price:Optional[float]= None
    fees:          float          = 0.0
    timestamp:     Optional[datetime] = None
    raw_response:  dict           = Field(default_factory=dict)


class WorkflowStep(BaseModel):
    """Audit record for one workflow step."""
    status:    WorkflowStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message:   str      = ""
    data:      dict     = Field(default_factory=dict)


class OrderWorkflowState(BaseModel):
    """
    Complete state of one order workflow run.
    This is the LangGraph state schema — flows through all nodes.
    """

    # Identity
    workflow_id:   str
    request:       OrderRequest
    status:        WorkflowStatus = WorkflowStatus.PENDING
    created_at:    datetime       = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:    datetime       = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Stage outputs
    signal_valid:     Optional[bool]       = None
    signal_errors:    list[str]            = Field(default_factory=list)

    risk_approved:    Optional[bool]       = None
    risk_veto_reason: Optional[str]        = None
    adjusted_qty:     Optional[float]      = None

    token_valid:      Optional[bool]       = None
    token_exchange:   Optional[str]        = None

    routed_to:        Optional[str]        = None  # Final exchange chosen
    routing_reason:   Optional[str]        = None

    order_result:     Optional[OrderResult] = None
    fill_price:       Optional[float]       = None
    fill_quantity:    Optional[float]       = None
    pnl:              Optional[float]       = None

    # Audit trail
    steps:     list[WorkflowStep] = Field(default_factory=list)
    errors:    list[str]          = Field(default_factory=list)
    warnings:  list[str]          = Field(default_factory=list)

    # Control
    retry_count:  int  = 0
    max_retries:  int  = 2
    cancelled_by: Optional[str] = None   # "user" | "risk" | "token" | "system"

    def transition(self, new_status: WorkflowStatus, message: str = "", data: dict | None = None) -> None:
        """Apply a state transition with validation."""
        allowed = TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        self.steps.append(WorkflowStep(status=new_status, message=message, data=data or {}))
        self.status     = new_status
        self.updated_at = datetime.now(timezone.utc)

    def add_error(self, msg: str) -> None:
        self.errors.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    @property
    def duration_ms(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds() * 1000

    def to_summary(self) -> dict:
        return {
            "workflow_id":  self.workflow_id,
            "symbol":       self.request.symbol,
            "exchange":     self.request.exchange,
            "side":         self.request.side.value,
            "quantity":     self.request.quantity,
            "status":       self.status.value,
            "routed_to":    self.routed_to,
            "fill_price":   self.fill_price,
            "fill_quantity":self.fill_quantity,
            "pnl":          self.pnl,
            "duration_ms":  round(self.duration_ms, 1),
            "steps":        [{"status": s.status.value, "msg": s.message} for s in self.steps],
            "errors":       self.errors,
        }
