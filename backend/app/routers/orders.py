"""CRUD for orders."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role, audit
from ..events_bus import publish

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[schemas.OrderRead])
def list_orders(db: Session = Depends(get_db)):
    return db.query(models.OrderHeader).order_by(models.OrderHeader.order_id).all()


@router.get("/{pk}", response_model=schemas.OrderRead)
def get_order(pk: int, db: Session = Depends(get_db)):
    obj = db.get(models.OrderHeader, pk)
    if not obj:
        raise HTTPException(404, "Order not found")
    return obj


@router.post("", response_model=schemas.OrderRead, status_code=201)
def create_order(payload: schemas.OrderCreate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    if db.query(models.OrderHeader).filter_by(order_id=payload.order_id).first():
        raise HTTPException(409, f"order_id {payload.order_id} already exists")
    if not db.get(models.Product, payload.product_id):
        raise HTTPException(422, f"product_id {payload.product_id} does not exist")
    if payload.committed_delivery_date < payload.order_date:
        raise HTTPException(422, "committed_delivery_date cannot precede order_date")
    obj = models.OrderHeader(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "create", "order", obj.order_id)
    publish("order_changed", {"action": "create", "order_id": obj.order_id})
    return obj


@router.patch("/{pk}", response_model=schemas.OrderRead)
def update_order(pk: int, payload: schemas.OrderUpdate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.OrderHeader, pk)
    if not obj:
        raise HTTPException(404, "Order not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    publish("order_changed", {"action": "update", "order_id": obj.order_id})
    return obj


@router.delete("/{pk}", status_code=204)
def delete_order(pk: int, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.OrderHeader, pk)
    if not obj:
        raise HTTPException(404, "Order not found")
    oid = obj.order_id
    db.delete(obj)
    db.commit()
    audit(db, actor, "delete", "order", oid)
    publish("order_changed", {"action": "delete", "order_id": oid})
