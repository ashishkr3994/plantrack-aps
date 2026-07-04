# 4. Use OR-Tools CP-SAT for scheduling

**Status:** Accepted

## Context
The prototype schedules with a hand-written greedy heuristic: it places operations but
does not *optimize*. A real APS must optimize against finite capacity, precedence,
parallel operations, material readiness, and due dates. This is the core differentiator
of the product and was the biggest technical unknown at Phase 0.

## Decision
Use **Google OR-Tools CP-SAT** as the scheduling engine. CP-SAT is the constraint-
programming solver inside the OR-Tools suite; it provides native scheduling constructs
(interval variables, `AddNoOverlap`, `AddCumulative`) that map directly onto our routing
model. A working, verified starter model exists in `solver/cpsat_scheduler.py`.

Rationale:
- Open-source and free; strong, repeatedly competition-winning performance on job-shop.
- Interval/no-overlap/cumulative constructs express our exact problem (precedence,
  parallel groups, multi-machine work centers) cleanly.
- De-risking is complete: see `solver/STRESS_TEST_RESULTS.md`.

Alternatives considered:
- **Gurobi (MIP):** excellent for large numeric optimization, but commercial, and CP is a
  more natural fit for sequencing-heavy scheduling.
- **IBM CP Optimizer:** strong on large permutation scheduling, but commercial.
- We can revisit these later if scale demands; the model concepts transfer.

## Consequences
- The solver is a Python module/service invoked by the backend as an async job.
- Stress testing (Phase 0) showed the model is correct and feasible at scale, but that
  solution *quality* is time-bounded at high volume — which drives ADR 0007.
- Calendar/working-day conversion stays in a surrounding layer; the solver optimizes
  within a flat working-minute timeline.


