# Architecture Decision Records (ADRs)

This directory captures the significant architecture decisions for the PlanTrack APS
product, so the rationale is preserved for anyone who joins the project.

Each ADR follows a short, standard format: **Context → Decision → Consequences**, plus a
**Status** (Proposed / Accepted / Superseded).

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-database-postgresql.md) | Use PostgreSQL as the primary datastore | Accepted |
| [0003](0003-backend-fastapi-python.md) | Use Python + FastAPI for the backend | Accepted |
| [0004](0004-optimization-ortools-cpsat.md) | Use OR-Tools CP-SAT for scheduling | Accepted |
| [0005](0005-frontend-react-typescript.md) | Use React + TypeScript for the frontend | Accepted |
| [0006](0006-repository-structure.md) | Monorepo structure and layout | Accepted |
| [0007](0007-scheduling-strategy-horizon-decomposition.md) | Horizon + decomposition scheduling strategy | Accepted |
| [0008](0008-async-solve-celery.md) | Run scheduling solves asynchronously (Celery + Redis) | Accepted |
| [0009](0009-frontend-data-and-realtime.md) | Frontend data layer and real-time updates | Accepted |
| [0010](0010-auth-rbac-audit.md) | Authentication, role-based access, and audit | Accepted |
| [0011](0011-phase5-import-events-risk-sandbox.md) | Phase 5 — import, events, material risk, sandbox | Accepted |
| [0012](0012-deviation-alert-engine.md) | Server-side deviation & alert engine + capacity load | Accepted |
| [0013](0013-solver-eligibility-setup-warmstart.md) | Solver: eligibility, sequence-dependent setup, warm start, explainability | Accepted |
| [0014](0014-live-updates-scheduler-recovery.md) | Live updates wiring, periodic scheduler, single-order recovery, UI conveniences | Accepted |
| [0015](0015-deployment-hardening.md) | Deployment hardening (secrets, tokens, lockout, probes, Alembic, containers) | Accepted |

## Why ADRs

Decisions like "which database" or "which solver" are expensive to reverse and easy to
forget the reasoning behind. A one-page record per decision means new contributors can
understand *why* the system is built the way it is, and we can revisit a decision
deliberately (by superseding its ADR) rather than by accident.