"""
alchemy.api.journal_routes
============================
Trade Journal — attach notes, tags, emotions, and analysis to trades.
"""
from __future__ import annotations

import json
import sqlite3
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from alchemy.auth.middleware import get_current_user, CurrentUser

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/journal", tags=["trade-journal"])

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn():
    c = sqlite3.connect(_DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS trade_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_price REAL DEFAULT 0,
        exit_price REAL DEFAULT 0,
        quantity REAL DEFAULT 0,
        pnl REAL DEFAULT 0,
        return_pct REAL DEFAULT 0,
        strategy TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',
        emotion TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        lessons TEXT DEFAULT '',
        rating INTEGER DEFAULT 0,
        screenshot_url TEXT DEFAULT '',
        trade_date TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_journal_user ON trade_journal(user_id)")
    return c


class JournalEntry(BaseModel):
    symbol: str
    side: str
    entry_price: float = 0
    exit_price: float = 0
    quantity: float = 0
    pnl: float = 0
    return_pct: float = 0
    strategy: str = ""
    tags: List[str] = []
    emotion: str = ""  # confident, fearful, greedy, neutral, disciplined
    notes: str = ""
    lessons: str = ""
    rating: int = 0  # 1-5 star self-rating
    trade_date: str = ""


class JournalUpdate(BaseModel):
    tags: Optional[List[str]] = None
    emotion: Optional[str] = None
    notes: Optional[str] = None
    lessons: Optional[str] = None
    rating: Optional[int] = None


@router.get("")
async def list_journal(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    symbol: str = Query("", description="Filter by symbol"),
    tag: str = Query("", description="Filter by tag"),
    emotion: str = Query("", description="Filter by emotion"),
    user: CurrentUser = Depends(get_current_user),
):
    """List trade journal entries with filters."""
    with _conn() as c:
        query = "SELECT * FROM trade_journal WHERE user_id=?"
        params = [user.user_id]

        if symbol:
            query += " AND symbol=?"
            params.append(symbol.upper())
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        if emotion:
            query += " AND emotion=?"
            params.append(emotion)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = c.execute(query, params).fetchall()
        total = c.execute("SELECT COUNT(*) FROM trade_journal WHERE user_id=?",
                          (user.user_id,)).fetchone()[0]

    entries = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags", "[]"))
        entries.append(d)

    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@router.post("")
async def create_journal_entry(entry: JournalEntry,
                                 user: CurrentUser = Depends(get_current_user)):
    """Create a new trade journal entry."""
    with _conn() as c:
        c.execute("""INSERT INTO trade_journal
            (user_id, symbol, side, entry_price, exit_price, quantity, pnl, return_pct,
             strategy, tags, emotion, notes, lessons, rating, trade_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user.user_id, entry.symbol.upper(), entry.side, entry.entry_price,
             entry.exit_price, entry.quantity, entry.pnl, entry.return_pct,
             entry.strategy, json.dumps(entry.tags), entry.emotion,
             entry.notes, entry.lessons, entry.rating,
             entry.trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        entry_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {"ok": True, "id": entry_id, "message": "Journal entry created"}


@router.patch("/{entry_id}")
async def update_journal_entry(entry_id: int, update: JournalUpdate,
                                 user: CurrentUser = Depends(get_current_user)):
    """Update a journal entry (notes, tags, emotion, rating)."""
    with _conn() as c:
        existing = c.execute("SELECT * FROM trade_journal WHERE id=? AND user_id=?",
                             (entry_id, user.user_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Entry not found")

        updates = []
        params = []
        if update.tags is not None:
            updates.append("tags=?"); params.append(json.dumps(update.tags))
        if update.emotion is not None:
            updates.append("emotion=?"); params.append(update.emotion)
        if update.notes is not None:
            updates.append("notes=?"); params.append(update.notes)
        if update.lessons is not None:
            updates.append("lessons=?"); params.append(update.lessons)
        if update.rating is not None:
            updates.append("rating=?"); params.append(max(0, min(5, update.rating)))

        if updates:
            updates.append("updated_at=datetime('now')")
            params.extend([entry_id, user.user_id])
            c.execute(f"UPDATE trade_journal SET {','.join(updates)} WHERE id=? AND user_id=?", params)

    return {"ok": True, "message": "Entry updated"}


@router.delete("/{entry_id}")
async def delete_journal_entry(entry_id: int,
                                 user: CurrentUser = Depends(get_current_user)):
    """Delete a journal entry."""
    with _conn() as c:
        c.execute("DELETE FROM trade_journal WHERE id=? AND user_id=?",
                  (entry_id, user.user_id))
    return {"ok": True}


@router.get("/stats")
async def journal_stats(user: CurrentUser = Depends(get_current_user)):
    """Get journal statistics — emotions, tags, win rate by emotion."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM trade_journal WHERE user_id=?",
                         (user.user_id,)).fetchall()

    emotions = {}
    tags_count = {}
    total_pnl = 0

    for r in rows:
        d = dict(r)
        pnl = d.get("pnl", 0)
        total_pnl += pnl

        # Emotion stats
        emo = d.get("emotion", "untagged") or "untagged"
        if emo not in emotions:
            emotions[emo] = {"trades": 0, "wins": 0, "total_pnl": 0}
        emotions[emo]["trades"] += 1
        emotions[emo]["total_pnl"] += pnl
        if pnl > 0:
            emotions[emo]["wins"] += 1

        # Tag frequency
        for tag in json.loads(d.get("tags", "[]")):
            tags_count[tag] = tags_count.get(tag, 0) + 1

    emotion_stats = []
    for emo, s in emotions.items():
        emotion_stats.append({
            "emotion": emo,
            "trades": s["trades"],
            "win_rate": round(s["wins"] / s["trades"] * 100, 1) if s["trades"] else 0,
            "total_pnl": round(s["total_pnl"], 2),
        })
    emotion_stats.sort(key=lambda x: x["total_pnl"], reverse=True)

    return {
        "total_entries": len(rows),
        "total_pnl": round(total_pnl, 2),
        "avg_rating": round(sum(dict(r).get("rating", 0) for r in rows) / max(len(rows), 1), 1),
        "emotions": emotion_stats,
        "top_tags": sorted(tags_count.items(), key=lambda x: x[1], reverse=True)[:10],
    }


@router.post("/auto-import")
async def auto_import_trades(user: CurrentUser = Depends(get_current_user)):
    """Auto-import closed trades from paper trading into journal."""
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)

    imported = 0
    with _conn() as c:
        for trade in portfolio.trade_log:
            # Check if already imported
            existing = c.execute(
                "SELECT id FROM trade_journal WHERE user_id=? AND symbol=? AND entry_price=? AND exit_price=?",
                (user.user_id, trade["symbol"], trade.get("entry_price", 0), trade.get("exit_price", 0))
            ).fetchone()
            if existing:
                continue

            c.execute("""INSERT INTO trade_journal
                (user_id, symbol, side, entry_price, exit_price, quantity, pnl, return_pct,
                 strategy, trade_date)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (user.user_id, trade["symbol"], trade.get("side", ""),
                 trade.get("entry_price", 0), trade.get("exit_price", 0),
                 trade.get("quantity", 0), trade.get("net_pnl", 0),
                 trade.get("return_pct", 0), trade.get("strategy", ""),
                 trade.get("closed_at", "")[:10] if trade.get("closed_at") else ""))
            imported += 1

    return {"ok": True, "imported": imported, "message": f"Imported {imported} trades into journal"}
