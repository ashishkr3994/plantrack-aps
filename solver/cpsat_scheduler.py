#!/usr/bin/env python3
# =====================================================================
#  PlanTrack APS — CP-SAT Scheduling Engine (Phase 2 starter)
#  -------------------------------------------------------------------
#  Replaces the prototype's hand-written greedy heuristic with a real
#  constraint-programming optimiser built on Google OR-Tools CP-SAT.
#
#  It takes the SAME routing structure the prototype uses
#  (operations with setup/run/queue/move, predecessor links, parallel
#  groups) plus orders and finite work-center capacity, and returns an
#  optimised schedule that:
#     * respects operation precedence (an op can't start before its
#       predecessor finishes),
#     * runs parallel-group operations concurrently,
#     * never overloads a work center (one job per machine-instance at
#       a time; capacity = number of parallel machine instances),
#     * starts no earlier than material is ready,
#     * minimises total weighted lateness against committed dates
#       (priority-weighted), with makespan as a tie-breaker.
#
#  Time is modelled in WORKING MINUTES from a common horizon origin
#  (minute 0). Calendar/working-day conversion is handled by the caller
#  the same way the prototype does; here we optimise within a flat
#  working-minute timeline so the solver stays fast and clean.
#
#  Run:  python3 cpsat_scheduler.py
#  Deps: pip install ortools
# =====================================================================

from ortools.sat.python import cp_model
from dataclasses import dataclass
from typing import Optional
import collections


# ---------------------------------------------------------------------
# 1. INPUT DATA STRUCTURES
#    These mirror the prototype's ROUTING_DEFS / orders / work centers.
# ---------------------------------------------------------------------

@dataclass
class OperationDef:
    seq: int
    work_center: str
    setup: float            # minutes, once per order
    run_per_unit: float     # minutes per unit
    queue: float            # minutes
    move: float             # minutes
    predecessor: Optional[int] = None   # seq of the op that must finish first
    parallel_group: Optional[str] = None  # ops sharing a group run concurrently

@dataclass
class Routing:
    route_id: str
    ops: list                # list[OperationDef]

@dataclass
class Order:
    order_id: str
    route_id: str
    qty: int
    priority: str            # 'HIGH' | 'MED' | 'LOW'
    committed_due_min: int   # committed delivery, in working-minutes from origin
    material_ready_min: int = 0  # earliest production can start (material on hand)

@dataclass
class WorkCenter:
    name: str
    capacity: int = 1        # how many jobs it can run at once (machine instances)


PRIORITY_WEIGHT = {'HIGH': 8, 'MED': 3, 'LOW': 1}


# ---------------------------------------------------------------------
# 2. THE SCHEDULER
# ---------------------------------------------------------------------

class CpSatScheduler:
    """
    Builds and solves the job-shop model.

    Operation duration mirrors the prototype:
        duration = setup + run_per_unit * qty + queue + move
    Parallel-group ops share their predecessor's end as a common start
    (they overlap rather than queue behind each other), exactly like the
    prototype's scheduleOpsForward / computeProdDuration logic.
    """

    def __init__(self, routings, orders, work_centers, horizon_min=None):
        self.routings = {r.route_id: r for r in routings}
        self.orders = orders
        self.work_centers = {w.name: w for w in work_centers}
        # default capacity 1 for any work center not explicitly declared
        self._default_wc_cap = 1
        self.horizon = horizon_min or self._auto_horizon()
        self.model = cp_model.CpModel()
        # task[(order_id, seq)] -> dict with start/end/interval vars + meta
        self.tasks = {}
        self.order_end = {}     # order_id -> IntVar (order completion minute)

    # ---- duration, mirroring the prototype ----
    @staticmethod
    def op_duration(op: OperationDef, qty: int) -> int:
        return int(round(op.setup + op.run_per_unit * qty + op.queue + op.move))

    def _wc_capacity(self, name: str) -> int:
        wc = self.work_centers.get(name)
        return wc.capacity if wc else self._default_wc_cap

    def _auto_horizon(self) -> int:
        # generous upper bound: sum of every operation's duration across all
        # orders (a fully serial worst case), padded, so the model is always
        # feasible to bound.
        total = 0
        for o in self.orders:
            r = self.routings[o.route_id]
            total += sum(self.op_duration(op, o.qty) for op in r.ops)
        # add the latest material-ready offset so origins are covered
        total += max((o.material_ready_min for o in self.orders), default=0)
        return max(total, 1) + 1000

    # ---- build the model ----
    def build(self):
        m = self.model
        wc_intervals = collections.defaultdict(list)  # work_center -> [intervals]

        for o in self.orders:
            routing = self.routings[o.route_id]
            end_vars_for_order = []
            seq_to_end = {}   # seq -> end var (for precedence wiring)

            # First pass: create one optional/!interval per operation
            for op in routing.ops:
                dur = self.op_duration(op, o.qty)
                suffix = f"{o.order_id}_op{op.seq}"
                start = m.NewIntVar(o.material_ready_min, self.horizon, f"start_{suffix}")
                end = m.NewIntVar(o.material_ready_min, self.horizon, f"end_{suffix}")
                interval = m.NewIntervalVar(start, dur, end, f"ivl_{suffix}")
                self.tasks[(o.order_id, op.seq)] = {
                    "op": op, "start": start, "end": end,
                    "interval": interval, "dur": dur,
                }
                seq_to_end[op.seq] = end
                end_vars_for_order.append(end)
                # capacity: this op consumes one slot of its work center
                wc_intervals[op.work_center].append(interval)

            # Second pass: precedence + parallel-group wiring
            for op in routing.ops:
                t = self.tasks[(o.order_id, op.seq)]
                if op.predecessor is not None and op.predecessor in seq_to_end:
                    # start >= predecessor end  (op cannot begin until pred done)
                    m.Add(t["start"] >= seq_to_end[op.predecessor])
                # NOTE: parallel-group members simply share the same
                # predecessor and have NO ordering constraint between them,
                # so the solver is free to overlap them — that is exactly the
                # "run concurrently" behaviour. No extra constraint needed; we
                # just must NOT force them to be sequential.

            # order completion = max end across its operations
            order_end = m.NewIntVar(0, self.horizon, f"orderend_{o.order_id}")
            m.AddMaxEquality(order_end, end_vars_for_order)
            self.order_end[o.order_id] = order_end

        # ---- finite capacity per work center ----
        # If capacity == 1  -> classic no-overlap (one job at a time).
        # If capacity  > 1  -> cumulative (that many jobs concurrently).
        for wc_name, intervals in wc_intervals.items():
            cap = self._wc_capacity(wc_name)
            if cap <= 1:
                m.AddNoOverlap(intervals)
            else:
                demands = [1] * len(intervals)
                m.AddCumulative(intervals, demands, cap)

        # ---- objective: weighted tardiness, makespan tie-breaker ----
        tardiness_terms = []
        for o in self.orders:
            w = PRIORITY_WEIGHT.get(o.priority, 1)
            # lateness = max(0, completion - committed_due)
            late = m.NewIntVar(0, self.horizon, f"late_{o.order_id}")
            m.Add(late >= self.order_end[o.order_id] - o.committed_due_min)
            # late >= 0 is implied by the var domain
            tardiness_terms.append(w * late)

        makespan = m.NewIntVar(0, self.horizon, "makespan")
        m.AddMaxEquality(makespan, list(self.order_end.values()))

        # Primary: minimise weighted tardiness. Secondary: makespan.
        # Scale tardiness up so it dominates makespan as a tie-breaker.
        m.Minimize(sum(tardiness_terms) * 1000 + makespan)

        self._makespan = makespan
        return self

    # ---- solve ----
    def solve(self, max_seconds: float = 20.0, workers: int = 8):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds
        solver.parameters.num_search_workers = workers
        status = solver.Solve(self.model)
        self._solver = solver
        self._status = status
        return self._extract(solver, status)

    def _extract(self, solver, status):
        feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        result = {
            "status": solver.StatusName(status),
            "feasible": feasible,
            "objective": solver.ObjectiveValue() if feasible else None,
            "makespan": solver.Value(self._makespan) if feasible else None,
            "wall_time_s": round(solver.WallTime(), 3),
            "orders": {},
            "operations": [],
        }
        if not feasible:
            return result
        for o in self.orders:
            comp = solver.Value(self.order_end[o.order_id])
            result["orders"][o.order_id] = {
                "completion_min": comp,
                "committed_due_min": o.committed_due_min,
                "lateness_min": max(0, comp - o.committed_due_min),
                "on_time": comp <= o.committed_due_min,
            }
        for (oid, seq), t in self.tasks.items():
            result["operations"].append({
                "order_id": oid,
                "operation_seq": seq,
                "work_center": t["op"].work_center,
                "parallel_group": t["op"].parallel_group,
                "predecessor": t["op"].predecessor,
                "start_min": solver.Value(t["start"]),
                "end_min": solver.Value(t["end"]),
                "duration_min": t["dur"],
            })
        result["operations"].sort(key=lambda r: (r["order_id"], r["operation_seq"]))
        return result


# ---------------------------------------------------------------------
# 3. SAMPLE INPUT  (the prototype's real routing + a few sample orders)
# ---------------------------------------------------------------------

def sample_routings():
    # R-STD-01 — Standard mechanical, with Paint as a parallel branch (G1),
    # taken directly from the prototype's ROUTING_DEFS.
    return [
        Routing("R-STD-01", [
            OperationDef(10, "Material prep", 60, 0.5, 30, 15, predecessor=None,  parallel_group=None),
            OperationDef(20, "Machining",     90, 1.2, 30, 15, predecessor=10,    parallel_group=None),
            OperationDef(30, "Assembly",      45, 2.0, 20, 10, predecessor=20,    parallel_group=None),
            OperationDef(40, "QC inspection", 30, 0.3, 15, 10, predecessor=30,    parallel_group=None),
            OperationDef(50, "Paint / finish",45, 0.4, 20, 15, predecessor=30,    parallel_group="G1"),
            OperationDef(60, "Packing",       15, 0.2, 10, 5,  predecessor=40,    parallel_group=None),
        ]),
        Routing("R-ELEC-01", [
            OperationDef(10, "PCB assembly",  60, 3.0, 30, 10, predecessor=None,  parallel_group=None),
            OperationDef(20, "Wiring",        30, 2.5, 20, 10, predecessor=10,    parallel_group="G1"),
            OperationDef(30, "Firmware load", 20, 1.0, 15, 5,  predecessor=10,    parallel_group="G1"),
            OperationDef(40, "Testing",       45, 1.0, 20, 10, predecessor=20,    parallel_group=None),
            OperationDef(50, "Packing",       15, 0.2, 10, 5,  predecessor=40,    parallel_group=None),
        ]),
    ]

def sample_orders():
    # committed_due_min / material_ready_min are working-minutes from origin.
    # (In production these come from the calendar conversion layer.)
    return [
        Order("ORD-4312", "R-STD-01",  500, "HIGH", committed_due_min=6000, material_ready_min=0),
        Order("ORD-4305", "R-STD-01",  800, "MED",  committed_due_min=9000, material_ready_min=480),
        Order("ORD-4287", "R-ELEC-01",  60, "LOW",  committed_due_min=7000, material_ready_min=0),
        Order("ORD-4268", "R-ELEC-01", 150, "MED",  committed_due_min=8000, material_ready_min=960),
        Order("ORD-4255", "R-STD-01",   80, "HIGH", committed_due_min=4000, material_ready_min=0),
    ]

def sample_work_centers():
    # capacity = number of parallel machine instances at that work center.
    # Machining has 2 machines; everything else is single-capacity.
    return [
        WorkCenter("Material prep", 1),
        WorkCenter("Machining",     2),
        WorkCenter("Assembly",      1),
        WorkCenter("QC inspection", 1),
        WorkCenter("Paint / finish",1),
        WorkCenter("Packing",       1),
        WorkCenter("PCB assembly",  1),
        WorkCenter("Wiring",        1),
        WorkCenter("Firmware load", 1),
        WorkCenter("Testing",       1),
    ]


# ---------------------------------------------------------------------
# 4. PRETTY-PRINT
# ---------------------------------------------------------------------

def fmt_min(m):
    h, mm = divmod(int(m), 60)
    d, h = divmod(h, 8)  # 8-working-hour "day" just for readable output
    return f"D{d} {h:02d}:{mm:02d}"

def report(res):
    print("=" * 68)
    print(f"SOLVER STATUS : {res['status']}   (feasible={res['feasible']})")
    if not res["feasible"]:
        print("No feasible schedule found.")
        return
    print(f"OBJECTIVE     : {res['objective']:.0f}   "
          f"MAKESPAN: {res['makespan']} min ({fmt_min(res['makespan'])})   "
          f"SOLVE TIME: {res['wall_time_s']}s")
    print("-" * 68)
    print("ORDER COMPLETION vs COMMITTED DUE")
    for oid, o in res["orders"].items():
        flag = "ON TIME" if o["on_time"] else f"LATE +{o['lateness_min']}m"
        print(f"  {oid:10s} done {fmt_min(o['completion_min']):>9s}  "
              f"due {fmt_min(o['committed_due_min']):>9s}   {flag}")
    print("-" * 68)
    print("OPERATION SCHEDULE")
    print(f"  {'Order':10s} {'Seq':>3s} {'Work center':15s} {'Par':4s} "
          f"{'Start':>9s} {'End':>9s} {'Dur':>6s}")
    for op in res["operations"]:
        par = op["parallel_group"] or "-"
        print(f"  {op['order_id']:10s} {op['operation_seq']:>3d} "
              f"{op['work_center']:15s} {par:4s} "
              f"{fmt_min(op['start_min']):>9s} {fmt_min(op['end_min']):>9s} "
              f"{op['duration_min']:>6d}")
    print("=" * 68)


# ---------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------

if __name__ == "__main__":
    scheduler = CpSatScheduler(
        routings=sample_routings(),
        orders=sample_orders(),
        work_centers=sample_work_centers(),
    )
    scheduler.build()
    result = scheduler.solve(max_seconds=20.0)
    report(result)
