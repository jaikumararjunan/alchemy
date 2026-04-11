"""
alchemy.api.capital_routes
=============================
REST API for capital allocation and multi-strategy management.

Fund Management:
  GET  /api/capital/fund              — Get your fund overview
  POST /api/capital/fund/setup        — Create/reset fund with total capital
  POST /api/capital/fund/template     — Apply a preset allocation template

Bucket Management:
  POST /api/capital/bucket            — Add allocation bucket
  PUT  /api/capital/bucket/{id}       — Update bucket settings
  DEL  /api/capital/bucket/{id}       — Remove bucket

Trading:
  POST /api/capital/bucket/{id}/trade — Record trade in a bucket

Rebalancing:
  GET  /api/capital/rebalance/check   — Check if rebalancing needed
  POST /api/capital/rebalance         — Execute rebalance

Reference:
  GET  /api/capital/risk-presets      — Available risk level presets
  GET  /api/capital/templates         — Available allocation templates
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alchemy.auth.middleware import CurrentUser, get_current_user

router = APIRouter(prefix="/capital", tags=["capital-allocation"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SetupFundRequest(BaseModel):
    total_capital: float = Field(100000, gt=0, description="Total capital to manage")
    allocation_method: str = Field("manual", description="manual, equal_weight, risk_parity, kelly")


class AddBucketRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Bucket name (e.g., 'Trend Following')")
    allocation_pct: float = Field(..., gt=0, le=100, description="% of fund to allocate")
    strategy: str = Field("manual", description="Strategy: sma_crossover, rsi_mean_reversion, bollinger_band, combined_sma_rsi, cash, manual")
    symbols: list[str] = Field(default_factory=list, description="Symbols to trade (e.g., ['BTCUSDT', 'ETHUSDT'])")
    risk_level: str = Field("moderate", description="conservative, moderate, aggressive, ultra")
    parent_id: Optional[str] = Field(None, description="Parent bucket ID for nesting (multi-level)")
    auto_trade: bool = Field(False, description="Auto-execute strategy signals")
    notes: str = Field("", description="Notes about this allocation")


class UpdateBucketRequest(BaseModel):
    name: Optional[str] = None
    allocation_pct: Optional[float] = None
    strategy: Optional[str] = None
    symbols: Optional[list[str]] = None
    risk_level: Optional[str] = None
    auto_trade: Optional[bool] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class RecordTradeRequest(BaseModel):
    symbol: str
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(..., gt=0)
    fee: float = Field(0, ge=0)


class ApplyTemplateRequest(BaseModel):
    template: str = Field(..., description="conservative, balanced, aggressive, crypto_diversified")
    total_capital: float = Field(100000, gt=0)


# ── Fund Endpoints ────────────────────────────────────────────────────────────

@router.get("/fund")
async def get_fund(user: CurrentUser = Depends(get_current_user)):
    """
    Get your capital fund overview.

    Shows total capital, allocation tree, per-bucket P&L, and rebalance status.
    Each bucket shows: allocated capital, current value, strategy, risk level,
    win rate, and drift from target allocation.
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    return get_capital_engine().get_fund(user.user_id).summary()


@router.post("/fund/setup")
async def setup_fund(
    body: SetupFundRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Create or reset your capital fund.

    Sets the total capital pool that will be divided among strategy buckets.
    Existing buckets are cleared. Use /capital/bucket to add allocations.
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    fund = get_capital_engine().setup_fund(
        user.user_id, body.total_capital, body.allocation_method,
    )
    return {
        "ok": True,
        "message": f"Fund created with ${body.total_capital:,.2f} total capital",
        "fund": fund.summary(),
    }


@router.post("/fund/template")
async def apply_template(
    body: ApplyTemplateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Apply a preset allocation template.

    Templates:
    - **conservative**: 30% Blue Chip, 30% Stablecoin, 20% Index, 20% Cash
    - **balanced**: 35% Trend, 25% Mean Reversion, 20% Volatility, 20% Cash
    - **aggressive**: 30% Momentum, 25% Breakout, 25% Combined, 15% High Risk, 5% Cash
    - **crypto_diversified**: 40% BTC, 25% ETH, 20% Alts, 15% Stablecoin
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    try:
        fund = get_capital_engine().apply_template(
            user.user_id, body.template, body.total_capital,
        )
        return {
            "ok": True,
            "message": f"Applied '{body.template}' template with ${body.total_capital:,.2f}",
            "fund": fund.summary(),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Bucket Endpoints ──────────────────────────────────────────────────────────

@router.post("/bucket")
async def add_bucket(
    body: AddBucketRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Add a new capital allocation bucket.

    Each bucket gets a slice of your total capital, assigned to a strategy.
    Buckets can be nested (multi-level) by setting parent_id.

    Example: Add 40% to Trend Following with BTC and ETH:
    ```
    {"name": "Trend Following", "allocation_pct": 40,
     "strategy": "sma_crossover", "symbols": ["BTCUSDT", "ETHUSDT"],
     "risk_level": "moderate"}
    ```
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    try:
        bucket = get_capital_engine().add_bucket(
            user_id=user.user_id,
            name=body.name,
            allocation_pct=body.allocation_pct,
            strategy=body.strategy,
            symbols=body.symbols,
            risk_level=body.risk_level,
            parent_id=body.parent_id,
            auto_trade=body.auto_trade,
            notes=body.notes,
        )
        return {
            "ok": True,
            "message": f"Added '{body.name}' — {body.allocation_pct}% = ${bucket.allocated_capital:,.2f}",
            "bucket": bucket.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/bucket/{bucket_id}")
async def update_bucket(
    bucket_id: str,
    body: UpdateBucketRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update a bucket's settings (strategy, risk level, allocation, etc.)."""
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        bucket = get_capital_engine().update_bucket(user.user_id, bucket_id, **updates)
        return {"ok": True, "bucket": bucket.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/bucket/{bucket_id}")
async def remove_bucket(
    bucket_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Remove a bucket and return its capital to unallocated pool."""
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    ok = get_capital_engine().remove_bucket(user.user_id, bucket_id)
    if not ok:
        raise HTTPException(404, "Bucket not found")
    return {"ok": True, "message": "Bucket removed, capital returned to pool"}


# ── Trading in Buckets ────────────────────────────────────────────────────────

@router.post("/bucket/{bucket_id}/trade")
async def record_bucket_trade(
    bucket_id: str,
    body: RecordTradeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Record a completed trade within a specific bucket.

    Updates the bucket's P&L, win rate, and drawdown tracking.
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    try:
        trade = get_capital_engine().record_trade(
            user_id=user.user_id,
            bucket_id=bucket_id,
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
            entry_price=body.entry_price,
            exit_price=body.exit_price,
            fee=body.fee,
        )
        return {"ok": True, "trade": trade}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Rebalancing ───────────────────────────────────────────────────────────────

@router.get("/rebalance/check")
async def check_rebalance(user: CurrentUser = Depends(get_current_user)):
    """
    Check if any buckets have drifted beyond their rebalance threshold.

    Returns alerts with exactly how much to add or remove from each bucket.
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    return get_capital_engine().check_rebalance(user.user_id)


@router.post("/rebalance")
async def rebalance(user: CurrentUser = Depends(get_current_user)):
    """
    Execute rebalancing — reset all buckets to their target allocation percentages.

    This redistributes capital proportionally. Positions within buckets are not
    affected — only cash balances are adjusted.
    """
    from alchemy.paper_trading.capital_allocator import get_capital_engine
    return get_capital_engine().rebalance(user.user_id)


# ── Reference ─────────────────────────────────────────────────────────────────

@router.get("/risk-presets")
async def get_risk_presets(user: CurrentUser = Depends(get_current_user)):
    """Get all available risk level presets with their settings."""
    from alchemy.paper_trading.capital_allocator import RISK_PRESETS, RiskLevel
    return {
        level.value: preset
        for level, preset in RISK_PRESETS.items()
    }


@router.get("/templates")
async def get_templates(user: CurrentUser = Depends(get_current_user)):
    """Get all available allocation templates."""
    return {
        "templates": {
            "conservative": {
                "name": "Conservative",
                "description": "Capital preservation focus. 50% low-risk, 20% moderate, 20% cash reserve.",
                "risk": "Low",
                "buckets": ["Blue Chip Crypto (30%)", "Stablecoin Yield (30%)", "Index Follow (20%)", "Cash Reserve (20%)"],
            },
            "balanced": {
                "name": "Balanced",
                "description": "Mix of trend following and mean reversion. 35% trend, 25% reversion, 20% volatility plays.",
                "risk": "Medium",
                "buckets": ["Trend Following (35%)", "Mean Reversion (25%)", "Volatility Play (20%)", "Cash Reserve (20%)"],
            },
            "aggressive": {
                "name": "Aggressive",
                "description": "High growth focus. Multiple momentum strategies. Only 5% cash reserve.",
                "risk": "High",
                "buckets": ["Momentum (30%)", "Breakout (25%)", "Combined Signals (25%)", "High Risk Alpha (15%)", "Emergency Cash (5%)"],
            },
            "crypto_diversified": {
                "name": "Crypto Diversified",
                "description": "Crypto-focused with BTC core position. Diversified across market cap tiers.",
                "risk": "Medium-High",
                "buckets": ["BTC Core (40%)", "ETH Growth (25%)", "Alt Rotation (20%)", "Stablecoin Buffer (15%)"],
            },
        }
    }
