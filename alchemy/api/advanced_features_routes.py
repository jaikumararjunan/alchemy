"""
alchemy.api.advanced_features_routes
========================================
Advanced platform features API.

Arbitrage:
  GET  /api/arbitrage/scan         — Scan cross-exchange price diffs
  GET  /api/arbitrage/prices       — Current multi-exchange prices

Leaderboard:
  GET  /api/leaderboard            — Global ranking
  GET  /api/leaderboard/profile    — My profile
  PUT  /api/leaderboard/profile    — Update profile
  GET  /api/leaderboard/profile/:slug — Public profile by slug
  GET  /api/leaderboard/achievements  — My achievements

Reports:
  GET  /api/reports/pdf            — Download portfolio PDF report
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(tags=["advanced"])


# ── Arbitrage ─────────────────────────────────────────────────────────────────

@router.get("/arbitrage/scan")
async def arbitrage_scan(
    symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT", description="Comma-separated symbols"),
    min_spread: float = Query(0.05, description="Minimum spread % to report"),
    user: CurrentUser = Depends(get_current_user),
):
    """Scan for cross-exchange arbitrage opportunities."""
    from alchemy.services.arbitrage_scanner import scan_arbitrage
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    return await scan_arbitrage(sym_list, min_spread)


@router.get("/arbitrage/prices")
async def multi_exchange_prices(
    symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT", description="Comma-separated symbols"),
    user: CurrentUser = Depends(get_current_user),
):
    """Get current prices from all exchanges for comparison."""
    from alchemy.services.arbitrage_scanner import scan_arbitrage
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    result = await scan_arbitrage(sym_list, min_spread_pct=0)
    return {"prices": result["prices"], "exchanges": result["exchanges_reached"]}


# ── Leaderboard ───────────────────────────────────────────────────────────────

@router.get("/leaderboard")
async def get_leaderboard(
    sort_by: str = Query("return", description="Sort: return, pnl, win_rate, trades, profit_factor"),
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """Get global trading leaderboard."""
    from alchemy.services.leaderboard import build_leaderboard
    return {"leaderboard": build_leaderboard(sort_by, limit)}


@router.get("/leaderboard/profile")
async def my_profile(user: CurrentUser = Depends(get_current_user)):
    """Get my trader profile."""
    from alchemy.services.leaderboard import get_or_create_profile, get_user_achievements
    profile = get_or_create_profile(user.user_id, getattr(user, 'username', 'Trader'))
    achievements = get_user_achievements(user.user_id)
    return {"profile": profile, "achievements": achievements}


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    is_public: Optional[bool] = None
    bio: Optional[str] = None
    avatar_color: Optional[str] = None


@router.put("/leaderboard/profile")
async def update_my_profile(req: ProfileUpdateRequest,
                              user: CurrentUser = Depends(get_current_user)):
    """Update my trader profile."""
    from alchemy.services.leaderboard import update_profile
    profile = update_profile(
        user.user_id,
        display_name=req.display_name,
        is_public=req.is_public,
        bio=req.bio,
        avatar_color=req.avatar_color,
    )
    return {"ok": True, "profile": profile}


@router.get("/leaderboard/profile/{slug}")
async def public_profile(slug: str):
    """Get a public trader profile by slug (no auth required)."""
    from alchemy.services.leaderboard import get_public_profile, get_user_achievements
    profile = get_public_profile(slug)
    if not profile:
        raise HTTPException(404, "Profile not found or not public")

    achievements = get_user_achievements(profile["user_id"])
    # Remove sensitive fields
    profile.pop("user_id", None)
    return {"profile": profile, "achievements": achievements}


@router.get("/leaderboard/achievements")
async def my_achievements(user: CurrentUser = Depends(get_current_user)):
    """Get my achievement badges."""
    from alchemy.services.leaderboard import get_user_achievements, check_achievements, BADGES
    from alchemy.paper_trading.engine import get_paper_engine

    engine = get_paper_engine()
    p = engine.get_portfolio(user.user_id)

    # Check for new achievements
    newly_earned = check_achievements(
        user.user_id, p.trade_log, p.portfolio_value, p.starting_balance
    )

    all_achievements = get_user_achievements(user.user_id)
    all_badges = {k: {**v, "earned": False} for k, v in BADGES.items()}
    for a in all_achievements:
        if a["badge_id"] in all_badges:
            all_badges[a["badge_id"]]["earned"] = True
            all_badges[a["badge_id"]]["earned_at"] = a.get("earned_at", "")

    return {
        "earned": all_achievements,
        "earned_count": len(all_achievements),
        "total_badges": len(BADGES),
        "newly_earned": newly_earned,
        "all_badges": all_badges,
    }


# ── PDF Report ────────────────────────────────────────────────────────────────

@router.get("/reports/pdf")
async def download_pdf_report(user: CurrentUser = Depends(get_current_user)):
    """Download portfolio report as PDF."""
    from alchemy.services.pdf_report import generate_portfolio_pdf
    username = getattr(user, 'username', getattr(user, 'email', 'Trader'))
    pdf_bytes = generate_portfolio_pdf(user.user_id, username)

    filename = f"alchemy_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
