# 7. Horizon + decomposition scheduling strategy

**Status:** Accepted

## Context
The Phase 0 stress test (`solver/STRESS_TEST_RESULTS.md`) showed CP-SAT is correct and
produces a feasible schedule at every scale up to 1,000 orders / ~4,800 operations, with
near-instant model build. However, within a fixed per-solve time budget, *solution
quality* falls off above a few hundred orders: the solver finds a feasible plan fast but
runs out of time to optimize it before the limit. Solving the entire backlog in one
monolithic shot is therefore not viable at scale.

## Decision
Schedule using a **rolling horizon with decomposition and warm starts**, rather than one
global solve:

1. **Horizon:** optimize a near-term window (e.g. next 1–2 weeks) to high quality; freeze
   and roll the remainder.
2. **Decomposition:** partition by plant / work-center cluster / product family so each
   solve stays in the few-hundred-order range where quality is high and fast.
3. **Warm starts:** seed each solve with the prior schedule (or the heuristic's output)
   as a hint so it improves rather than searching from scratch.
4. **Tiered time budgets:** short budget for interactive what-if (accept "good"); longer
   budget for the authoritative overnight plan (push toward optimal).

## Consequences
- The backend's scheduling orchestration is responsible for windowing, partitioning, and
  passing warm-start hints — this is a Phase 2 design requirement, now explicit rather
  than an open risk.
- A single full-backlog "solve everything optimally" mode is explicitly out of scope.
- Solver parameters (workers, branching, objective formulation) are tuning levers to
  revisit in Phase 2.


