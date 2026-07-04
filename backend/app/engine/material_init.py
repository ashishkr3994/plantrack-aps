"""Initialise / refresh material_status rows from each order's BOM.

Mirrors the prototype: an order's material readiness is driven by the longest
supplier lead time across its product's BOM. planned_ready_dt is derived from
the order date plus that max lead time (a simple, transparent rule for the
CSV/manual stage; the scheduler refines actual staging timing separately).
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from .. import models


def ensure_material_status(db: Session) -> int:
    """Create a material_status row for any order missing one, and refresh the
    derived planned_ready_dt / max_lead_days. Returns rows touched."""
    touched = 0
    orders = db.query(models.OrderHeader).all()
    existing = {m.order_id: m for m in db.query(models.MaterialStatus).all()}
    for o in orders:
        # max lead across the product's BOM
        bom = db.query(models.BomLine).filter_by(product_id=o.product_id).all()
        max_lead = max((int(b.lead_days or 0) for b in bom), default=0)
        count = len(bom)
        order_dt = datetime.combine(o.order_date, datetime.min.time(), tzinfo=timezone.utc)
        planned_ready = order_dt + timedelta(days=max_lead)

        ms = existing.get(o.id)
        if ms is None:
            ms = models.MaterialStatus(
                order_id=o.id, product_id=o.product_id,
                material_count=count, max_lead_days=max_lead,
                planned_ready_dt=planned_ready, status="ordered")
            db.add(ms)
            touched += 1
        else:
            # refresh derived fields only if no actual arrival yet
            ms.material_count = count
            ms.max_lead_days = max_lead
            if ms.actual_ready_dt is None:
                ms.planned_ready_dt = planned_ready
            touched += 1
    db.commit()
    return touched
