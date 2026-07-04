"""CRUD for bill-of-materials lines, plus list-by-product."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role, audit

router = APIRouter(prefix="/bom", tags=["bom"])


@router.get("", response_model=list[schemas.BomRead])
def list_bom(product_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.BomLine)
    if product_id is not None:
        q = q.filter_by(product_id=product_id)
    return q.order_by(models.BomLine.id).all()


@router.post("", response_model=schemas.BomRead, status_code=201)
def create_bom(payload: schemas.BomCreate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    if not db.get(models.Product, payload.product_id):
        raise HTTPException(422, f"product_id {payload.product_id} does not exist")
    obj = models.BomLine(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "create", "bom_line", str(obj.id))
    return obj


@router.patch("/{pk}", response_model=schemas.BomRead)
def update_bom(pk: int, payload: schemas.BomUpdate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.BomLine, pk)
    if not obj:
        raise HTTPException(404, "BOM line not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "update", "bom_line", str(obj.id))
    return obj


@router.delete("/{pk}", status_code=204)
def delete_bom(pk: int, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.BomLine, pk)
    if not obj:
        raise HTTPException(404, "BOM line not found")
    bid = obj.id
    db.delete(obj)
    db.commit()
    audit(db, actor, "delete", "bom_line", str(bid))
