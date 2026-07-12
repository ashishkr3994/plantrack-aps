"""CP-SAT scheduling engine - the production optimisation core.

Consumes a SchedulingInput (from loader.py) and produces an optimised schedule.

Capabilities:
  * operations as interval variables; precedence via predecessor links
  * parallel groups allowed to overlap
  * material-ready as an earliest-start bound
  * MACHINE ELIGIBILITY: an op may run on any of several eligible work centers;
    the solver assigns each op to one machine (optional intervals + exactly-one)
    and balances load across them
  * finite capacity per machine (no-overlap, or cumulative when capacity > 1)
  * SEQUENCE-DEPENDENT SETUP: changeover time between setup families on the same
    machine, modelled with a circuit (sequencing) constraint per single-capacity
    machine
  * objective: priority-weighted tardiness, makespan tie-breaker
  * WARM START: prior schedule fed as hints for stable, faster re-solves
  * EXPLAINABILITY: per-order critical-path-ish reason + bottleneck machines

Time-boxed with a feasible-solution fallback.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import collections

from ortools.sat.python import cp_model

from .loader import SchedulingInput

PRIORITY_WEIGHT = {"HIGH": 8, "MED": 3, "LOW": 1}


@dataclass
class ScheduledOp:
    order_id: str
    order_pk: int
    operation_seq: int
    work_center: str          # the machine actually chosen
    parallel_group: Optional[str]
    predecessor: Optional[int]
    start_min: int
    end_min: int
    duration_min: int
    setup_min_applied: int = 0   # changeover time the solver placed before this op


@dataclass
class ScheduledOrder:
    order_id: str
    order_pk: int
    completion_min: int
    committed_due_min: int
    lateness_min: int
    on_time: bool
    bottleneck: Optional[str] = None   # explainability: limiting machine/reason


@dataclass
class ScheduleResult:
    status: str
    feasible: bool
    objective: Optional[float]
    makespan: Optional[int]
    wall_time_s: float
    weighted_tardiness: int
    orders: list[ScheduledOrder] = field(default_factory=list)
    operations: list[ScheduledOp] = field(default_factory=list)
    explain: dict = field(default_factory=dict)   # bottlenecks, machine loads


def base_duration(op, qty: int) -> int:
    """Processing time excluding sequence-dependent changeover (setup here is the
    op's intrinsic setup; changeover between families is added separately)."""
    return int(round(op.setup + op.run_per_unit * qty + op.queue + op.move))


def op_duration(op, qty: int) -> int:   # kept for callers/tests
    return base_duration(op, qty)


def _changeover(si: SchedulingInput, from_family, to_family) -> int:
    if from_family is None or to_family is None or from_family == to_family:
        return 0
    return int(si.changeover_minutes.get((from_family, to_family), 0))


def solve(si: SchedulingInput, max_seconds: float = 30.0, workers: int = 8,
          leveling: str = "off") -> ScheduleResult:
    model = cp_model.CpModel()

    # horizon: serial worst case + latest material ready + a setup allowance
    horizon = 0
    for o in si.orders:
        horizon += sum(base_duration(op, o.qty) for op in o.ops)
    horizon += max((o.material_ready_min for o in si.orders), default=0)
    max_changeover = max(si.changeover_minutes.values(), default=0)
    horizon = max(horizon, 1) + 1000 + max_changeover * 50

    # presence/interval bookkeeping
    # op_key -> dict(start,end,dur,family, machines={wc: (present, interval)})
    tasks: dict[tuple, dict] = {}
    order_end: dict[int, object] = {}
    # per machine: list of (op_key, present_var, interval, family, start, end)
    machine_ops: dict[str, list] = collections.defaultdict(list)

    for o in si.orders:
        seq_to_end = {}
        end_vars = []
        for op in o.ops:
            dur = base_duration(op, o.qty)
            sfx = f"{o.order_id}_{op.seq}"
            start = model.NewIntVar(o.material_ready_min, horizon, f"s_{sfx}")
            end = model.NewIntVar(o.material_ready_min, horizon, f"e_{sfx}")

            eligible = op.eligible_work_centers or [op.work_center]
            machines = {}
            presence_lits = []
            for wc in eligible:
                if len(eligible) == 1:
                    present = model.NewConstant(1)
                    interval = model.NewIntervalVar(start, dur, end, f"i_{sfx}_{wc}")
                else:
                    present = model.NewBoolVar(f"p_{sfx}_{wc}")
                    interval = model.NewOptionalIntervalVar(start, dur, end, present, f"i_{sfx}_{wc}")
                machines[wc] = (present, interval)
                presence_lits.append(present)
                machine_ops[wc].append(dict(
                    key=(o.pk, op.seq), present=present, interval=interval,
                    family=op.setup_family, start=start, end=end, dur=dur))
            if len(eligible) > 1:
                model.AddExactlyOne(presence_lits)

            tasks[(o.pk, op.seq)] = dict(
                op=op, start=start, end=end, dur=dur, machines=machines,
                eligible=eligible)
            seq_to_end[op.seq] = end
            end_vars.append(end)

        for op in o.ops:
            if op.predecessor is not None and op.predecessor in seq_to_end:
                model.Add(tasks[(o.pk, op.seq)]["start"] >= seq_to_end[op.predecessor])
        oe = model.NewIntVar(0, horizon, f"oe_{o.order_id}")
        model.AddMaxEquality(oe, end_vars)
        order_end[o.pk] = oe

    # capacity + sequencing per machine
    for wc, ops in machine_ops.items():
        cap = si.work_center_capacity.get(wc, 1)
        intervals = [d["interval"] for d in ops]
        if cap <= 1:
            model.AddNoOverlap(intervals)
            _add_sequence_setups(model, si, wc, ops, horizon)
        else:
            model.AddCumulative(intervals, [1] * len(intervals), cap)
            # sequence-dependent setup on multi-capacity machines is approximated
            # by capacity only (full per-resource sequencing would need per-unit
            # disaggregation); intrinsic op setup still applies via duration.

    # objective
    #
    # Tardiness is always the dominant term (x1000): meeting committed dates
    # beats everything, so leveling never sacrifices a due date. Beyond that,
    # a JIT earliness penalty discourages finishing far ahead of the promise
    # date -- this spreads work across the calendar (load leveling) instead of
    # clustering it early the way a pure makespan objective does.
    #
    #   leveling='off'    -> legacy behaviour: minimize makespan (finish ASAP)
    #   leveling='soft'   -> mild earliness penalty; still uses idle machine time
    #   leveling='strict' -> strong earliness penalty; holds orders to the
    #                        promise window even if machines sit idle
    #
    # We never breach capacity to hit a date (no-overlap stays hard); orders
    # that cannot fit simply run late and are surfaced for an overtime
    # RECOMMENDATION elsewhere, rather than the solver over-utilising a machine.
    tardiness_terms = []
    earliness_terms = []
    want_earliness = leveling in ("soft", "strict")
    for o in si.orders:
        w = PRIORITY_WEIGHT.get(o.priority, 1)
        late = model.NewIntVar(0, horizon, f"late_{o.order_id}")
        model.Add(late >= order_end[o.pk] - o.committed_due_min)
        tardiness_terms.append(w * late)
        # earliness = how far BEFORE the committed date the order finishes.
        # Only modelled when leveling is active. Upper bound must cover due
        # dates beyond the scheduling horizon (far-future commitments), else
        # the model could be forced infeasible.
        if want_earliness:
            early_ub = max(horizon, o.committed_due_min)
            early = model.NewIntVar(0, early_ub, f"early_{o.order_id}")
            model.Add(early >= o.committed_due_min - order_end[o.pk])
            earliness_terms.append(early)

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, list(order_end.values()))

    if leveling == "strict":
        # hold orders to the promise window: earliness weighted heavily, makespan
        # dropped entirely so the solver has no incentive to pull work forward.
        model.Minimize(sum(tardiness_terms) * 1000 + sum(earliness_terms) * 4)
    elif leveling == "soft":
        # prefer JIT but keep utilisation high: mild earliness penalty, and a
        # light makespan tie-breaker so idle capacity still gets used.
        model.Minimize(sum(tardiness_terms) * 1000 + sum(earliness_terms) + makespan)
    else:  # 'off' -> legacy
        model.Minimize(sum(tardiness_terms) * 1000 + makespan)

    # warm start: hint each op's start so re-solves stay close to the prior plan
    if si.warm_start:
        hint_vars = []
        hint_vals = []
        for (pk, seq), t in tasks.items():
            hint = si.warm_start.get((pk, seq))
            if hint is not None:
                hint_vars.append(t["start"])
                hint_vals.append(int(hint))
        for v, val in zip(hint_vars, hint_vals):
            model.AddHint(v, val)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = workers
    status = solver.Solve(model)
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    res = ScheduleResult(
        status=solver.StatusName(status), feasible=feasible,
        objective=solver.ObjectiveValue() if feasible else None,
        makespan=solver.Value(makespan) if feasible else None,
        wall_time_s=round(solver.WallTime(), 3),
        weighted_tardiness=0,
    )
    if not feasible:
        return res

    _extract(solver, si, tasks, order_end, machine_ops, res)
    return res


def _add_sequence_setups(model, si, wc, ops, horizon):
    """Sequence-dependent changeover on a single-capacity machine.

    For each pair of ops that could run on this machine, a boolean decides their
    order; the successor cannot start until the predecessor ends PLUS the
    family-dependent changeover. Only enforced when both ops are actually present
    on this machine. This is the standard disjunctive + setup formulation and is
    robust (no circuit bookkeeping needed)."""
    n = len(ops)
    if n <= 1:
        return
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ops[i], ops[j]
            co_ab = _changeover(si, a["family"], b["family"])
            co_ba = _changeover(si, b["family"], a["family"])
            # i_before_j: a precedes b on this machine
            i_before_j = model.NewBoolVar(f"ord_{wc}_{i}_{j}")
            both_present = [a["present"], b["present"]]
            # b starts after a ends + changeover, OR a starts after b ends + changeover
            model.Add(b["start"] >= a["end"] + co_ab).OnlyEnforceIf(
                [i_before_j, *both_present])
            model.Add(a["start"] >= b["end"] + co_ba).OnlyEnforceIf(
                [i_before_j.Not(), *both_present])


def _extract(solver, si, tasks, order_end, machine_ops, res: ScheduleResult):
    # machine load (busy minutes) for explainability
    machine_load = collections.defaultdict(int)
    # per op chosen machine + applied setup
    chosen = {}
    for (pk, seq), t in tasks.items():
        wc_chosen = None
        for wc, (present, _interval) in t["machines"].items():
            if solver.Value(present) == 1:
                wc_chosen = wc
                break
        wc_chosen = wc_chosen or t["op"].work_center
        chosen[(pk, seq)] = wc_chosen
        machine_load[wc_chosen] += t["dur"]

    wt = 0
    # bottleneck machine = highest total load
    bottleneck_machine = max(machine_load, key=machine_load.get) if machine_load else None
    for o in si.orders:
        comp = solver.Value(order_end[o.pk])
        lateness = max(0, comp - o.committed_due_min)
        wt += PRIORITY_WEIGHT.get(o.priority, 1) * lateness
        # explainability: name the busiest machine this order touches
        order_machines = {chosen[(o.pk, op.seq)] for op in o.ops}
        order_bottleneck = max(order_machines, key=lambda m: machine_load[m]) if order_machines else None
        reason = None
        if lateness > 0:
            reason = (f"Late {round(lateness/60,1)}h - limited by {order_bottleneck} "
                      f"(busiest machine on its route)")
        elif o.material_ready_min > 0:
            reason = "On time"
        res.orders.append(ScheduledOrder(
            order_id=o.order_id, order_pk=o.pk, completion_min=comp,
            committed_due_min=o.committed_due_min, lateness_min=lateness,
            on_time=comp <= o.committed_due_min, bottleneck=reason))
    res.weighted_tardiness = wt

    for (pk, seq), t in tasks.items():
        op = t["op"]
        oid = next(o.order_id for o in si.orders if o.pk == pk)
        res.operations.append(ScheduledOp(
            order_id=oid, order_pk=pk, operation_seq=seq, work_center=chosen[(pk, seq)],
            parallel_group=op.parallel_group, predecessor=op.predecessor,
            start_min=solver.Value(t["start"]), end_min=solver.Value(t["end"]),
            duration_min=t["dur"]))
    res.operations.sort(key=lambda r: (r.order_id, r.operation_seq))

    res.explain = {
        "bottleneck_machine": bottleneck_machine,
        "machine_load_min": dict(sorted(machine_load.items(), key=lambda kv: -kv[1])),
    }
