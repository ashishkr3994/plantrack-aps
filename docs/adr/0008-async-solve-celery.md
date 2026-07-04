# 8. Run scheduling solves asynchronously (Celery + Redis)

**Status:** Accepted

## Context
A CP-SAT solve takes from milliseconds (small) to tens of seconds (time-boxed at
scale — see ADR 0007 and the stress test). A solve must never block an HTTP
request, and multiple solves should be queued and observable.

## Decision
Run solves as **asynchronous Celery tasks**. The API endpoint `POST /schedule/solve`
creates a `solve_job` row, dispatches the task, and returns `202 Accepted` with a
`job_id` immediately. Clients poll `GET /schedule/jobs/{job_id}` for status/result.
The solver is **time-boxed** (`time_budget_s`, default 30s) and returns the best
feasible solution found within the budget — it does not wait for proven optimality.

The broker is swappable via env:
- Production: `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` = Redis.
- Tests / single-process dev: `CELERY_TASK_ALWAYS_EAGER=1` runs the task inline,
  so no Redis daemon is needed to exercise the full path.

## Consequences
- The web tier stays responsive regardless of solve time.
- Job lifecycle (queued -> running -> succeeded/failed) is persisted in `solve_job`
  and observable via the API.
- A real Redis + worker is required in production (`docker compose` will add them);
  the eager mode keeps CI and local dev dependency-free.


