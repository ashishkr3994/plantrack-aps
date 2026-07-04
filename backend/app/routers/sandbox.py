"""What-if sandbox endpoint. Runs a scenario solve against a copy of the live
plan with overrides + plan levers (overtime, partial qty); never persists.
Requires planner+ (it runs the solver)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..deps import require_role
from ..engine.sandbox import run_sandbox, SandboxRequest, OrderOverride

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class OverrideIn(BaseModel):
    order_id: str
    qty: int | None = None
    priority: str | None = None
    committed_due_dt: str | None = None
    exclude: bool = False
    partial_qty: int | None = None


class SandboxIn(BaseModel):
    overrides: list[OverrideIn] = []
    mode: str = "forward"
    time_budget_s: int = 15
    overtime_hrs_per_day: int = 0


@router.post("/simulate")
def simulate(body: SandboxIn, _: models.AppUser = Depends(require_role("planner")),
             db: Session = Depends(get_db)):
    req = SandboxRequest(
        overrides=[OrderOverride(**o.model_dump()) for o in body.overrides],
        mode=body.mode, time_budget_s=min(body.time_budget_s, 60),
        overtime_hrs_per_day=max(0, min(body.overtime_hrs_per_day, 12)))
    return run_sandbox(db, req)
