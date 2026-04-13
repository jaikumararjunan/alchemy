"""
alchemy.api.watchlist_routes
============================
Watchlist management API — users maintain a personal list of symbols
they want to monitor, with optional notes and target-price tags.

Endpoints:
  GET  /watchlist              — list all items for current user
  POST /watchlist              — add a symbol to watchlist
  PATCH /watchlist/{symbol}    — update notes / target_price for an entry
  DELETE /watchlist/{symbol}   — remove a symbol from watchlist
  DELETE /watchlist            — clear entire watchlist
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from alchemy.auth.middleware import CurrentUser, get_current_user
from alchemy.api.database import _get_sqlite_db_path

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

_SYMBOL_MAX = 20


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    path = _get_sqlite_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT    NOT NULL,
                symbol       TEXT    NOT NULL,
                exchange     TEXT    NOT NULL DEFAULT 'binance',
                notes        TEXT,
                target_price REAL,
                added_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, symbol)
            )
        """)
        conn.commit()


# Ensure table exists at import time
try:
    _ensure_table()
except Exception:
    pass  # Will retry on first request if DB not ready yet


# ── Schemas ───────────────────────────────────────────────────────────────────

class WatchlistAddRequest(BaseModel):
    symbol:       str           = Field(..., min_length=1, max_length=_SYMBOL_MAX,
                                        pattern=r"^[A-Za-z0-9_\-\.]+$")
    exchange:     str           = Field("binance", max_length=32)
    notes:        Optional[str] = Field(None, max_length=500)
    target_price: Optional[float] = None


class WatchlistUpdateRequest(BaseModel):
    notes:        Optional[str]   = Field(None, max_length=500)
    target_price: Optional[float] = None
    exchange:     Optional[str]   = Field(None, max_length=32)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_watchlist(user: CurrentUser = Depends(get_current_user)):
    """Return all watchlist entries for the authenticated user."""
    try:
        _ensure_table()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist_items WHERE user_id=? ORDER BY added_at DESC",
                (str(user.user_id),),
            ).fetchall()
        return {"items": [dict(r) for r in rows]}
    except Exception as exc:
        log.error("watchlist.list_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to fetch watchlist")


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a symbol to the watchlist. Silently returns the existing entry if already present."""
    try:
        _ensure_table()
        symbol = body.symbol.upper()
        now = datetime.now(timezone.utc).isoformat()
        with _conn() as conn:
            # Upsert: if duplicate, just update metadata
            conn.execute(
                """
                INSERT INTO watchlist_items (user_id, symbol, exchange, notes, target_price, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, symbol) DO UPDATE SET
                    exchange=excluded.exchange,
                    notes=excluded.notes,
                    target_price=excluded.target_price
                """,
                (str(user.user_id), symbol, body.exchange, body.notes, body.target_price, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM watchlist_items WHERE user_id=? AND symbol=?",
                (str(user.user_id), symbol),
            ).fetchone()
        log.info("watchlist.added", user=str(user.user_id)[:8], symbol=symbol)
        return {"item": dict(row)}
    except Exception as exc:
        log.error("watchlist.add_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to add to watchlist")


@router.patch("/{symbol}")
async def update_watchlist_item(
    symbol: str,
    body: WatchlistUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update notes or target_price for a watchlist entry."""
    symbol = symbol.upper()
    try:
        _ensure_table()
        with _conn() as conn:
            row = conn.execute(
                "SELECT id FROM watchlist_items WHERE user_id=? AND symbol=?",
                (str(user.user_id), symbol),
            ).fetchone()
            if not row:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"{symbol} not in watchlist")

            updates: dict[str, object] = {}
            if body.notes is not None:
                updates["notes"] = body.notes
            if body.target_price is not None:
                updates["target_price"] = body.target_price
            if body.exchange is not None:
                updates["exchange"] = body.exchange

            if updates:
                set_clause = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE watchlist_items SET {set_clause} WHERE user_id=? AND symbol=?",
                    (*updates.values(), str(user.user_id), symbol),
                )
                conn.commit()

            updated = conn.execute(
                "SELECT * FROM watchlist_items WHERE user_id=? AND symbol=?",
                (str(user.user_id), symbol),
            ).fetchone()
        return {"item": dict(updated)}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("watchlist.update_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update watchlist item")


@router.delete("/{symbol}", status_code=status.HTTP_200_OK)
async def remove_from_watchlist(
    symbol: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Remove a single symbol from the watchlist."""
    symbol = symbol.upper()
    try:
        _ensure_table()
        with _conn() as conn:
            result = conn.execute(
                "DELETE FROM watchlist_items WHERE user_id=? AND symbol=?",
                (str(user.user_id), symbol),
            )
            conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{symbol} not in watchlist")
        log.info("watchlist.removed", user=str(user.user_id)[:8], symbol=symbol)
        return {"ok": True, "symbol": symbol}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("watchlist.remove_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to remove from watchlist")


@router.delete("", status_code=status.HTTP_200_OK)
async def clear_watchlist(user: CurrentUser = Depends(get_current_user)):
    """Clear all watchlist entries for the current user."""
    try:
        _ensure_table()
        with _conn() as conn:
            conn.execute(
                "DELETE FROM watchlist_items WHERE user_id=?",
                (str(user.user_id),),
            )
            conn.commit()
        return {"ok": True}
    except Exception as exc:
        log.error("watchlist.clear_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to clear watchlist")
