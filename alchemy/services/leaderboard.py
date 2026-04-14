"""
alchemy.services.leaderboard
================================
Public leaderboard with shareable trader profiles.

Features:
  - Global ranking by total return, win rate, profit factor
  - Trader profiles with anonymized stats
  - Shareable profile links
  - Weekly/monthly leaderboard snapshots
  - Achievement badges system
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
log = structlog.get_logger(__name__)

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS trader_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT DEFAULT 'Anonymous',
        profile_slug TEXT UNIQUE,
        is_public INTEGER DEFAULT 0,
        bio TEXT DEFAULT '',
        avatar_color TEXT DEFAULT '#3B82F6',
        achievements TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        badge_id TEXT NOT NULL,
        earned_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, badge_id)
    )""")
    return c


# ── Achievement Badges ────────────────────────────────────────────────────────

BADGES = {
    "first_trade":    {"name": "First Trade",     "icon": "🎯", "desc": "Placed your first trade"},
    "10_trades":      {"name": "Getting Started",  "icon": "📈", "desc": "Completed 10 trades"},
    "50_trades":      {"name": "Active Trader",    "icon": "🔥", "desc": "Completed 50 trades"},
    "100_trades":     {"name": "Centurion",        "icon": "💯", "desc": "Completed 100 trades"},
    "first_profit":   {"name": "First Profit",     "icon": "💰", "desc": "Closed first profitable trade"},
    "1k_profit":      {"name": "$1K Club",         "icon": "🏆", "desc": "Earned $1,000 in total profit"},
    "5k_profit":      {"name": "$5K Club",         "icon": "👑", "desc": "Earned $5,000 in total profit"},
    "win_streak_5":   {"name": "Hot Streak",       "icon": "🔥", "desc": "5 consecutive winning trades"},
    "win_streak_10":  {"name": "Unstoppable",      "icon": "⚡", "desc": "10 consecutive winning trades"},
    "win_rate_60":    {"name": "Sharp Shooter",    "icon": "🎯", "desc": "Achieved 60%+ win rate (min 20 trades)"},
    "win_rate_70":    {"name": "Elite Trader",     "icon": "💎", "desc": "Achieved 70%+ win rate (min 50 trades)"},
    "multi_symbol":   {"name": "Diversified",      "icon": "🌐", "desc": "Traded 5+ different symbols"},
    "night_owl":      {"name": "Night Owl",        "icon": "🦉", "desc": "Placed a trade between midnight and 4 AM"},
    "comeback":       {"name": "Comeback Kid",     "icon": "🔄", "desc": "Recovered from 5%+ drawdown to new high"},
}


def check_achievements(user_id: str, trade_log: list[dict], portfolio_value: float,
                        starting_balance: float, max_streak: int = 0) -> list[str]:
    """Check and award achievements. Returns list of newly earned badge IDs."""
    newly_earned = []
    total = len(trade_log)
    wins = len([t for t in trade_log if t.get("net_pnl", 0) > 0])
    total_profit = sum(t.get("net_pnl", 0) for t in trade_log if t.get("net_pnl", 0) > 0)
    symbols = set(t.get("symbol", "") for t in trade_log)
    win_rate = (wins / total * 100) if total else 0

    checks = {
        "first_trade": total >= 1,
        "10_trades": total >= 10,
        "50_trades": total >= 50,
        "100_trades": total >= 100,
        "first_profit": any(t.get("net_pnl", 0) > 0 for t in trade_log),
        "1k_profit": total_profit >= 1000,
        "5k_profit": total_profit >= 5000,
        "win_streak_5": max_streak >= 5,
        "win_streak_10": max_streak >= 10,
        "win_rate_60": win_rate >= 60 and total >= 20,
        "win_rate_70": win_rate >= 70 and total >= 50,
        "multi_symbol": len(symbols) >= 5,
    }

    with _conn() as c:
        for badge_id, earned in checks.items():
            if earned:
                try:
                    c.execute("INSERT OR IGNORE INTO achievements (user_id, badge_id) VALUES (?,?)",
                              (user_id, badge_id))
                    if c.execute("SELECT changes()").fetchone()[0] > 0:
                        newly_earned.append(badge_id)
                except Exception:
                    pass

    return newly_earned


def get_user_achievements(user_id: str) -> list[dict]:
    """Get all achievements for a user."""
    with _conn() as c:
        rows = c.execute("SELECT badge_id, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at",
                         (user_id,)).fetchall()
    return [{"badge_id": r["badge_id"], "earned_at": r["earned_at"], **BADGES.get(r["badge_id"], {})} for r in rows]


# ── Profiles ──────────────────────────────────────────────────────────────────

def _slug(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def get_or_create_profile(user_id: str, display_name: str = "Anonymous") -> dict:
    """Get or create a trader profile."""
    with _conn() as c:
        row = c.execute("SELECT * FROM trader_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            slug = _slug(user_id)
            c.execute("INSERT INTO trader_profiles (user_id, display_name, profile_slug) VALUES (?,?,?)",
                      (user_id, display_name, slug))
            row = c.execute("SELECT * FROM trader_profiles WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else {}


def get_public_profile(slug: str) -> dict | None:
    """Get a public profile by slug."""
    with _conn() as c:
        row = c.execute("SELECT * FROM trader_profiles WHERE profile_slug=? AND is_public=1",
                        (slug,)).fetchone()
    return dict(row) if row else None


def update_profile(user_id: str, display_name: str = None, is_public: bool = None,
                    bio: str = None, avatar_color: str = None) -> dict:
    """Update profile settings."""
    with _conn() as c:
        if display_name is not None:
            c.execute("UPDATE trader_profiles SET display_name=?, updated_at=datetime('now') WHERE user_id=?",
                      (display_name, user_id))
        if is_public is not None:
            c.execute("UPDATE trader_profiles SET is_public=?, updated_at=datetime('now') WHERE user_id=?",
                      (1 if is_public else 0, user_id))
        if bio is not None:
            c.execute("UPDATE trader_profiles SET bio=?, updated_at=datetime('now') WHERE user_id=?",
                      (bio[:500], user_id))
        if avatar_color is not None:
            c.execute("UPDATE trader_profiles SET avatar_color=?, updated_at=datetime('now') WHERE user_id=?",
                      (avatar_color, user_id))
    return get_or_create_profile(user_id)


# ── Leaderboard ───────────────────────────────────────────────────────────────

def build_leaderboard(sort_by: str = "return", limit: int = 20) -> list[dict]:
    """Build global leaderboard from all paper trading portfolios."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()

    board = []
    for uid, p in engine._portfolios.items():
        wins = len([t for t in p.trade_log if t.get("net_pnl", 0) > 0])
        total = len(p.trade_log)
        total_profit = sum(t.get("net_pnl", 0) for t in p.trade_log if t.get("net_pnl", 0) > 0)
        total_loss = abs(sum(t.get("net_pnl", 0) for t in p.trade_log if t.get("net_pnl", 0) < 0))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf')

        profile = get_or_create_profile(uid)
        achievements = get_user_achievements(uid)

        board.append({
            "user_id": uid[:8] + "...",
            "display_name": profile.get("display_name", "Anonymous"),
            "profile_slug": profile.get("profile_slug", ""),
            "avatar_color": profile.get("avatar_color", "#3B82F6"),
            "is_public": bool(profile.get("is_public", 0)),
            "portfolio_value": round(p.portfolio_value, 2),
            "total_return_pct": round(p.total_return_pct, 2),
            "realized_pnl": round(p.realized_pnl, 2),
            "total_trades": total,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "profit_factor": round(min(profit_factor, 99.99), 2),
            "achievement_count": len(achievements),
            "badges": [a["icon"] for a in achievements[:5]],
        })

    # Sort
    sort_keys = {
        "return": lambda x: x["total_return_pct"],
        "pnl": lambda x: x["realized_pnl"],
        "win_rate": lambda x: x["win_rate"],
        "trades": lambda x: x["total_trades"],
        "profit_factor": lambda x: x["profit_factor"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["return"])
    board.sort(key=key_fn, reverse=True)

    # Assign ranks
    for i, entry in enumerate(board[:limit]):
        entry["rank"] = i + 1

    return board[:limit]
