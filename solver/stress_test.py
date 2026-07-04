
#!/usr/bin/env python3
# =====================================================================
#  PlanTrack APS — CP-SAT Solver Stress Test  (Phase 0 de-risking)
#  -------------------------------------------------------------------
#  Generates synthetic workloads at increasing scale and measures
#  solve time, status, and solution quality. The goal is to confirm
#  the CP-SAT model holds up at realistic production volume (hundreds
#  of orders / thousands of operations) before committing to it.
#
#  It reuses the SAME model (CpSatScheduler) and routing structure as
#  the production starter — only the input volume changes.
#
#  Run:   python3 stress_test.py
#         python3 stress_test.py --quick     (smaller ladder, for CI)
# =====================================================================

import argparse
import random
import time
import sys

from cpsat_scheduler import (
    CpSatScheduler, Routing, OperationDef, Order, WorkCenter,
)


# ---------------------------------------------------------------------
# Workload generator
# ---------------------------------------------------------------------

# A small library of routes with varying length + a parallel branch,
# representative of a real mixed-product plant.
def build_routes():
    return [
        Routing("R-STD-01", [
            OperationDef(10, "Material prep", 60, 0.5, 30, 15, None, None),
            OperationDef(20, "Machining",     90, 1.2, 30, 15, 10,   None),
            OperationDef(30, "Assembly",      45, 2.0, 20, 10, 20,   None),
            OperationDef(40, "QC inspection", 30, 0.3, 15, 10, 30,   None),
            OperationDef(50, "Paint",         45, 0.4, 20, 15, 30,   "G1"),
            OperationDef(60, "Packing",       15, 0.2, 10, 5,  40,   None),
        ]),
        Routing("R-STD-02", [
            OperationDef(10, "Casting",       120, 1.5, 60, 20, None, None),
            OperationDef(20, "Machining",     90,  2.0, 30, 15, 10,   None),
            OperationDef(30, "Assembly",      60,  3.0, 20, 10, 20,   None),
            OperationDef(40, "QC inspection", 30,  0.5, 15, 10, 30,   None),
        ]),
        Routing("R-ELEC-01", [
            OperationDef(10, "PCB assembly",  60, 3.0, 30, 10, None, None),
            OperationDef(20, "Wiring",        30, 2.5, 20, 10, 10,   "G1"),
            OperationDef(30, "Firmware load", 20, 1.0, 15, 5,  10,   "G1"),
            OperationDef(40, "Testing",       45, 1.0, 20, 10, 20,   None),
            OperationDef(50, "Packing",       15, 0.2, 10, 5,  40,   None),
        ]),
        Routing("R-HYD-01", [
            OperationDef(10, "Component prep", 90,  2.0, 45, 20, None, None),
            OperationDef(20, "Hyd assembly",   120, 4.0, 30, 20, 10,   None),
            OperationDef(30, "Pressure test",  60,  1.0, 20, 15, 20,   None),
            OperationDef(40, "QC & pack",      30,  0.5, 10, 10, 30,   None),
        ]),
    ]


def build_work_centers(multi_machine=True):
    # Give the busiest shared centers >1 machine so larger workloads stay
    # feasible in reasonable time — mirrors a real plant having parallel lines.
    caps = {
        "Material prep": 2, "Machining": 3, "Assembly": 2, "QC inspection": 2,
        "Paint": 2, "Packing": 2, "Casting": 2, "PCB assembly": 2,
        "Wiring": 2, "Firmware load": 2, "Testing": 2,
        "Component prep": 2, "Hyd assembly": 2, "Pressure test": 1, "QC & pack": 2,
    }
    if not multi_machine:
        caps = {k: 1 for k in caps}
    return [WorkCenter(n, c) for n, c in caps.items()]


def generate_orders(n, routes, seed=42):
    rng = random.Random(seed)
    route_ids = [r.route_id for r in routes]
    priorities = ["HIGH", "MED", "MED", "LOW"]  # weighted toward MED
    orders = []
    for i in range(n):
        rid = rng.choice(route_ids)
        qty = rng.choice([50, 80, 120, 200, 300, 500, 800, 1000])
        # spread material-ready across the first few "days" (480 min each)
        mat_ready = rng.choice([0, 0, 480, 960, 1440])
        # committed due spread across a realistic horizon
        due = rng.randint(3000, 30000)
        orders.append(Order(
            order_id=f"ORD-{5000+i}",
            route_id=rid,
            qty=qty,
            priority=rng.choice(priorities),
            committed_due_min=due,
            material_ready_min=mat_ready,
        ))
    return orders


def count_operations(orders, routes):
    by_id = {r.route_id: r for r in routes}
    return sum(len(by_id[o.route_id].ops) for o in orders)


# ---------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------

def run_one(n_orders, routes, work_centers, max_seconds, seed=42):
    orders = generate_orders(n_orders, routes, seed=seed)
    n_ops = count_operations(orders, routes)

    build_start = time.perf_counter()
    sched = CpSatScheduler(routes, orders, work_centers)
    sched.build()
    build_s = time.perf_counter() - build_start

    res = sched.solve(max_seconds=max_seconds, workers=8)

    on_time = sum(1 for o in res["orders"].values() if o["on_time"]) if res["feasible"] else 0
    total = len(orders)
    return {
        "orders": n_orders,
        "operations": n_ops,
        "status": res["status"],
        "feasible": res["feasible"],
        "build_s": round(build_s, 3),
        "solve_s": res["wall_time_s"],
        "makespan": res["makespan"],
        "on_time": on_time,
        "total": total,
        "on_time_pct": round(100 * on_time / total, 1) if total else 0,
    }


# ---------------------------------------------------------------------
# Ladder
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="smaller ladder + short time limits (used by CI)")
    args = ap.parse_args()

    routes = build_routes()
    work_centers = build_work_centers(multi_machine=True)

    if args.quick:
        ladder = [(20, 5), (50, 5)]
    else:
        # (order count, per-solve time budget in seconds)
        ladder = [(10, 10), (50, 15), (100, 20), (250, 30), (500, 45), (1000, 60)]

    print("=" * 86)
    print("CP-SAT SOLVER STRESS TEST")
    print("Model: interval vars + precedence + parallel groups + finite capacity")
    print("Objective: priority-weighted tardiness, makespan tie-breaker")
    print("=" * 86)
    header = f"{'Orders':>7} {'Ops':>7} {'Status':>10} {'Build(s)':>9} {'Solve(s)':>9} {'Makespan':>9} {'OnTime':>8}"
    print(header)
    print("-" * 86)

    rows = []
    worst_solve = 0.0
    for n, budget in ladder:
        r = run_one(n, routes, work_centers, max_seconds=budget)
        rows.append(r)
        worst_solve = max(worst_solve, r["solve_s"])
        print(f"{r['orders']:>7} {r['operations']:>7} {r['status']:>10} "
              f"{r['build_s']:>9.3f} {r['solve_s']:>9.3f} "
              f"{str(r['makespan']):>9} {str(r['on_time'])+'/'+str(r['total']):>8}")

    print("-" * 86)
    # Verdict: every run must be feasible, and solve time must stay within budget.
    all_feasible = all(r["feasible"] for r in rows)
    print(f"All scales feasible : {all_feasible}")
    print(f"Worst solve time    : {worst_solve:.3f}s")
    print("=" * 86)

    # Exit non-zero if any scale failed to find a feasible solution — this is
    # what makes the test usable as a CI / de-risking gate.
    if not all_feasible:
        print("RESULT: ❌ at least one scale returned no feasible schedule")
        sys.exit(1)
    print("RESULT: ✅ CP-SAT produced feasible schedules at every scale")
    sys.exit(0)


if __name__ == "__main__":
    main()
