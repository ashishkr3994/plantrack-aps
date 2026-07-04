"""CRUD for products."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role, audit

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[schemas.ProductRead])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.Product).order_by(models.Product.product_id).all()


@router.get("/{pk}", response_model=schemas.ProductRead)
def get_product(pk: int, db: Session = Depends(get_db)):
    obj = db.get(models.Product, pk)
    if not obj:
        raise HTTPException(404, "Product not found")
    return obj


@router.post("", response_model=schemas.ProductRead, status_code=201)
def create_product(payload: schemas.ProductCreate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    if db.query(models.Product).filter_by(product_id=payload.product_id).first():
        raise HTTPException(409, f"product_id {payload.product_id} already exists")
    obj = models.Product(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "create", "product", obj.product_id)
    return obj


@router.patch("/{pk}", response_model=schemas.ProductRead)
def update_product(pk: int, payload: schemas.ProductUpdate, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.Product, pk)
    if not obj:
        raise HTTPException(404, "Product not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    audit(db, actor, "update", "product", obj.product_id)
    return obj


@router.delete("/{pk}", status_code=204)
def delete_product(pk: int, actor: models.AppUser = Depends(require_role("planner")), db: Session = Depends(get_db)):
    obj = db.get(models.Product, pk)
    if not obj:
        raise HTTPException(404, "Product not found")
    pid = obj.product_id
    db.delete(obj)
    db.commit()
    audit(db, actor, "delete", "product", pid)
