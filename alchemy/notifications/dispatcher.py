"""
alchemy.notifications.dispatcher
==================================
Central notification dispatcher.

Responsibilities:
  - Receive NotificationEvent from any platform module
  - Apply NotificationRules to determine which channels receive it
  - Deduplicate using idempotency keys (prevent duplicate sends)
  - Rate-limit per user/channel
  - Async queue with configurable concurrency
  - Track all delivery attempts in DeliveryRecord log
  - Auto-retry on transient failures (3 attempts, exponential backoff)

Usage::

    # From any module:
    from alchemy.notifications.dispatcher import dispatch

    await dispatch(NotificationEvent.from_signal(signal, user_id="jai"))

    # Or use the singleton:
    from alchemy.notifications.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    await dispatcher.notify(event)
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Optional

import structlog

from alchemy.notifications.models import (
    DeliveryRecord, DeliveryStatus, EventSeverity, EventType,
    NotificationChannel, NotificationEvent, NotificationPreference,
    NotificationRule, ProviderType,
)
from alchemy.notifications.providers.registry import registry

log = structlog.get_logger(__name__)

MAX_RETRIES     = 3
RETRY_BACKOFF_S = [2, 5, 15]   # Seconds between retries


class NotificationDispatcher:
    """
    Async notification dispatcher with queue, deduplication, and retry.

    In production: replace in-memory stores with Redis for distributed deployment.
    """

    def __init__(self, concurrency: int = 4) -> None:
        # In-memory stores (replace with Redis/DB in production)
        self._channels:     dict[str, list[NotificationChannel]]   = defaultdict(list)
        self._rules:        dict[str, list[NotificationRule]]       = defaultdict(list)
        self._prefs:        dict[str, NotificationPreference]       = {}
        self._delivery_log: list[DeliveryRecord]                    = []
        self._sent_ids:     set[str]                                = set()  # Deduplication
        self._rate_buckets: dict[str, list[float]]                  = defaultdict(list)

        self._queue:  asyncio.Queue[NotificationEvent] = asyncio.Queue(maxsize=1000)
        self._workers: list[asyncio.Task] = []
        self._concurrency = concurrency
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def notify(self, event: NotificationEvent) -> list[DeliveryRecord]:
        """
        Dispatch a notification event to all matching channels.
        Non-blocking — puts event on queue and returns immediately.
        Returns list of DeliveryRecords (may be empty if queued async).
        """
        # Deduplication
        if event.idempotency_key and event.idempotency_key in self._sent_ids:
            log.debug("notification.dedup_skip", key=event.idempotency_key)
            return []

        if event.idempotency_key:
            self._sent_ids.add(event.idempotency_key)
            # Clean old keys (keep last 10k)
            if len(self._sent_ids) > 10_000:
                self._sent_ids = set(list(self._sent_ids)[-5_000:])

        # For CRITICAL events, process immediately (bypass queue)
        if event.severity == EventSeverity.CRITICAL:
            return await self._process_event(event)

        # Queue for async processing
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("notification.queue_full", event_type=event.event_type.value)
            return await self._process_event(event)   # Fallback: process directly
        return []

    def notify_sync(self, event: NotificationEvent) -> None:
        """Fire-and-forget from sync code. Creates an asyncio task."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.notify(event))
            else:
                asyncio.run(self.notify(event))
        except Exception as e:
            log.error("notification.sync_dispatch_error", error=str(e))

    async def start(self) -> None:
        """Start background worker tasks."""
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self._concurrency)
        ]
        log.info("notification.dispatcher_started", workers=self._concurrency)

    async def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    # ── Channel + Rule management ─────────────────────────────────────────────

    def add_channel(self, channel: NotificationChannel) -> None:
        """Register a user's notification channel."""
        channels = self._channels[channel.user_id]
        # Replace if same ID
        channels = [c for c in channels if c.id != channel.id]
        channels.append(channel)
        self._channels[channel.user_id] = channels
        log.info("notification.channel_added",
                 user=channel.user_id, provider=channel.provider.value)

    def remove_channel(self, user_id: str, channel_id: str) -> bool:
        channels = self._channels.get(user_id, [])
        before = len(channels)
        self._channels[user_id] = [c for c in channels if c.id != channel_id]
        return len(self._channels[user_id]) < before

    def get_channels(self, user_id: str) -> list[NotificationChannel]:
        return self._channels.get(user_id, [])

    def add_rule(self, rule: NotificationRule) -> None:
        rules = self._rules[rule.user_id]
        rules = [r for r in rules if r.id != rule.id]
        rules.append(rule)
        self._rules[rule.user_id] = rules

    def set_preference(self, pref: NotificationPreference) -> None:
        self._prefs[pref.user_id] = pref

    def delivery_log(self, user_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        logs = self._delivery_log
        if user_id:
            logs = [r for r in logs if r.user_id == user_id]
        return [r.model_dump() for r in logs[-limit:]]

    def channel_stats(self, user_id: str) -> list[dict]:
        return [c.safe_dict() for c in self.get_channels(user_id)]

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error("notification.worker_error", worker=worker_id, error=str(e))

    async def _process_event(self, event: NotificationEvent) -> list[DeliveryRecord]:
        """Route event to matching channels and send."""
        records = []
        target_users = self._get_target_users(event)

        for user_id in target_users:
            if not self._check_user_rate_limit(user_id):
                log.warning("notification.rate_limit", user_id=user_id)
                continue

            channels = self._resolve_channels(user_id, event)
            for channel in channels:
                if not channel.enabled:
                    continue
                if self._is_quiet_hours(user_id):
                    if event.severity not in (EventSeverity.CRITICAL,):
                        log.debug("notification.quiet_hours_skip", user_id=user_id)
                        continue

                record = await self._send_with_retry(channel, event)
                records.append(record)
                self._delivery_log.append(record)
                if len(self._delivery_log) > 10_000:
                    self._delivery_log = self._delivery_log[-5_000:]

        return records

    async def _send_with_retry(
        self,
        channel: NotificationChannel,
        event: NotificationEvent,
    ) -> DeliveryRecord:
        """Send with exponential backoff retry."""
        record = DeliveryRecord(
            event_id=event.id,
            channel_id=channel.id,
            user_id=channel.user_id,
            provider=channel.provider,
        )

        provider = registry.get(channel.provider)
        if not provider:
            record.status = DeliveryStatus.FAILED
            record.error  = f"No provider registered for {channel.provider.value}"
            return record

        for attempt in range(MAX_RETRIES):
            record.attempts += 1
            try:
                result = await provider.send(channel, event)
                record.status     = result.status
                record.message_id = result.message_id
                record.error      = result.error

                # Update channel stats
                channel.last_sent_at = event.created_at
                if result.success:
                    channel.total_sent += 1
                    record.sent_at = event.created_at
                    log.info("notification.sent",
                             provider=channel.provider.value,
                             user=channel.user_id,
                             event=event.event_type.value,
                             msg_id=result.message_id)
                    return record
                else:
                    channel.total_failed += 1
                    channel.last_error = result.error

                if attempt < MAX_RETRIES - 1:
                    record.status = DeliveryStatus.RETRYING
                    await asyncio.sleep(RETRY_BACKOFF_S[attempt])

            except Exception as e:
                record.error  = str(e)
                record.status = DeliveryStatus.FAILED
                log.error("notification.send_exception",
                          provider=channel.provider.value, error=str(e), attempt=attempt)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF_S[attempt])

        record.status = DeliveryStatus.FAILED
        return record

    def _get_target_users(self, event: NotificationEvent) -> list[str]:
        if event.user_id:
            return [event.user_id]
        # Broadcast to all users who have channels configured
        return list(self._channels.keys())

    def _resolve_channels(
        self, user_id: str, event: NotificationEvent
    ) -> list[NotificationChannel]:
        """Apply rules to determine which channels receive this event."""
        all_channels = self._channels.get(user_id, [])
        if not all_channels:
            return []

        rules = self._rules.get(user_id, [])
        if not rules:
            # Default: send to all enabled channels
            return [c for c in all_channels if c.enabled]

        matching_channel_ids: set[str] = set()
        for rule in rules:
            if not rule.enabled:
                continue
            # Event type filter
            if rule.event_types and event.event_type not in rule.event_types:
                continue
            # Severity filter
            severity_order = [EventSeverity.INFO, EventSeverity.SUCCESS,
                               EventSeverity.WARNING, EventSeverity.CRITICAL]
            if severity_order.index(event.severity) < severity_order.index(rule.min_severity):
                continue
            # Channel filter
            if rule.channel_ids:
                matching_channel_ids.update(rule.channel_ids)
            else:
                matching_channel_ids.update(c.id for c in all_channels)

        return [c for c in all_channels if c.id in matching_channel_ids and c.enabled]

    def _check_user_rate_limit(self, user_id: str, max_per_hour: int = 50) -> bool:
        pref = self._prefs.get(user_id)
        if pref:
            max_per_hour = pref.max_per_hour
        now = time.time()
        bucket = self._rate_buckets[user_id]
        bucket = [t for t in bucket if now - t < 3600]
        if len(bucket) >= max_per_hour:
            return False
        bucket.append(now)
        self._rate_buckets[user_id] = bucket
        return True

    def _is_quiet_hours(self, user_id: str) -> bool:
        pref = self._prefs.get(user_id)
        if not pref or pref.quiet_hours_start is None:
            return False
        from datetime import datetime, timezone
        import zoneinfo
        try:
            tz   = zoneinfo.ZoneInfo(pref.timezone_str)
            hour = datetime.now(tz).hour
            start, end = pref.quiet_hours_start, pref.quiet_hours_end
            if start <= end:
                return start <= hour < end
            else:   # Wraps midnight
                return hour >= start or hour < end
        except Exception:
            return False


# ── Singleton ──────────────────────────────────────────────────────────────────
_dispatcher: Optional[NotificationDispatcher] = None

def get_dispatcher() -> NotificationDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotificationDispatcher()
    return _dispatcher

async def dispatch(event: NotificationEvent) -> list[DeliveryRecord]:
    """Convenience function — dispatch an event via the singleton."""
    return await get_dispatcher().notify(event)
