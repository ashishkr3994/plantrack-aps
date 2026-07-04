"""Heuristic baseline scheduler — a faithful port of the prototype's greedy
forward placement (scheduleOpsForward + computeProdDuration). Used ONLY as the
comparison baseline in validation: the CP-SAT solver must be feasible and at
least as good (by weighted tardiness) as this.

The heuristic lays each order's operations forward from its material-ready time,
honouring predecessor links and letting parallel-group ops share a start. It does
NOT do finite-capacity leveling across orders (the prototype's heuristic computes
capacity load separately and only flags it) — so it can overload work centers,
which is exactly the weakness the solver fixes.
"""
from __future__ import annotations
from .loader import SchedulingInput
from .cpsat_engine import op_duration, ScheduleResult, ScheduledOp, ScheduledOrder, PRIORITY_WEIGHT


def solve(si: SchedulingInput) -> ScheduleResult:
    operations = []
    orders_out = []
    wt = 0
    makespan = 0

    for o in si.orders:
        end_times = {}                 # seq -> end minute
        cursor = o.material_ready_min   # forward cursor for sequential ops
        order_end = o.material_ready_min
        for op in o.ops:
            dur = op_duration(op, o.qty)
            if op.predecessor is not None and op.predecessor in end_times:
                start = end_times[op.predecessor]
            elif op.parallel_group and op.predecessor in end_times:
                start = end_times[op.predecessor]
            else:
                start = cursor
            end = start + dur
            end_times[op.seq] = end
            if not op.parallel_group:
                cursor = end
            order_end = max(order_end, end)
            operations.append(ScheduledOp(
                order_id=o.order_id, order_pk=o.pk, operation_seq=op.seq,
                work_center=op.work_center, parallel_group=op.parallel_group,
                predecessor=op.predecessor, start_min=start, end_min=end,
                duration_min=dur))
        lateness = max(0, order_end - o.committed_due_min)
        wt += PRIORITY_WEIGHT.get(o.priority, 1) * lateness
        makespan = max(makespan, order_end)
        orders_out.append(ScheduledOrder(
            order_id=o.order_id, order_pk=o.pk, completion_min=order_end,
            committed_due_min=o.committed_due_min, lateness_min=lateness,
            on_time=order_end <= o.committed_due_min))

    operations.sort(key=lambda r: (r.order_id, r.operation_seq))
    return ScheduleResult(
        status="HEURISTIC", feasible=True, objective=None, makespan=makespan,
        wall_time_s=0.0, weighted_tardiness=wt, orders=orders_out, operations=operations)
