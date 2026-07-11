"""Admin utilities — demo data management.

Provides a protected endpoint to reset the database to the curated 10-order
demo dataset (wipe + shop setup + products + orders), then prime the derived
state (material status/risk, capacity load, deviations) so the dashboard is
immediately populated. Admin-only. Designed for the Render free tier where no
Shell is available: the whole reset runs from one authenticated request.
"""
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db, engine
from .. import models
from ..deps import require_role, audit

router = APIRouter(prefix="/admin", tags=["admin"])

# The demo SQL scripts ship with the app under db/demo/, applied in order.
REPO = pathlib.Path(__file__).resolve().parents[3]
DEMO_DIR = REPO / "db" / "demo"
DEMO_SCRIPTS = [
    "0001_wipe.sql",
    "0002_shop_setup.sql",
    "0003_products.sql",
    "0004_orders.sql",
]


@router.post("/reset-demo-data")
def reset_demo_data(actor: models.AppUser = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    """Wipe all orders + master data and load the curated demo dataset.
    Users are preserved. Then prime derived state so the dashboard is
    immediately meaningful. Admin-only; safe to run repeatedly."""
    applied = []
    missing = [s for s in DEMO_SCRIPTS if not (DEMO_DIR / s).exists()]
    if missing:
        raise HTTPException(
            500,
            f"demo scripts not found on server: {', '.join(missing)} "
            f"(expected under {DEMO_DIR})")

    # Run each script in its own transaction (each file wraps its own
    # BEGIN/COMMIT). Mirrors app.seed_demo's proven execution path.
    with engine.begin() as conn:
        for name in DEMO_SCRIPTS:
            conn.execute(text((DEMO_DIR / name).read_text()))
            applied.append(name)

    # Prime derived state on a fresh session so the freshly-loaded orders
    # get material status, risk, capacity load, and deviations computed.
    from ..engine.material_init import ensure_material_status
    from ..engine.material_risk import evaluate_material_risk
    ensure_material_status(db)
    material_counts = evaluate_material_risk(db)

    audit(db, actor, "reset", "demo_data", None, {"scripts": applied})

    return {
        "status": "ok",
        "scripts_applied": applied,
        "material_counts": material_counts,
        "note": ("Demo data loaded. Run the optimiser (Schedule screen) for all "
                 "orders EXCEPT ORD-9002 to reproduce the intended scenarios, "
                 "then a deviation scan to populate delayed/critical."),
    }

