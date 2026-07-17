"""What-if sandbox endpoint. Runs a scenario solve against a copy of the live
plan with overrides + plan levers (overtime, partial qty, hypothetical events);
never persists. Requires planner+ (it runs the solver)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..deps import require_role
from ..engine.sandbox import run_sandbox, SandboxRequest, OrderOverride, EventOverride

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class EventOverrideIn(BaseModel):
    event_type: str                        # "pause" | "scrap" | "complete"
    operation_seq: int
    event_timestamp: str | None = None
    downtime_mins: int = 0
    whole_wc: bool = False
    qty: int = 0


class OverrideIn(BaseModel):
    order_id: str
    qty: int | None = None
    priority: str | None = None
    committed_due_dt: str | None = None
    exclude: bool = False
    partial_qty: int | None = None
    events: list[EventOverrideIn] = []


class SandboxIn(BaseModel):
    overrides: list[OverrideIn] = []
    mode: str = "forward"
    time_budget_s: int = 15
    overtime_hrs_per_day: int = 0


@router.post("/simulate")
def simulate(body: SandboxIn, _: models.AppUser = Depends(require_role("planner")),
             db: Session = Depends(get_db)):
    overrides = []
    for o in body.overrides:
        d = o.model_dump()
        events_in = d.pop("events")
        overrides.append(OrderOverride(
            **d, events=[EventOverride(**e) for e in events_in]))
    req = SandboxRequest(
        overrides=overrides,
        mode=body.mode, time_budget_s=min(body.time_budget_s, 60),
        overtime_hrs_per_day=max(0, min(body.overtime_hrs_per_day, 12)))
    return run_sandbox(db, req)
