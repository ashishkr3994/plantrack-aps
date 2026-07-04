"""CSV import for master data and orders (the ERP stand-in for Phase 5).

Each endpoint accepts raw CSV text and returns a per-row result: how many rows
were imported, skipped (duplicates), and any row-level errors. Imports are
idempotent on business keys (existing rows are skipped, not duplicated).
Writes require planner+. After an orders/BOM import, material status is
re-initialised and risk re-evaluated so the KPI reflects the new data.
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..deps import require_role, audit
from ..engine.material_init import ensure_material_status
from ..engine.material_risk import evaluate_material_risk

router = APIRouter(prefix="/import", tags=["import"])


class CsvPayload(BaseModel):
    csv: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.strip())))


@router.post("/products", response_model=ImportResult)
def import_products(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
                    db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    existing = {p.product_id for p in db.query(models.Product).all()}
    routings = {r.route_id: r.id for r in db.query(models.Routing).all()}
    for i, row in enumerate(_rows(body.csv), start=2):
        pid = (row.get("product_id") or "").strip()
        if not pid:
            errors.append(f"row {i}: missing product_id")
            continue
        if pid in existing:
            skipped += 1
            continue
        route_id = (row.get("route_id") or "").strip()
        rid = routings.get(route_id) if route_id else None
        if route_id and rid is None:
            errors.append(f"row {i}: unknown route_id '{route_id}'")
            continue
        db.add(models.Product(
            product_id=pid, name=(row.get("name") or pid).strip(),
            family=(row.get("family") or "").strip(), routing_id=rid))
        existing.add(pid)
        imported += 1
    db.commit()
    audit(db, actor, "import", "product", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.post("/bom", response_model=ImportResult)
def import_bom(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
               db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    prod = {p.product_id: p.id for p in db.query(models.Product).all()}
    for i, row in enumerate(_rows(body.csv), start=2):
        pid = (row.get("product_id") or "").strip()
        if pid not in prod:
            errors.append(f"row {i}: unknown product_id '{pid}'")
            continue
        material = (row.get("material") or "").strip()
        if not material:
            errors.append(f"row {i}: missing material")
            continue
        try:
            qty = float(row.get("qty_per_unit") or 0)
            lead = int(float(row.get("lead_days") or 0))
        except ValueError:
            errors.append(f"row {i}: qty_per_unit/lead_days must be numeric")
            continue
        if qty <= 0:
            errors.append(f"row {i}: qty_per_unit must be > 0")
            continue
        db.add(models.BomLine(
            product_id=prod[pid], material=material, qty_per_unit=qty,
            uom=(row.get("uom") or "ea").strip(),
            supplier=(row.get("supplier") or "").strip() or None, lead_days=lead))
        imported += 1
    db.commit()
    ensure_material_status(db)
    evaluate_material_risk(db)
    audit(db, actor, "import", "bom_line", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.post("/orders", response_model=ImportResult)
def import_orders(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
                  db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    existing = {o.order_id for o in db.query(models.OrderHeader).all()}
    prod = {p.product_id: p.id for p in db.query(models.Product).all()}
    plants = {p.plant_code: p.id for p in db.query(models.Plant).all()}
    for i, row in enumerate(_rows(body.csv), start=2):
        oid = (row.get("order_id") or "").strip()
        if not oid:
            errors.append(f"row {i}: missing order_id")
            continue
        if oid in existing:
            skipped += 1
            continue
        pid = (row.get("product_id") or "").strip()
        if pid not in prod:
            errors.append(f"row {i}: unknown product_id '{pid}'")
            continue
        try:
            qty = int(float(row.get("order_qty") or 0))
            order_date = datetime.fromisoformat((row.get("order_date") or "").strip()).date()
            due = datetime.fromisoformat((row.get("committed_delivery_date") or "").strip()).date()
        except ValueError:
            errors.append(f"row {i}: bad qty or date (use YYYY-MM-DD)")
            continue
        if qty <= 0:
            errors.append(f"row {i}: order_qty must be > 0")
            continue
        if due < order_date:
            errors.append(f"row {i}: committed date before order date")
            continue
        priority = (row.get("priority") or "MED").strip().upper()
        if priority not in ("HIGH", "MED", "LOW"):
            priority = "MED"
        mode = (row.get("sched_mode") or "backward").strip().lower()
        if mode not in ("backward", "forward"):
            mode = "backward"
        plant_code = (row.get("plant") or "").strip()
        db.add(models.OrderHeader(
            order_id=oid, product_id=prod[pid],
            customer=(row.get("customer") or "").strip(), order_qty=qty,
            order_date=order_date, committed_delivery_date=due,
            priority=priority, plant_id=plants.get(plant_code), sched_mode=mode))
        existing.add(oid)
        imported += 1
    db.commit()
    ensure_material_status(db)
    evaluate_material_risk(db)
    audit(db, actor, "import", "order", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)