"""
alchemy.data.ws_reconnector
=============================
WebSocket auto-reconnect manager with exponential backoff + jitter.

Wraps any exchange WebSocket connection and automatically reconnects
on disconnection, with configurable backoff, max retries, and
notification on disconnect/reconnect events.

Usage::

    reconnector = WSReconnector(
        name="binance",
        connect_fn=binance_ws.connect,
        on_message=handle_message,
    )
    await reconnector.start()

    # Later:
    await reconnector.stop()
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

import structlog

log = structlog.get_logger(__name__)

# Backoff config
INITIAL_BACKOFF_S  = 1.0
MAX_BACKOFF_S      = 60.0
BACKOFF_MULTIPLIER = 2.0
JITTER_RANGE       = 0.5   # ±50% jitter
MAX_RETRIES        = 0     # 0 = unlimited retries


@dataclass
class WSReconnectorStats:
    """Connection statistics."""
    exchange: str = ""
    connected: bool = False
    total_connects: int = 0
    total_disconnects: int = 0
    total_reconnects: int = 0
    last_connected_at: Optional[float] = None
    last_disconnected_at: Optional[float] = None
    current_backoff_s: float = INITIAL_BACKOFF_S
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "connected": self.connected,
            "total_connects": self.total_connects,
            "total_disconnects": self.total_disconnects,
            "total_reconnects": self.total_reconnects,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "current_backoff_s": round(self.current_backoff_s, 1),
        }


class WSReconnector:
    """
    Auto-reconnecting WebSocket wrapper.

    Handles:
      - Automatic reconnection with exponential backoff + jitter
      - Disconnect/reconnect notifications via Telegram/Slack
      - Connection health monitoring (ping/pong or heartbeat)
      - Statistics tracking (uptime, reconnect count)
      - Graceful shutdown
    """

    def __init__(
        self,
        name: str,
        connect_fn: Callable[..., Coroutine],
        on_message: Optional[Callable[[Any], Coroutine]] = None,
        on_connect: Optional[Callable[[], Coroutine]] = None,
        on_disconnect: Optional[Callable[[], Coroutine]] = None,
        initial_backoff: float = INITIAL_BACKOFF_S,
        max_backoff: float = MAX_BACKOFF_S,
        max_retries: int = MAX_RETRIES,
        notify_on_disconnect: bool = True,
        heartbeat_interval: float = 30.0,
    ) -> None:
        self.name = name
        self._connect_fn = connect_fn
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._max_retries = max_retries
        self._notify = notify_on_disconnect
        self._heartbeat_interval = heartbeat_interval

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._ws: Any = None
        self.stats = WSReconnectorStats(exchange=name)

    async def start(self) -> None:
        """Start the reconnection loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reconnect_loop())
        log.info("ws_reconnector.started", exchange=self.name)

    async def stop(self) -> None:
        """Stop and close the connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._ws and hasattr(self._ws, "close"):
            try:
                await self._ws.close()
            except Exception:
                pass
        self.stats.connected = False
        log.info("ws_reconnector.stopped", exchange=self.name)

    async def _reconnect_loop(self) -> None:
        """Main reconnection loop with exponential backoff."""
        backoff = self._initial_backoff
        retry_count = 0

        while self._running:
            try:
                # Attempt connection
                log.info("ws_reconnector.connecting",
                         exchange=self.name, attempt=retry_count + 1)

                self._ws = await self._connect_fn()
                self.stats.connected = True
                self.stats.total_connects += 1
                self.stats.last_connected_at = time.time()
                backoff = self._initial_backoff  # Reset backoff on success
                retry_count = 0

                if retry_count > 0:
                    self.stats.total_reconnects += 1

                log.info("ws_reconnector.connected", exchange=self.name)

                # Notify reconnect (if not first connect)
                if self.stats.total_connects > 1 and self._notify:
                    await self._send_notification(
                        "reconnected",
                        f"WebSocket reconnected (downtime: "
                        f"{self._calc_downtime():.1f}s)",
                    )

                # Run callback
                if self._on_connect:
                    await self._on_connect()

                # Message loop — blocks until disconnect
                await self._message_loop()

            except asyncio.CancelledError:
                break

            except Exception as e:
                self.stats.connected = False
                self.stats.total_disconnects += 1
                self.stats.last_disconnected_at = time.time()

                log.warning(
                    "ws_reconnector.disconnected",
                    exchange=self.name,
                    error=str(e),
                    backoff_s=round(backoff, 1),
                )

                if self._on_disconnect:
                    try:
                        await self._on_disconnect()
                    except Exception:
                        pass

                # Notify disconnect
                if self._notify:
                    await self._send_notification(
                        "disconnected",
                        f"WebSocket disconnected: {e}. Reconnecting in {backoff:.0f}s...",
                    )

                # Check max retries
                retry_count += 1
                if self._max_retries > 0 and retry_count >= self._max_retries:
                    log.error("ws_reconnector.max_retries",
                              exchange=self.name, retries=retry_count)
                    break

                # Backoff with jitter
                jitter = backoff * random.uniform(-JITTER_RANGE, JITTER_RANGE)
                sleep_time = max(0.5, backoff + jitter)
                self.stats.current_backoff_s = backoff

                await asyncio.sleep(sleep_time)

                # Increase backoff
                backoff = min(backoff * BACKOFF_MULTIPLIER, self._max_backoff)

    async def _message_loop(self) -> None:
        """
        Process messages from the WebSocket.
        Override or provide on_message callback.
        Raises exception on disconnect to trigger reconnect.
        """
        if not self._ws:
            return

        # If the WS object supports async iteration
        if hasattr(self._ws, "__aiter__"):
            async for message in self._ws:
                if not self._running:
                    break
                if self._on_message:
                    try:
                        await self._on_message(message)
                    except Exception as e:
                        log.error("ws_reconnector.message_error",
                                  exchange=self.name, error=str(e))

        # If it has a recv() method
        elif hasattr(self._ws, "recv"):
            while self._running:
                try:
                    message = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=self._heartbeat_interval * 2,
                    )
                    if self._on_message:
                        await self._on_message(message)
                except asyncio.TimeoutError:
                    log.warning("ws_reconnector.heartbeat_timeout",
                                exchange=self.name)
                    raise ConnectionError("Heartbeat timeout")

    def _calc_downtime(self) -> float:
        """Calculate downtime in seconds."""
        if self.stats.last_disconnected_at and self.stats.last_connected_at:
            if self.stats.last_connected_at > self.stats.last_disconnected_at:
                return self.stats.last_connected_at - self.stats.last_disconnected_at
        return 0.0

    async def _send_notification(self, event_type: str, message: str) -> None:
        """Send disconnect/reconnect notification."""
        try:
            from alchemy.notifications.dispatcher import dispatch
            from alchemy.notifications.models import (
                EventSeverity, EventType, NotificationEvent,
            )

            severity = (EventSeverity.WARNING if event_type == "disconnected"
                        else EventSeverity.INFO)
            etype = (EventType.EXCHANGE_DISCONNECTED if event_type == "disconnected"
                     else EventType.SYSTEM_STARTUP)

            await dispatch(NotificationEvent(
                event_type=etype,
                severity=severity,
                title=f"{self.name.title()} WebSocket {event_type}",
                message=message,
                data=self.stats.to_dict(),
            ))
        except Exception as e:
            log.error("ws_reconnector.notify_error", error=str(e))


# ── Registry of all reconnectors ─────────────────────────────────────────────
_reconnectors: dict[str, WSReconnector] = {}


def register_reconnector(reconnector: WSReconnector) -> None:
    _reconnectors[reconnector.name] = reconnector


def get_reconnector(name: str) -> Optional[WSReconnector]:
    return _reconnectors.get(name)


def all_reconnector_stats() -> list[dict]:
    return [r.stats.to_dict() for r in _reconnectors.values()]
