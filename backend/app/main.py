"""PlanTrack APS - FastAPI application entrypoint.

Run (dev):
    cd backend
    pip install -r requirements.txt
    export DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/plantrack
    uvicorn app.main:app --reload

Interactive API docs at http://localhost:8000/docs
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings, enforce_production_safety
from .database import engine
from .routers import (products, orders, bom, events, routings, dashboard, schedule, datamodel,
                      auth, audit, materials, imports, sandbox, alerts, admin, lead_times)
from .ws import router as ws_router
from .inproc_scheduler import start_if_enabled

# Fail fast if production is misconfigured (insecure secret, wildcard CORS, etc.)
enforce_production_safety()

# Optional error tracking - only active when SENTRY_DSN is provided.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.ENVIRONMENT,
                        traces_sample_rate=0.1)
    except Exception:
        pass

app = FastAPI(title=settings.API_TITLE, version=settings.API_VERSION)

# CORS: explicit origins in production, permissive in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(orders.router)
app.include_router(bom.router)
app.include_router(events.router)
app.include_router(routings.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(materials.router)
app.include_router(imports.router)
app.include_router(sandbox.router)
app.include_router(alerts.router)
app.include_router(datamodel.router)
app.include_router(admin.router)
app.include_router(lead_times.router)
app.include_router(ws_router)


@app.on_event("startup")
def _startup() -> None:
    # single-process deployments (e.g. Render free tier) run the periodic scan
    # in-process since there's no separate Celery beat worker.
    start_if_enabled()


@app.get("/health", tags=["meta"])
def health():
    """Liveness: the process is up and serving. Cheap; no external deps.
    Use this for the platform's restart/liveness probe."""
    return {"status": "ok", "version": settings.API_VERSION,
            "environment": settings.ENVIRONMENT}


@app.get("/ready", tags=["meta"])
def ready():
    """Readiness: the app can serve real traffic (DB reachable). Use this for the
    load balancer's 'send traffic here' probe. Returns 503 when not ready."""
    from fastapi import Response
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "up"}
    except Exception:
        return Response(content='{"status":"not_ready","database":"down"}',
                        status_code=503, media_type="application/json")


@app.get("/", tags=["meta"], include_in_schema=False)
def root():
    if os.environ.get("PLANTRACK_STATIC_DIR"):
        from fastapi.responses import FileResponse
        sd = os.environ["PLANTRACK_STATIC_DIR"]
        index = os.path.join(sd, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
    return {"service": settings.API_TITLE, "docs": "/docs",
            "health": "/health", "ready": "/ready"}


# ---- serve the built frontend (single-service deploy) ----
_static_dir = os.environ.get("PLANTRACK_STATIC_DIR", "")
if _static_dir and os.path.isdir(_static_dir):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from starlette.requests import Request as _Request

    _assets = os.path.join(_static_dir, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa(full_path: str, request: _Request):
        # never shadow the API or docs
        candidate = os.path.join(_static_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static_dir, "index.html"))
