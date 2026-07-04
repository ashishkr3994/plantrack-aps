# 3. Use Python + FastAPI for the backend

**Status:** Accepted

## Context
We need an API layer between the database and the frontend, exposing CRUD for every
entity and orchestrating the scheduling engine. The single most consequential factor is
that our optimization engine (see ADR 0004) is Python-native (OR-Tools). The backend
language should not force an awkward boundary with the solver.

## Decision
Use **Python with FastAPI** for the backend API.

Rationale:
- Keeps the API and the optimization engine in one language, avoiding a cross-language
  bridge to the solver.
- FastAPI provides typed request/response models (Pydantic), automatic OpenAPI docs,
  async I/O, and high performance.
- Strong ecosystem for data work, testing, and ORM/migration tooling.

Alternatives considered:
- **Node.js/TypeScript** would unify language with the frontend, but the solver is still
  Python, so we would end up calling out to Python anyway — losing the main benefit.

## Consequences
- The backend lives in `backend/`; the solver in `solver/` is imported as a library or
  called as an async job.
- We standardize on Pydantic models that mirror the database entities.
- Heavy solves must run as async jobs (never block a request) — see ADR 0007.


