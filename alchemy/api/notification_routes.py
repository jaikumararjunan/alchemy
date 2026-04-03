"""
alchemy.api.notification_routes
================================
REST API for the notification system.

Endpoints:
  GET  /notifications/providers         — List all available providers + config fields
  GET  /notifications/channels          — List user's channels
  POST /notifications/channels          — Add a new channel
  PUT  /notifications/channels/{id}     — Update channel
  DEL  /notifications/channels/{id}     — Delete channel
  POST /notifications/channels/{id}/test — Send test notification
  GET  /notifications/rules             — List notification rules
  POST /notifications/rules             — Create rule
  PUT  /notifications/rules/{id}        — Update rule
  DEL  /notifications/rules/{id}        — Delete rule
  GET  /notifications/delivery-log      — Delivery history
  GET  /notifications/events            — Available event types
  POST /notifications/preferences       — Update preferences
  POST /notifications/broadcast         — Admin: broadcast to all users
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from alchemy.auth.middleware import CurrentUser, get_current_user, require_role
from alchemy.notifications.dispatcher import get_dispatcher
from alchemy.notifications.models import (
    DeliveryStatus, EventSeverity, EventType, NotificationChannel,
    NotificationEvent, NotificationPreference, NotificationRule, ProviderType,
)
from alchemy.notifications.providers.registry import registry
from alchemy.users.models import UserRole

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AddChannelRequest(BaseModel):
    name:     str
    provider: ProviderType
    config:   dict[str, Any]
    enabled:  bool = True


class UpdateChannelRequest(BaseModel):
    name:    Optional[str]          = None
    enabled: Optional[bool]         = None
    config:  Optional[dict[str, Any]] = None


class AddRuleRequest(BaseModel):
    name:               str
    enabled:            bool               = True
    event_types:        list[EventType]    = []
    min_severity:       EventSeverity      = EventSeverity.INFO
    channel_ids:        list[str]          = []
    providers:          list[ProviderType] = []
    throttle_s:         int                = 0
    quiet_hours_start:  Optional[int]      = None
    quiet_hours_end:    Optional[int]      = None


class UpdatePreferencesRequest(BaseModel):
    enabled:            Optional[bool] = None
    quiet_hours_start:  Optional[int]  = None
    quiet_hours_end:    Optional[int]  = None
    timezone_str:       Optional[str]  = None
    max_per_hour:       Optional[int]  = None
    digest_mode:        Optional[bool] = None


class BroadcastRequest(BaseModel):
    title:      str
    message:    str
    severity:   EventSeverity = EventSeverity.INFO
    event_type: EventType     = EventType.CUSTOM


# ── Provider discovery ────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    """Return all available providers with their config fields (for UI form generation)."""
    return {"providers": registry.provider_metadata()}


@router.get("/events")
async def list_event_types():
    """Return all event types with their default severity."""
    from alchemy.notifications.models import EVENT_SEVERITY
    return {
        "events": [
            {
                "type":     et.value,
                "severity": EVENT_SEVERITY.get(et, EventSeverity.INFO).value,
                "group":    et.value.split(".")[0],
            }
            for et in EventType
        ]
    }


# ── Channel management ────────────────────────────────────────────────────────

@router.get("/channels")
async def list_channels(user: CurrentUser = Depends(get_current_user)):
    dispatcher = get_dispatcher()
    return {
        "channels": [c.safe_dict() for c in dispatcher.get_channels(user.user_id)]
    }


@router.post("/channels", status_code=status.HTTP_201_CREATED)
async def add_channel(
    req:  AddChannelRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a new notification channel after validating the config."""
    provider = registry.get(req.provider)
    if not provider:
        raise HTTPException(400, f"Provider '{req.provider.value}' not registered. "
                                 f"Available: {registry.available_types()}")
    try:
        provider.validate_config(req.config)
    except ValueError as e:
        raise HTTPException(422, f"Invalid config: {e}")

    channel = NotificationChannel(
        user_id=user.user_id,
        provider=req.provider,
        name=req.name,
        config=req.config,
        enabled=req.enabled,
    )
    get_dispatcher().add_channel(channel)
    return {"channel": channel.safe_dict(), "message": f"{req.provider.value} channel added"}


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    req:        UpdateChannelRequest,
    user:       CurrentUser = Depends(get_current_user),
):
    dispatcher = get_dispatcher()
    channels   = dispatcher.get_channels(user.user_id)
    channel    = next((c for c in channels if c.id == channel_id), None)
    if not channel:
        raise HTTPException(404, "Channel not found")

    if req.name    is not None: channel.name    = req.name
    if req.enabled is not None: channel.enabled = req.enabled
    if req.config  is not None:
        try:
            provider = registry.get_or_raise(channel.provider)
            provider.validate_config(req.config)
        except ValueError as e:
            raise HTTPException(422, str(e))
        channel.config = req.config

    dispatcher.add_channel(channel)  # Re-register (replaces by ID)
    return {"channel": channel.safe_dict()}


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: str,
    user:       CurrentUser = Depends(get_current_user),
):
    removed = get_dispatcher().remove_channel(user.user_id, channel_id)
    if not removed:
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: str,
    user:       CurrentUser = Depends(get_current_user),
):
    """Send a test notification to verify the channel works."""
    channels = get_dispatcher().get_channels(user.user_id)
    channel  = next((c for c in channels if c.id == channel_id), None)
    if not channel:
        raise HTTPException(404, "Channel not found")

    provider = registry.get_or_raise(channel.provider)
    result   = await provider.test_connection(channel.config)
    return {
        "success":    result.success,
        "provider":   result.provider,
        "message_id": result.message_id,
        "error":      result.error,
    }


# ── Rules ─────────────────────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules(user: CurrentUser = Depends(get_current_user)):
    dispatcher = get_dispatcher()
    rules = dispatcher._rules.get(user.user_id, [])
    return {"rules": [r.model_dump() for r in rules]}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    req:  AddRuleRequest,
    user: CurrentUser = Depends(get_current_user),
):
    rule = NotificationRule(
        user_id=user.user_id,
        name=req.name,
        enabled=req.enabled,
        event_types=req.event_types,
        min_severity=req.min_severity,
        channel_ids=req.channel_ids,
        providers=req.providers,
        throttle_s=req.throttle_s,
        quiet_hours_start=req.quiet_hours_start,
        quiet_hours_end=req.quiet_hours_end,
    )
    get_dispatcher().add_rule(rule)
    return {"rule": rule.model_dump()}


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    user:    CurrentUser = Depends(get_current_user),
):
    dispatcher = get_dispatcher()
    rules = dispatcher._rules.get(user.user_id, [])
    before = len(rules)
    dispatcher._rules[user.user_id] = [r for r in rules if r.id != rule_id]
    if len(dispatcher._rules[user.user_id]) == before:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


# ── Preferences ───────────────────────────────────────────────────────────────

@router.post("/preferences")
async def update_preferences(
    req:  UpdatePreferencesRequest,
    user: CurrentUser = Depends(get_current_user),
):
    dispatcher = get_dispatcher()
    pref = dispatcher._prefs.get(user.user_id) or NotificationPreference(user_id=user.user_id)
    if req.enabled            is not None: pref.enabled             = req.enabled
    if req.quiet_hours_start  is not None: pref.quiet_hours_start   = req.quiet_hours_start
    if req.quiet_hours_end    is not None: pref.quiet_hours_end     = req.quiet_hours_end
    if req.timezone_str       is not None: pref.timezone_str        = req.timezone_str
    if req.max_per_hour       is not None: pref.max_per_hour        = req.max_per_hour
    if req.digest_mode        is not None: pref.digest_mode         = req.digest_mode
    dispatcher.set_preference(pref)
    return {"preferences": pref.model_dump()}


@router.get("/preferences")
async def get_preferences(user: CurrentUser = Depends(get_current_user)):
    dispatcher = get_dispatcher()
    pref = dispatcher._prefs.get(user.user_id) or NotificationPreference(user_id=user.user_id)
    return {"preferences": pref.model_dump()}


# ── Delivery log ──────────────────────────────────────────────────────────────

@router.get("/delivery-log")
async def delivery_log(
    limit: int = 50,
    user:  CurrentUser = Depends(get_current_user),
):
    return {
        "records": get_dispatcher().delivery_log(user.user_id, limit)
    }


# ── Admin broadcast ───────────────────────────────────────────────────────────

@router.post("/broadcast")
async def broadcast(
    req:  BroadcastRequest,
    user: CurrentUser = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)),
):
    """Admin-only: broadcast a notification to all configured channels."""
    event = NotificationEvent(
        event_type=req.event_type,
        severity=req.severity,
        user_id=None,   # Broadcast = no specific user
        title=req.title,
        message=req.message,
        source=f"admin:{user.email}",
    )
    records = await get_dispatcher().notify(event)
    return {
        "sent":   sum(1 for r in records if r.status == DeliveryStatus.SENT),
        "failed": sum(1 for r in records if r.status == DeliveryStatus.FAILED),
        "total":  len(records),
    }
