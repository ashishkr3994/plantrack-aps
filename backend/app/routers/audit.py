"""Read the audit trail (admin only)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..deps import require_role

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditRead])
def list_audit(limit: int = 100, _: models.AppUser = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    return (db.query(models.AuditLog)
              .order_by(models.AuditLog.at.desc())
              .limit(min(limit, 500)).all())
