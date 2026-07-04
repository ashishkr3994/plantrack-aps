"""Event bus for live updates — bridges sync request handlers and the Celery
worker to the async WebSocket hub.

Two backends, chosen by env:
  * Redis pub/sub (CELERY_BROKER_URL or REDIS_URL set to redis://...): any process
    publishes to a channel; each web process's WS endpoint subscribes and fans out
    to its connected clients. This works across the web tier AND the worker, and
    across multiple web workers.
  * In-process (no Redis): publish() hands directly to the local async hub via the
    running event loop. Fine for single-process dev and tests; a worker in this
    mode can't reach web clients (acceptable for those setups).

publish() is safe to call from sync code (request handlers, Celery tasks).
"""
from __future__ import annotations
import asyncio
import json
import os

REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("CELERY_BROKER_URL", "")
USE_REDIS = REDIS_URL.startswith("redis://") or REDIS_URL.startswith("rediss://")
CHANNEL = "plantrack:events"


def publish(event_type: str, payload: dict | None = None) -> None:
    """Publish an event from anywhere (sync-safe). Best-effort; never raises."""
    message = json.dumps({"type": event_type, "payload": payload or {}})
    try:
        if USE_REDIS:
            _redis_publish(message)
        else:
            _local_publish(event_type, payload)
    except Exception:
        # live updates are best-effort; a failure here must never break the action
        pass


# ---- Redis backend ----
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis.from_url(REDIS_URL)
    return _redis_client


def _redis_publish(message: str) -> None:
    _get_redis().publish(CHANNEL, message)


async def redis_subscribe(handler):
    """Async: subscribe to the channel and call handler(type, payload) per message.
    Used by the WS endpoint when Redis is configured."""
    import redis.asyncio as aioredis
    client = aioredis.Redis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                data = json.loads(msg["data"])
            except Exception:
                continue
            await handler(data.get("type", ""), data.get("payload", {}))
    finally:
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.close()


# ---- In-process backend ----
# The WS endpoint registers the running loop + hub so sync callers can schedule
# a broadcast onto it.
_loop = None
_hub = None


def register_local(loop, hub) -> None:
    global _loop, _hub
    _loop = loop
    _hub = hub


def _local_publish(event_type: str, payload: dict | None) -> None:
    if _loop is None or _hub is None:
        return
    fut = asyncio.run_coroutine_threadsafe(_hub.broadcast(event_type, payload), _loop)
    # don't block the caller waiting for delivery
    del fut
