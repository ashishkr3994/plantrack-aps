"""Load scheduling inputs from the database into plain dataclasses the
CP-SAT model and the heuristic both consume. Keeps the engine decoupled
from SQLAlchemy.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from .calendar import WorkingCalendar

# Fixed downstream lead time (days) between production end and customer
# delivery: pack + dispatch + transport. The solver targets production
# finishing early enough that delivery (prod_end + this lead) lands by the
# committed date, so we subtract this here when computing the due target.
# The writer imports these SAME constants so the two never drift apart.
PACK_DAYS = 1
DISPATCH_DAYS = 1
TRANSPORT_DAYS = 2
DELIVERY_LEAD_DAYS = PACK_DAYS + DISPATCH_DAYS + TRANSPORT_DAYS  # = 4


@dataclass
class OpInput:
    seq: int
    work_center: str
    setup: float
    run_per_unit: float
    queue: float
    move: float
    predecessor: Optional[int]
    parallel_group: Optional[str]
    # Machine eligibility: work centers this op MAY run on. Defaults to just its
    # primary work_center (backward compatible). When more than one, the solver
    # picks the best machine to balance load.
    eligible_work_centers: list[str] = field(default_factory=list)
    # Setup family: ops sharing a family on the same machine need no changeover;
    # switching families incurs a sequence-dependent setup. None = no family.
    setup_family: Optional[str] = None


@dataclass
class OrderInput:
    order_id: str              # business id e.g. ORD-4312
    pk: int                    # db primary key
    route_id: str
    qty: int
    priority: str
    committed_due_min: int     # working-minutes from origin
    material_ready_min: int    # earliest start, working-minutes from origin
    committed_due_dt: datetime
    ops: list[OpInput] = field(default_factory=list)


@dataclass
class SchedulingInput:
    origin: datetime
    calendar: WorkingCalendar
    orders: list[OrderInput]
    work_center_capacity: dict[str, int]
    # Sequence-dependent changeover minutes between setup families on the same
    # machine: changeover_minutes[(from_family, to_family)] = minutes.
    # Missing pairs default to 0 (same family) - see engine.
    changeover_minutes: dict[tuple, int] = field(default_factory=dict)
    # Optional warm start: {(order_pk, operation_seq): start_minute} from the
    # current schedule, fed to the solver as hints so re-solves stay stable.
    warm_start: dict[tuple, int] = field(default_factory=dict)


def load_scheduling_input(db: Session, minutes_per_day: int = 600,
                          default_wc_capacity: int = 1,
                          wc_capacity_overrides: dict[str, int] | None = None,
                          order_ids: list[str] | None = None) -> SchedulingInput:
    """Read orders (optionally a subset), their routings, and material status.
    The origin is 'now' (UTC), floored to the hour."""
    origin = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # holidays from the plant calendar (explicit holiday_date rows)
    holidays = set()
    for row in db.query(models.PlantCalendar).filter(
            models.PlantCalendar.is_holiday.is_(True)).all():
        if row.holiday_date:
            holidays.add(row.holiday_date)

    cal = WorkingCalendar(origin, minutes_per_day=minutes_per_day, holidays=holidays)

    # routings -> {route_id: [OpInput]}
    routes: dict[str, list[OpInput]] = {}
    for r in db.query(models.Routing).all():
        ops = sorted(r.operations, key=lambda o: o.operation_seq)
        routes[r.route_id] = [
            OpInput(
                seq=o.operation_seq, work_center=o.work_center,
                setup=float(o.setup_min or 0), run_per_unit=float(o.run_per_unit_min or 0),
                queue=float(o.queue_min or 0), move=float(o.move_min or 0),
                predecessor=o.predecessor_seq, parallel_group=o.parallel_group,
                eligible_work_centers=(
                    [w.strip() for w in o.eligible_work_centers.split(",") if w.strip()]
                    if getattr(o, "eligible_work_centers", None) else [o.work_center]),
                setup_family=getattr(o, "setup_family", None),
            ) for o in ops
        ]

    # product pk -> route_id
    prod_route = {p.id: (p.routing.route_id if p.routing_id and p.routing else None)
                  for p in db.query(models.Product).all()}

    # material status: order pk -> earliest ready datetime (expected/actual/planned)
    matstat = {m.order_id: m for m in db.query(models.MaterialStatus).all()}

    q = db.query(models.OrderHeader)
    if order_ids:
        q = q.filter(models.OrderHeader.order_id.in_(order_ids))
    orders: list[OrderInput] = []
    for o in q.all():
        route_id = prod_route.get(o.product_id)
        if not route_id or route_id not in routes:
            continue
        # material-ready offset
        ms = matstat.get(o.id)
        ready_dt = None
        if ms:
            ready_dt = ms.expected_ready_dt or ms.actual_ready_dt or ms.planned_ready_dt
        if ready_dt is None:
            ready_dt = origin
        if ready_dt.tzinfo is None:
            ready_dt = ready_dt.replace(tzinfo=timezone.utc)
        material_ready_min = max(0, cal.working_minutes_between(origin, ready_dt))

        # committed due offset. The committed date is the customer DELIVERY
        # deadline; production must finish DELIVERY_LEAD_DAYS earlier so that
        # delivery (prod_end + pack + dispatch + transport) still lands by the
        # committed date. So the solver's production due target is the
        # committed date minus the delivery lead.
        delivery_due_dt = datetime.combine(o.committed_delivery_date, datetime.min.time(), tzinfo=timezone.utc)
        prod_due_dt = delivery_due_dt - timedelta(days=DELIVERY_LEAD_DAYS)
        committed_due_min = max(0, cal.working_minutes_between(origin, prod_due_dt))

        orders.append(OrderInput(
            order_id=o.order_id, pk=o.id, route_id=route_id, qty=int(o.order_qty),
            priority=str(o.priority), committed_due_min=committed_due_min,
            material_ready_min=material_ready_min, committed_due_dt=delivery_due_dt,
            ops=routes[route_id],
        ))

    # work-center capacity map
    wc_caps: dict[str, int] = {}
    for ops in routes.values():
        for op in ops:
            for wc in (op.eligible_work_centers or [op.work_center]):
                wc_caps.setdefault(wc, default_wc_capacity)
    if wc_capacity_overrides:
        wc_caps.update(wc_capacity_overrides)

    # sequence-dependent changeover matrix
    changeover: dict[tuple, int] = {}
    for cm in db.query(models.ChangeoverMatrix).all():
        changeover[(cm.from_family, cm.to_family)] = int(cm.changeover_min or 0)

    # warm start from the current schedule's operations (stabilises re-solves)
    warm: dict[tuple, int] = {}
    for oo in db.query(models.OrderOperation).all():
        if oo.planned_start is not None:
            start_dt = oo.planned_start
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            warm[(oo.order_id, oo.operation_seq)] = max(
                0, cal.working_minutes_between(origin, start_dt))

    return SchedulingInput(origin=origin, calendar=cal, orders=orders,
                           work_center_capacity=wc_caps,
                           changeover_minutes=changeover, warm_start=warm)
