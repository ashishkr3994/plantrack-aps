"""Routings and their operations — read plus write.

A routing is a named process flow; operations are its ordered steps. Both are
editable here. Deleting a routing cascades to its operations (FK ON DELETE
CASCADE). Operation sequence is unique within a routing.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from sqlalchemy import text
from .. import models, schemas
from ..deps import require_role, audit

router = APIRouter(prefix="/routings", tags=["routings"])


def _mark_schedules_stale(db: Session, routing_pk: int, reason: str) -> int:
    """Flag current schedules of orders whose product uses this routing as stale."""
    res = db.execute(text("""
        UPDATE planned_schedule s SET is_stale = TRUE, stale_reason = :reason
        FROM order_header o JOIN product p ON p.id = o.product_id
        WHERE s.order_id = o.id AND s.is_current AND p.routing_id = :rid
    """), {"reason": reason, "rid": routing_pk})
    db.commit()
    return res.rowcount or 0



# ---- routing (header) ----
@router.get("", response_model=list[schemas.RoutingRead])
def list_routings(db: Session = Depends(get_db)):
    return db.query(models.Routing).order_by(models.Routing.route_id).all()


@router.get("/{pk}", response_model=schemas.RoutingRead)
def get_routing(pk: int, db: Session = Depends(get_db)):
    obj = db.get(models.Routing, pk)
    if not obj:
        raise HTTPException(404, "Routing not found")
    return obj


@router.post("", response_model=schemas.RoutingRead, status_code=201)
def create_routing(payload: schemas.RoutingCreate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    if db.query(models.Routing).filter_by(route_id=payload.route_id).first():
        raise HTTPException(409, f"route_id {payload.route_id} already exists")
    obj = models.Routing(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "create", "routing", obj.route_id)
    return obj


@router.delete("/{pk}", status_code=204)
def delete_routing(pk: int, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.Routing, pk)
    if not obj:
        raise HTTPException(404, "Routing not found")
    db.delete(obj)
    db.commit()


# ---- operations within a routing ----
def _get_routing_or_404(db: Session, routing_pk: int) -> models.Routing:
    r = db.get(models.Routing, routing_pk)
    if not r:
        raise HTTPException(404, "Routing not found")
    return r


@router.post("/{routing_pk}/operations", response_model=schemas.RoutingOpRead, status_code=201)
def add_operation(routing_pk: int, payload: schemas.RoutingOpCreate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    _get_routing_or_404(db, routing_pk)
    dup = (db.query(models.RoutingOperation)
             .filter_by(routing_id=routing_pk, operation_seq=payload.operation_seq).first())
    if dup:
        raise HTTPException(409, f"operation_seq {payload.operation_seq} already exists in this routing")
    obj = models.RoutingOperation(routing_id=routing_pk, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    n = _mark_schedules_stale(db, routing_pk, f"Operation {obj.operation_seq} added")
    audit(db, actor, "add_operation", "routing", str(routing_pk), {"seq": obj.operation_seq, "schedules_marked_stale": n})
    return obj


@router.patch("/{routing_pk}/operations/{op_pk}", response_model=schemas.RoutingOpRead)
def update_operation(routing_pk: int, op_pk: int, payload: schemas.RoutingOpUpdate,
                     actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    op = db.get(models.RoutingOperation, op_pk)
    if not op or op.routing_id != routing_pk:
        raise HTTPException(404, "Operation not found in this routing")
    data = payload.model_dump(exclude_unset=True)
    # if changing seq, guard uniqueness
    new_seq = data.get("operation_seq")
    if new_seq is not None and new_seq != op.operation_seq:
        dup = (db.query(models.RoutingOperation)
                 .filter_by(routing_id=routing_pk, operation_seq=new_seq).first())
        if dup:
            raise HTTPException(409, f"operation_seq {new_seq} already exists in this routing")
    for k, v in data.items():
        setattr(op, k, v)
    db.commit()
    db.refresh(op)
    n = _mark_schedules_stale(db, routing_pk, f"Operation {op.operation_seq} changed")
    audit(db, actor, "update_operation", "routing", str(routing_pk), {"op_pk": op_pk, "schedules_marked_stale": n})
    return op


@router.delete("/{routing_pk}/operations/{op_pk}", status_code=204)
def delete_operation(routing_pk: int, op_pk: int, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    op = db.get(models.RoutingOperation, op_pk)
    if not op or op.routing_id != routing_pk:
        raise HTTPException(404, "Operation not found in this routing")
    seq = op.operation_seq
    db.delete(op)
    db.commit()
    n = _mark_schedules_stale(db, routing_pk, f"Operation {seq} removed")
    audit(db, actor, "delete_operation", "routing", str(routing_pk), {"seq": seq, "schedules_marked_stale": n})
