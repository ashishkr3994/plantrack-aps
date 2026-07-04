#!/usr/bin/env python3
# Unit tests for the CP-SAT scheduler — verify the hard constraints hold.
# Run: pytest -q

from collections import defaultdict
from cpsat_scheduler import (
    CpSatScheduler, Routing, OperationDef, Order, WorkCenter,
    sample_routings, sample_orders, sample_work_centers,
)


def solve_sample():
    s = CpSatScheduler(sample_routings(), sample_orders(), sample_work_centers())
    s.build()
    return s.solve(max_seconds=20)


def test_sample_is_feasible():
    res = solve_sample()
    assert res["feasible"], f"expected feasible, got {res['status']}"
    assert res["makespan"] is not None and res["makespan"] > 0


def test_precedence_respected():
    res = solve_sample()
    routes = {r.route_id: r for r in sample_routings()}
    orders = {o.order_id: o for o in sample_orders()}
    byk = {(o["order_id"], o["operation_seq"]): o for o in res["operations"]}
    for o in res["operations"]:
        rdef = routes[orders[o["order_id"]].route_id]
        opdef = next(x for x in rdef.ops if x.seq == o["operation_seq"])
        if opdef.predecessor is not None:
            pred = byk[(o["order_id"], opdef.predecessor)]
            assert o["start_min"] >= pred["end_min"], (
                f"{o['order_id']} op{o['operation_seq']} starts before predecessor ends")


def test_material_ready_respected():
    res = solve_sample()
    orders = {o.order_id: o for o in sample_orders()}
    for o in res["operations"]:
        assert o["start_min"] >= orders[o["order_id"]].material_ready_min


def test_capacity_never_exceeded():
    res = solve_sample()
    wc = {w.name: w for w in sample_work_centers()}
    by_wc = defaultdict(list)
    for o in res["operations"]:
        by_wc[o["work_center"]].append(o)
    for name, lst in by_wc.items():
        cap = wc[name].capacity if name in wc else 1
        events = []
        for o in lst:
            events.append((o["start_min"], 1))
            events.append((o["end_min"], -1))
        events.sort(key=lambda e: (e[0], e[1]))  # ends before starts at equal t
        cur = peak = 0
        for _, d in events:
            cur += d
            peak = max(peak, cur)
        assert peak <= cap, f"{name} peak {peak} > capacity {cap}"


def test_parallel_group_can_overlap():
    # Two parallel ops sharing a predecessor must be allowed to overlap.
    res = solve_sample()
    for oid in {o["order_id"] for o in res["operations"]}:
        groups = defaultdict(list)
        for o in res["operations"]:
            if o["order_id"] == oid and o["parallel_group"]:
                groups[o["parallel_group"]].append(o)
        for members in groups.values():
            if len(members) >= 2:
                a, b = members[0], members[1]
                overlap = not (a["end_min"] <= b["start_min"] or b["end_min"] <= a["start_min"])
                assert overlap, f"{oid} parallel ops did not overlap"


def test_capacity_two_allows_concurrency():
    # A 2-machine work center should run two single-op orders concurrently,
    # halving makespan vs a 1-machine center.
    rt = [Routing("R", [OperationDef(10, "M", 0, 1.0, 0, 0, None, None)])]
    orders = [Order("O1", "R", 100, "MED", 10000, 0),
              Order("O2", "R", 100, "MED", 10000, 0)]
    m1 = CpSatScheduler(rt, orders, [WorkCenter("M", 1)])
    m1.build()
    r1 = m1.solve(5)
    m2 = CpSatScheduler(rt, orders, [WorkCenter("M", 2)])
    m2.build()
    r2 = m2.solve(5)
    assert r2["makespan"] < r1["makespan"], "capacity=2 should reduce makespan"


def test_priority_sequenced_first():
    # Under contention for one machine, the HIGH-priority order should start first.
    rt = [Routing("R", [OperationDef(10, "M", 0, 1.0, 0, 0, None, None)])]
    orders = [Order("LOWp", "R", 100, "LOW", 50, 0),
              Order("HIGHp", "R", 100, "HIGH", 50, 0)]
    s = CpSatScheduler(rt, orders, [WorkCenter("M", 1)])
    s.build()
    res = s.solve(5)
    ops = {o["order_id"]: o for o in res["operations"]}
    assert ops["HIGHp"]["start_min"] < ops["LOWp"]["start_min"]
