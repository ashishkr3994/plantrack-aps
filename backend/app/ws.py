"""WebSocket hub for live push updates.

Connected clients (planners' browsers) receive small JSON events when something
changes — a schedule re-solved, an alert raised, an order changed — so the UI
refreshes without manual reload. A periodic ping keeps connections warm.

Events arrive via app.events_bus.publish(), callable from sync request handlers
and the Celery worker. With Redis configured the endpoint subscribes to the
pub/sub channel (works across processes / multiple web workers); otherwise it
registers the in-process loop+hub so same-process publishers reach clients.
"""
from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import events_bus

router = APIRouter()


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event_type: str, payload: dict | None = None) -> None:
        msg = json.dumps({"type": event_type, "payload": payload or {}})
        async with self._lock:
            dead = []
            for ws in self._clients:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)


hub = Hub()
_redis_task = None


async def _ensure_redis_subscriber() -> None:
    """Start a single background task that relays Redis pub/sub -> local hub."""
    global _redis_task
    if not events_bus.USE_REDIS or _redis_task is not None:
        return

    async def relay(event_type, payload):
        await hub.broadcast(event_type, payload)

    _redis_task = asyncio.create_task(events_bus.redis_subscribe(relay))


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # register the running loop + hub so in-process publishers can reach clients
    events_bus.register_local(asyncio.get_running_loop(), hub)
    await _ensure_redis_subscriber()
    await hub.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)