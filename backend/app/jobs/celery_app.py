"""Celery application. Broker/backend come from env; in test or single-process
dev they can run eagerly (CELERY_TASK_ALWAYS_EAGER=1) so no Redis is required.
In production set CELERY_BROKER_URL / CELERY_RESULT_BACKEND to Redis.
"""
import os
from celery import Celery

BROKER = os.environ.get("CELERY_BROKER_URL", "memory://")
BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "cache+memory://")
SINGLE_PROCESS = os.environ.get("PLANTRACK_SINGLE_PROCESS", "0") == "1"
EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1" or SINGLE_PROCESS

celery_app = Celery("plantrack", broker=BROKER, backend=BACKEND)
# How often the periodic deviation/material-risk scan runs (seconds).
SCAN_INTERVAL_S = int(os.environ.get("PLANTRACK_SCAN_INTERVAL_S", "300"))  # 5 min

celery_app.conf.update(
    task_always_eager=EAGER,        # run inline (no worker) when set — used in tests
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "deviation-scan": {
            "task": "plantrack.periodic_deviation_scan",
            "schedule": float(SCAN_INTERVAL_S),
        },
    },
)

# ensure tasks module is imported so tasks register
from . import tasks  # noqa: E402,F401
