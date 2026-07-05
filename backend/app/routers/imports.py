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


# ===================================================================
#  Master data: calendar, lead-time master, routing & operations
#  (import from CSV + export current rows as JSON for CSV download)
# ===================================================================

def _export(db, sql):
    res = db.execute(__import__("sqlalchemy").text(sql))
    cols = list(res.keys())
    return [dict(zip(cols, r)) for r in res.fetchall()]


# ---- Lead-time master ----
@router.post("/lead-times", response_model=ImportResult)
def import_lead_times(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
                      db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    existing = {lt.product_family for lt in db.query(models.LeadTimeMaster).all()}
    for i, row in enumerate(_rows(body.csv), 1):
        fam = (row.get("product_family") or "").strip()
        if not fam:
            errors.append(f"row {i}: missing product_family")
            continue
        if fam in existing:
            skipped += 1
            continue
        try:
            db.add(models.LeadTimeMaster(
                product_family=fam,
                inbound_days=float(row.get("inbound_days") or 0),
                qa_days=float(row.get("qa_days") or 0),
                packing_days=float(row.get("packing_days") or 0),
                transport_days=float(row.get("transport_days") or 0),
                buffer_days=float(row.get("buffer_days") or 0)))
            imported += 1
        except ValueError:
            errors.append(f"row {i}: numeric fields must be numbers")
    db.commit()
    audit(db, actor, "import", "lead_time_master", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("/lead-times/export")
def export_lead_times(db: Session = Depends(get_db)):
    return _export(db, """
        SELECT product_family, inbound_days, qa_days, packing_days,
               transport_days, buffer_days FROM lead_time_master ORDER BY product_family
    """)


# ---- Plant calendar ----
@router.post("/calendar", response_model=ImportResult)
def import_calendar(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
                    db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    plants = {p.plant_code: p.id for p in db.query(models.Plant).all()}
    for i, row in enumerate(_rows(body.csv), 1):
        code = (row.get("plant_code") or "").strip()
        shift = (row.get("shift_name") or "").strip()
        if code not in plants:
            errors.append(f"row {i}: unknown plant_code '{code}'")
            continue
        if not shift:
            errors.append(f"row {i}: missing shift_name")
            continue
        try:
            db.add(models.PlantCalendar(
                plant_id=plants[code], shift_name=shift,
                start_time=row.get("start_time") or "08:00",
                end_time=row.get("end_time") or "16:00",
                available_min=int(float(row.get("available_min") or 480)),
                days_active=(row.get("days_active") or "Mon-Sat").strip(),
                is_holiday=(row.get("is_holiday") or "").strip().lower() in ("1", "true", "yes"),
                holiday_date=(row.get("holiday_date") or None) or None))
            imported += 1
        except (ValueError, TypeError):
            errors.append(f"row {i}: bad time/number/date value")
    db.commit()
    audit(db, actor, "import", "plant_calendar", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("/calendar/export")
def export_calendar(db: Session = Depends(get_db)):
    return _export(db, """
        SELECT p.plant_code, c.shift_name, c.start_time, c.end_time,
               c.available_min, c.days_active, c.is_holiday, c.holiday_date
        FROM plant_calendar c JOIN plant p ON p.id = c.plant_id
        ORDER BY p.plant_code, c.shift_name
    """)


# ---- Routing & operations (one CSV: route_id + operation columns) ----
@router.post("/routings", response_model=ImportResult)
def import_routings(body: CsvPayload, actor: models.AppUser = Depends(require_role("planner")),
                    db: Session = Depends(get_db)):
    imported = skipped = 0
    errors: list[str] = []
    routings = {r.route_id: r.id for r in db.query(models.Routing).all()}
    for i, row in enumerate(_rows(body.csv), 1):
        rid = (row.get("route_id") or "").strip()
        if not rid:
            errors.append(f"row {i}: missing route_id")
            continue
        # create the routing header if new
        if rid not in routings:
            r = models.Routing(route_id=rid, description=(row.get("description") or "").strip())
            db.add(r)
            db.flush()
            routings[rid] = r.id
        try:
            seq = int(float(row.get("operation_seq") or 0))
        except ValueError:
            errors.append(f"row {i}: operation_seq must be a number")
            continue
        wc = (row.get("work_center") or "").strip()
        if not wc or not seq:
            errors.append(f"row {i}: missing work_center or operation_seq")
            continue
        # skip if this routing already has this seq
        dup = db.query(models.RoutingOperation).filter_by(
            routing_id=routings[rid], operation_seq=seq).first()
        if dup:
            skipped += 1
            continue
        try:
            db.add(models.RoutingOperation(
                routing_id=routings[rid], operation_seq=seq, work_center=wc,
                setup_min=float(row.get("setup_min") or 0),
                run_per_unit_min=float(row.get("run_per_unit_min") or 0),
                queue_min=float(row.get("queue_min") or 0),
                move_min=float(row.get("move_min") or 0),
                predecessor_seq=int(float(row["predecessor_seq"])) if row.get("predecessor_seq") else None,
                parallel_group=(row.get("parallel_group") or None) or None))
            imported += 1
        except ValueError:
            errors.append(f"row {i}: numeric fields must be numbers")
    db.commit()
    audit(db, actor, "import", "routing", None, {"imported": imported, "skipped": skipped})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("/routings/export")
def export_routings(db: Session = Depends(get_db)):
    return _export(db, """
        SELECT r.route_id, r.description, o.operation_seq, o.work_center,
               o.setup_min, o.run_per_unit_min, o.queue_min, o.move_min,
               o.predecessor_seq, o.parallel_group
        FROM routing r JOIN routing_operation o ON o.routing_id = r.id
        ORDER BY r.route_id, o.operation_seq
    """)
