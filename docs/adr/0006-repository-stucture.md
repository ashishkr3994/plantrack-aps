# 6. Monorepo structure and layout

**Status:** Accepted

## Context
The Phase 0/1 deliverables (schema, solver, prototype) started life as standalone files.
A product needs a codebase with a clear layout, history, and a place for each concern.

## Decision
Use a single **monorepo** with top-level directories by concern:

```
plantrack-aps/
  backend/    FastAPI service (API + engine orchestration)
  solver/     OR-Tools CP-SAT model, stress test, unit tests
  frontend/   React app (and the prototype HTML as reference)
  db/
    migrations/  SQL schema migrations (source of truth)
    seeds/       sample/seed data
  docs/
    adr/      architecture decision records
  scripts/    dev/ops helper scripts
  .github/workflows/  CI pipelines
```

Rationale:
- One repo keeps schema, solver, backend, and frontend versioned together, so a change
  that spans layers is a single atomic commit.
- Clear separation of concerns mirrors the architecture (data / engine / API / UI).

## Consequences
- CI runs per-area jobs (solver tests, schema validation, lint) — see `.github/workflows`.
- As the team grows, areas could be split into packages, but a monorepo is right for now.


