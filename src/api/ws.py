"""WebSocket connection manager for real-time dashboard broadcasting."""
from __future__ import annotations

import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages all active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()

    @property
    def count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("WS client connected (%d total)", self.count)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("WS client disconnected (%d remaining)", self.count)

    async def broadcast(self, data: Dict[str, Any]) -> None:
        """Send JSON to all connected clients; silently drop dead connections."""
        dead: Set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def send(self, ws: WebSocket, data: Dict[str, Any]) -> None:
        """Send JSON to a single client."""
        try:
            await ws.send_json(data)
        except Exception:
            self.disconnect(ws)


# Singleton shared across the app
manager = ConnectionManager()
