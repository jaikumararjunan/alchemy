"""
alchemy.api.alert_routes
========================
Price-alert management API — users define threshold-based alerts
(price above / below a target) for any symbol.

Endpoints:
  GET  /alerts              — list all alerts for current user
  POST /alerts              — create a new price alert
  PATCH /alerts/{alert_id}  — update an alert (change threshold / status)
  DELETE /alerts/{alert_id} — delete an alert
  POST /alerts/check        — manually trigger alert evaluation (internal / admin)

Alert states:
  active    — still watching
  triggered — condition met, notification dispatched
  disabled  — paused by user
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from alchemy.auth.middleware import CurrentUser, get_current_user
from alchemy.api.database import _get_sqlite_db_path

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── DB helpers ────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_sqlite_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT    NOT NULL,
                symbol       TEXT    NOT NULL,
                exchange     TEXT    NOT NULL DEFAULT 'binance',
                condition    TEXT    NOT NULL CHECK(condition IN ('above','below')),
                target_price REAL    NOT NULL,
                notes        TEXT,
                status       TEXT    NOT NULL DEFAULT 'active'
                                     CHECK(status IN ('active','triggered','disabled')),
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                triggered_at TEXT
            )
        """)
        # Index for fast lookup by user+status
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_price_alerts_user_status
            ON price_alerts(user_id, status)
        """)
        conn.commit()


try:
    _ensure_table()
except Exception:
    pass


# ── Schemas ───────────────────────────────────────────────────────────────────

class AlertCreateRequest(BaseModel):
    symbol:       str   = Field(..., min_length=1, max_length=20,
                                pattern=r"^[A-Za-z0-9_\-\.]+$")
    exchange:     str   = Field("binance", max_length=32)
    condition:    Literal["above", "below"]
    target_price: float = Field(..., gt=0)
    notes:        Optional[str] = Field(None, max_length=500)


class AlertUpdateRequest(BaseModel):
    condition:    Optional[Literal["above", "below"]] = None
    target_price: Optional[float] = Field(None, gt=0)
    notes:        Optional[str]   = Field(None, max_length=500)
    status:       Optional[Literal["active", "disabled"]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_alerts(
    status_filter: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
):
    """List price alerts for the current user."""
    try:
        _ensure_table()
        with _conn() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM price_alerts WHERE user_id=? AND status=? ORDER BY created_at DESC",
                    (str(user.user_id), status_filter),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM price_alerts WHERE user_id=? ORDER BY created_at DESC",
                    (str(user.user_id),),
                ).fetchall()
        return {"alerts": [dict(r) for r in rows]}
    except Exception as exc:
        log.error("alerts.list_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to fetch alerts")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new price alert."""
    try:
        _ensure_table()
        symbol = body.symbol.upper()
        now = datetime.now(timezone.utc).isoformat()
        with _conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO price_alerts
                    (user_id, symbol, exchange, condition, target_price, notes, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (str(user.user_id), symbol, body.exchange,
                 body.condition, body.target_price, body.notes, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM price_alerts WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        log.info("alerts.created", user=str(user.user_id)[:8], symbol=symbol,
                 condition=body.condition, target=body.target_price)
        return {"alert": dict(row)}
    except Exception as exc:
        log.error("alerts.create_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create alert")


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: int,
    body: AlertUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update condition, target price, notes, or status (active/disabled)."""
    try:
        _ensure_table()
        with _conn() as conn:
            row = conn.execute(
                "SELECT id FROM price_alerts WHERE id=? AND user_id=?",
                (alert_id, str(user.user_id)),
            ).fetchone()
            if not row:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")

            updates: dict[str, object] = {}
            if body.condition is not None:
                updates["condition"] = body.condition
            if body.target_price is not None:
                updates["target_price"] = body.target_price
            if body.notes is not None:
                updates["notes"] = body.notes
            if body.status is not None:
                updates["status"] = body.status

            if updates:
                set_clause = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE price_alerts SET {set_clause} WHERE id=? AND user_id=?",
                    (*updates.values(), alert_id, str(user.user_id)),
                )
                conn.commit()

            updated = conn.execute(
                "SELECT * FROM price_alerts WHERE id=?", (alert_id,)
            ).fetchone()
        return {"alert": dict(updated)}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("alerts.update_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update alert")


@router.delete("/{alert_id}", status_code=status.HTTP_200_OK)
async def delete_alert(
    alert_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Permanently delete a price alert."""
    try:
        _ensure_table()
        with _conn() as conn:
            result = conn.execute(
                "DELETE FROM price_alerts WHERE id=? AND user_id=?",
                (alert_id, str(user.user_id)),
            )
            conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
        return {"ok": True, "id": alert_id}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("alerts.delete_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to delete alert")


@router.post("/check")
async def check_alerts(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Evaluate active alerts against supplied current prices and mark triggered ones.

    Request body: { "prices": { "BTCUSDT": 65000, "ETHUSDT": 3200, ... } }

    Returns list of newly triggered alerts so the frontend can display notifications.
    """
    prices: dict[str, float] = body.get("prices", {})
    if not prices:
        return {"triggered": []}

    triggered_alerts: list[dict] = []
    try:
        _ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        with _conn() as conn:
            active = conn.execute(
                "SELECT * FROM price_alerts WHERE user_id=? AND status='active'",
                (str(user.user_id),),
            ).fetchall()

            for row in active:
                symbol = row["symbol"]
                current_price = prices.get(symbol)
                if current_price is None:
                    continue

                hit = (
                    (row["condition"] == "above" and current_price >= row["target_price"])
                    or (row["condition"] == "below" and current_price <= row["target_price"])
                )
                if hit:
                    conn.execute(
                        "UPDATE price_alerts SET status='triggered', triggered_at=? WHERE id=?",
                        (now, row["id"]),
                    )
                    alert_dict = dict(row)
                    alert_dict["triggered_at"] = now
                    alert_dict["current_price"] = current_price
                    triggered_alerts.append(alert_dict)

            if triggered_alerts:
                conn.commit()

        if triggered_alerts:
            log.info("alerts.triggered", user=str(user.user_id)[:8],
                     count=len(triggered_alerts))
        return {"triggered": triggered_alerts}
    except Exception as exc:
        log.error("alerts.check_error", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to check alerts")
