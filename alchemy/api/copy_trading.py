"""
alchemy.api.copy_trading
==========================
Social copy trading — follow top traders, auto-mirror trades.
"""
from __future__ import annotations

import json
import sqlite3
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/social", tags=["social"])

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS copy_follows (
        follower_id TEXT NOT NULL,
        leader_id TEXT NOT NULL,
        allocation_pct REAL DEFAULT 10.0,
        max_position_pct REAL DEFAULT 5.0,
        enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (follower_id, leader_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS copy_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower_id TEXT NOT NULL,
        leader_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL DEFAULT 0,
        price REAL DEFAULT 0,
        pnl REAL DEFAULT 0,
        status TEXT DEFAULT 'filled',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS social_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        content TEXT NOT NULL,
        trade_ref TEXT DEFAULT '',
        likes INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    return c


class FollowRequest(BaseModel):
    leader_id: str
    allocation_pct: float = 10.0
    max_position_pct: float = 5.0


class PostRequest(BaseModel):
    content: str
    trade_ref: str = ""


# ── Copy Trading ──────────────────────────────────────────────────────────────

@router.post("/follow")
async def follow_trader(req: FollowRequest, user: CurrentUser = Depends(get_current_user)):
    """Follow a trader to auto-copy their trades."""
    if req.leader_id == user.user_id:
        raise HTTPException(400, "Cannot follow yourself")
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO copy_follows
            (follower_id, leader_id, allocation_pct, max_position_pct)
            VALUES (?,?,?,?)""",
            (user.user_id, req.leader_id, req.allocation_pct, req.max_position_pct))
    return {"ok": True, "message": f"Following trader. Allocating {req.allocation_pct}% of capital."}


@router.delete("/follow/{leader_id}")
async def unfollow_trader(leader_id: str, user: CurrentUser = Depends(get_current_user)):
    """Stop following a trader."""
    with _conn() as c:
        c.execute("DELETE FROM copy_follows WHERE follower_id=? AND leader_id=?",
                  (user.user_id, leader_id))
    return {"ok": True}


@router.get("/following")
async def get_following(user: CurrentUser = Depends(get_current_user)):
    """List traders you're following."""
    with _conn() as c:
        rows = c.execute("""SELECT cf.*, 
            (SELECT COUNT(*) FROM copy_trades WHERE follower_id=cf.follower_id AND leader_id=cf.leader_id) as trade_count,
            (SELECT COALESCE(SUM(pnl),0) FROM copy_trades WHERE follower_id=cf.follower_id AND leader_id=cf.leader_id) as total_pnl
            FROM copy_follows cf WHERE cf.follower_id=?""",
            (user.user_id,)).fetchall()
    return {"following": [dict(r) for r in rows]}


@router.get("/followers")
async def get_followers(user: CurrentUser = Depends(get_current_user)):
    """List traders following you."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM copy_follows WHERE leader_id=?",
                         (user.user_id,)).fetchall()
    return {"followers": [dict(r) for r in rows], "count": len(rows)}


@router.get("/copy-history")
async def copy_trade_history(user: CurrentUser = Depends(get_current_user)):
    """Get history of copied trades."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM copy_trades WHERE follower_id=? ORDER BY created_at DESC LIMIT 100",
            (user.user_id,)).fetchall()
    return {"trades": [dict(r) for r in rows]}


@router.get("/leaderboard")
async def social_leaderboard():
    """Public leaderboard with follow counts."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    board = []

    with _conn() as c:
        for uid, portfolio in engine._portfolios.items():
            followers = c.execute("SELECT COUNT(*) FROM copy_follows WHERE leader_id=?",
                                  (uid,)).fetchone()[0]
            s = portfolio.summary()
            board.append({
                "user_id": uid[:8] + "***",
                "portfolio_value": s["portfolio_value"],
                "total_return_pct": s["total_return_pct"],
                "realized_pnl": s["realized_pnl"],
                "win_rate": s["win_rate"],
                "total_trades": s["total_trades"],
                "followers": followers,
            })

    board.sort(key=lambda x: x["total_return_pct"], reverse=True)
    return {"leaderboard": board[:20]}


# ── Social Feed ───────────────────────────────────────────────────────────────

@router.get("/feed")
async def get_feed(limit: int = Query(20, ge=1, le=100),
                    user: CurrentUser = Depends(get_current_user)):
    """Get social feed — posts from followed traders + own posts."""
    with _conn() as c:
        following_ids = [r[0] for r in c.execute(
            "SELECT leader_id FROM copy_follows WHERE follower_id=?",
            (user.user_id,)).fetchall()]
        following_ids.append(user.user_id)

        placeholders = ",".join("?" * len(following_ids))
        rows = c.execute(
            f"SELECT * FROM social_posts WHERE user_id IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
            (*following_ids, limit)).fetchall()
    return {"posts": [dict(r) for r in rows]}


@router.post("/post")
async def create_post(req: PostRequest, user: CurrentUser = Depends(get_current_user)):
    """Create a social post."""
    if not req.content.strip():
        raise HTTPException(400, "Content required")
    with _conn() as c:
        c.execute("INSERT INTO social_posts (user_id, content, trade_ref) VALUES (?,?,?)",
                  (user.user_id, req.content[:500], req.trade_ref))
        post_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "id": post_id}


@router.post("/post/{post_id}/like")
async def like_post(post_id: int, user: CurrentUser = Depends(get_current_user)):
    """Like a post."""
    with _conn() as c:
        c.execute("UPDATE social_posts SET likes=likes+1 WHERE id=?", (post_id,))
    return {"ok": True}


# ── Copy Trade Execution (called from paper engine) ───────────────────────────

def execute_copy_trades(leader_id: str, symbol: str, side: str,
                          quantity: float, price: float):
    """Mirror a trade to all followers of this leader."""
    with _conn() as c:
        followers = c.execute(
            "SELECT * FROM copy_follows WHERE leader_id=? AND enabled=1",
            (leader_id,)).fetchall()

    if not followers:
        return

    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()

    for f in followers:
        f = dict(f)
        follower_id = f["follower_id"]
        alloc_pct = f["allocation_pct"]
        max_pos_pct = f["max_position_pct"]

        try:
            portfolio = engine.get_portfolio(follower_id)
            budget = portfolio.cash_balance * (alloc_pct / 100)
            copy_qty = round(budget / price, 6) if price > 0 else 0

            if copy_qty <= 0:
                continue

            # Cap at max position %
            pos_value = copy_qty * price
            max_value = portfolio.portfolio_value * (max_pos_pct / 100)
            if pos_value > max_value:
                copy_qty = round(max_value / price, 6)

            order = engine.place_order(
                user_id=follower_id, symbol=symbol, side=side,
                quantity=copy_qty, current_price=price,
                order_type="market", strategy=f"copy_{leader_id[:8]}",
                notes=f"Copied from {leader_id[:8]}",
            )

            with _conn() as c:
                c.execute("INSERT INTO copy_trades (follower_id, leader_id, symbol, side, quantity, price) VALUES (?,?,?,?,?,?)",
                          (follower_id, leader_id, symbol, side, copy_qty, price))

            log.info("copy.executed", follower=follower_id[:8], leader=leader_id[:8],
                     symbol=symbol, qty=copy_qty)

        except Exception as e:
            log.warning("copy.failed", follower=follower_id[:8], error=str(e))
