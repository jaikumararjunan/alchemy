"""
alchemy.api.security_audit_routes
====================================
Security audit dashboard API.

Endpoints:
  GET  /api/security/audit-log       — Browsable audit log with filters
  GET  /api/security/sessions        — Active sessions with device/geo info
  GET  /api/security/login-history   — Login history timeline
  GET  /api/security/devices         — Known devices with trust status
  GET  /api/security/locations       — Known login locations
  GET  /api/security/stats           — Security statistics (30d summary)
  GET  /api/security/risk-assessment — Current risk assessment
  POST /api/security/geo-fence       — Add geo-fence rule
  GET  /api/security/geo-fence       — List geo-fence rules
  DELETE /api/security/geo-fence/{id}— Remove geo-fence rule
  POST /api/security/trust-device    — Mark device as trusted
  POST /api/security/revoke-session  — Revoke a specific session
  POST /api/security/revoke-all      — Revoke all sessions (except current)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional

from alchemy.auth.middleware import get_current_user, CurrentUser
from alchemy.security.audit_engine import (
    get_audit_log, get_geo_fence, get_risk_engine,
    AuditEvent, AuditEventType, RiskLevel,
    parse_device, geolocate_ip,
)

import structlog
log = structlog.get_logger(__name__)

router = APIRouter(prefix="/security", tags=["security-audit"])


# ── Audit Log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log_entries(
    event_type: str = Query("", description="Filter by event type"),
    ip: str = Query("", description="Filter by IP"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    start_date: str = Query("", description="ISO date start"),
    end_date: str = Query("", description="ISO date end"),
    user: CurrentUser = Depends(get_current_user),
):
    """Get security audit log with full device, geo, and risk data."""
    entries = get_audit_log().query(
        user_id=user.user_id,
        event_type=event_type or None,
        ip=ip or None,
        limit=limit, offset=offset,
        start_date=start_date or None,
        end_date=end_date or None,
    )
    return {"entries": entries, "count": len(entries), "limit": limit, "offset": offset}


@router.get("/login-history")
async def login_history(
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """Get login history timeline with device and location details."""
    entries = get_audit_log().query(
        user_id=user.user_id,
        event_type=None,
        limit=limit,
    )
    # Filter to login events only
    login_events = [e for e in entries if e["event_type"] in (
        "login_success", "login_failed", "login_blocked", "geo_fence_blocked")]
    return {"history": login_events, "count": len(login_events)}


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_active_sessions(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """List all active sessions with device and geo info."""
    from alchemy.api.database import get_db
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession
    from alchemy.users.models import UserSession

    # Get sessions from DB
    db = None
    sessions = []
    try:
        from alchemy.api.database import get_session_factory
        async with get_session_factory()() as db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.user_id == user.user_id,
                    UserSession.is_active == True
                ).order_by(UserSession.last_used_at.desc())
            )
            db_sessions = result.scalars().all()

            current_ip = request.client.host if request.client else ""
            current_ua = request.headers.get("user-agent", "")

            for s in db_sessions:
                device = parse_device(s.user_agent or "")
                is_current = (s.ip_address == current_ip and s.user_agent == current_ua)
                sessions.append({
                    "session_id": str(s.id),
                    "ip": s.ip_address,
                    "user_agent": s.user_agent,
                    "device": {
                        "browser": device.browser,
                        "os": device.os,
                        "device_type": device.device_type,
                        "fingerprint": device.fingerprint_hash,
                    },
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                    "last_used": s.last_used_at.isoformat() if s.last_used_at else "",
                    "expires_at": s.expires_at.isoformat() if s.expires_at else "",
                    "is_current": is_current,
                    "is_expired": s.is_expired,
                })
    except Exception as e:
        log.warning("security.sessions_error", error=str(e))

    return {"sessions": sessions, "total": len(sessions)}


class RevokeSessionRequest(BaseModel):
    session_id: str


@router.post("/revoke-session")
async def revoke_session(req: RevokeSessionRequest,
                          user: CurrentUser = Depends(get_current_user)):
    """Revoke a specific session by ID."""
    try:
        from alchemy.api.database import get_session_factory
        from alchemy.users.models import UserSession
        from sqlalchemy import update

        async with get_session_factory()() as db:
            await db.execute(
                update(UserSession).where(
                    UserSession.id == req.session_id,
                    UserSession.user_id == user.user_id,
                ).values(is_active=False)
            )
            await db.commit()

        # Audit log
        get_audit_log().record(AuditEvent(
            event_type=AuditEventType.SESSION_REVOKED,
            user_id=user.user_id,
            session_id=req.session_id,
            metadata={"revoked_session": req.session_id},
        ))
        return {"ok": True, "message": "Session revoked"}
    except Exception as e:
        raise HTTPException(500, f"Failed to revoke session: {str(e)}")


@router.post("/revoke-all")
async def revoke_all_sessions(request: Request,
                                user: CurrentUser = Depends(get_current_user)):
    """Revoke all sessions except the current one."""
    try:
        from alchemy.api.database import get_session_factory
        from alchemy.users.models import UserSession
        from sqlalchemy import update

        current_ip = request.client.host if request.client else ""

        async with get_session_factory()() as db:
            # Deactivate all sessions for this user
            await db.execute(
                update(UserSession).where(
                    UserSession.user_id == user.user_id,
                ).values(is_active=False)
            )
            await db.commit()

        get_audit_log().record(AuditEvent(
            event_type=AuditEventType.LOGOUT_ALL,
            user_id=user.user_id, ip=current_ip,
        ))
        return {"ok": True, "message": "All sessions revoked. Please log in again."}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Known Devices ─────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(user: CurrentUser = Depends(get_current_user)):
    """List all known devices for this user."""
    risk_engine = get_risk_engine()
    with risk_engine._conn() as c:
        rows = c.execute("""SELECT fingerprint, device_info, first_seen, last_seen,
            is_trusted, login_count FROM known_devices WHERE user_id=?
            ORDER BY last_seen DESC""",
            (user.user_id,)).fetchall()

    devices = []
    for r in rows:
        d = dict(r)
        try:
            info = json.loads(d.get("device_info", "{}"))
        except (json.JSONDecodeError, TypeError):
            info = {}
        devices.append({
            "fingerprint": d["fingerprint"],
            "browser": info.get("browser", "Unknown"),
            "os": info.get("os", "Unknown"),
            "device_type": info.get("device_type", "unknown"),
            "device_brand": info.get("device_brand", ""),
            "is_trusted": bool(d["is_trusted"]),
            "login_count": d["login_count"],
            "first_seen": d["first_seen"],
            "last_seen": d["last_seen"],
        })
    return {"devices": devices, "total": len(devices)}


class TrustDeviceRequest(BaseModel):
    fingerprint: str
    trusted: bool = True


@router.post("/trust-device")
async def trust_device(req: TrustDeviceRequest,
                        user: CurrentUser = Depends(get_current_user)):
    """Mark a device as trusted (reduces risk score on future logins)."""
    risk_engine = get_risk_engine()
    with risk_engine._conn() as c:
        c.execute("UPDATE known_devices SET is_trusted=? WHERE user_id=? AND fingerprint=?",
                  (1 if req.trusted else 0, user.user_id, req.fingerprint))
    action = "trusted" if req.trusted else "untrusted"

    get_audit_log().record(AuditEvent(
        event_type=AuditEventType.DEVICE_TRUSTED,
        user_id=user.user_id,
        metadata={"fingerprint": req.fingerprint, "action": action},
    ))
    return {"ok": True, "message": f"Device {action}"}


# ── Known Locations ───────────────────────────────────────────────────────────

@router.get("/locations")
async def list_locations(user: CurrentUser = Depends(get_current_user)):
    """List all known login locations."""
    risk_engine = get_risk_engine()
    with risk_engine._conn() as c:
        rows = c.execute("""SELECT country_code, city, first_seen, last_seen, login_count
            FROM known_locations WHERE user_id=? ORDER BY last_seen DESC""",
            (user.user_id,)).fetchall()
    return {"locations": [dict(r) for r in rows]}


# ── Geo-Fencing ───────────────────────────────────────────────────────────────

class GeoFenceRequest(BaseModel):
    rule_type: str  # country_code, country, ip, ip_range, asn
    value: str      # e.g. "IN", "192.168.0.0/16", "AS15169"
    action: str = "block"  # block or allow
    description: str = ""


@router.get("/geo-fence")
async def list_geo_fence_rules(user: CurrentUser = Depends(get_current_user)):
    """List geo-fence rules for the current user."""
    rules = get_geo_fence().get_rules(user.user_id)
    return {"rules": rules}


@router.post("/geo-fence")
async def add_geo_fence_rule(req: GeoFenceRequest,
                               user: CurrentUser = Depends(get_current_user)):
    """Add a geo-fence rule (block or allow by country, IP, ASN)."""
    if req.rule_type not in ("country_code", "country", "ip", "ip_range", "asn"):
        raise HTTPException(400, "rule_type must be: country_code, country, ip, ip_range, asn")
    if req.action not in ("block", "allow"):
        raise HTTPException(400, "action must be: block or allow")

    rule_id = get_geo_fence().add_rule(
        user.user_id, req.rule_type, req.value, req.action, req.description)
    return {"ok": True, "id": rule_id, "message": f"Geo-fence rule added: {req.action} {req.rule_type}={req.value}"}


@router.delete("/geo-fence/{rule_id}")
async def remove_geo_fence_rule(rule_id: int,
                                  user: CurrentUser = Depends(get_current_user)):
    """Remove a geo-fence rule."""
    get_geo_fence().remove_rule(user.user_id, rule_id)
    return {"ok": True}


# ── Security Stats ────────────────────────────────────────────────────────────

@router.get("/stats")
async def security_stats(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """Get security statistics for the last N days."""
    return get_audit_log().get_stats(user.user_id, days)


@router.get("/risk-assessment")
async def current_risk_assessment(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Get current session risk assessment."""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")

    device = parse_device(ua)
    geo = await geolocate_ip(ip)

    risk_engine = get_risk_engine()
    score, level, factors = risk_engine.score(user.user_id, device, geo, ip)

    return {
        "risk_score": score,
        "risk_level": level.value,
        "risk_factors": factors,
        "current_session": {
            "ip": ip,
            "device": {
                "browser": device.browser,
                "os": device.os,
                "device_type": device.device_type,
                "fingerprint": device.fingerprint_hash,
            },
            "location": {
                "country": geo.country,
                "city": geo.city,
                "isp": geo.isp,
                "is_vpn": geo.is_vpn,
                "is_proxy": geo.is_proxy,
            },
        },
    }
