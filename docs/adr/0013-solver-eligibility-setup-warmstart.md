# 13. Solver upgrades: machine eligibility, sequence-dependent setup, warm start, explainability

**Status:** Accepted

## Context
The CP-SAT engine pinned each operation to one work center, used a fixed setup
time regardless of changeover, re-solved from scratch each time (reshuffling
stable plans), and gave no insight into *why* an order was late.

## Decisions
- **Machine eligibility / alternate work centers:** an operation may list several
  eligible work centers (`routing_operation.eligible_work_centers`). The model
  creates an optional interval per candidate machine with an exactly-one
  constraint, so the solver assigns each op to the machine that best balances
  load. Single-eligibility ops keep the original (mandatory-interval) behaviour.
- **Sequence-dependent setup:** operations carry a `setup_family`; a
  `changeover_matrix(from_family, to_family, minutes)` defines the time lost
  switching families on a machine. On single-capacity machines a pairwise
  disjunctive-with-setup formulation enforces the changeover gap between
  consecutive ops of different families (same family = no changeover).
- **Warm start:** the loader builds a hint map from the current schedule's
  operation starts and feeds it via `AddHint`, so re-solves stay close to the
  prior plan (faster convergence, less churn for planners).
- **Explainability:** the result reports the bottleneck machine, per-machine load
  (busy minutes), and a per-order reason naming the limiting machine for late
  orders. Surfaced in the solve-job result and the Reschedule screen.

## Consequences
- New migration 0004 adds the eligibility/setup columns, `changeover_matrix`, and
  `order_operation.chosen_work_center` (the machine the solver actually picked).
- Backward compatible: with no eligibility/family data the engine behaves exactly
  as before (verified — all prior tests pass unchanged).
- Sequence-dependent setup on multi-capacity (cumulative) machines is approximated
  by capacity + intrinsic op setup; full per-unit sequencing there is future work.
- Warm start is a hint, not a constraint — the solver may still depart from the
  prior plan when that materially improves the objective.


