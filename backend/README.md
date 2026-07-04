# backend/ — FastAPI service (Phase 1)

REST API over the PostgreSQL schema, with CRUD for the core entities plus
read-only dashboard endpoints backed by the schema's views.

## Layout
```
app/
  main.py        FastAPI app, CORS, health check, router wiring
  config.py      settings (DATABASE_URL, solver budget) from env
  database.py    SQLAlchemy engine, session, get_db dependency
  models.py      ORM models mapped to the schema (incl. PG enum types)
  schemas.py     Pydantic request/response models
  routers/       products, orders, bom, events, routings, dashboard
  tests/         integration tests (real embedded Postgres + seed)
```

## Endpoints
- `GET /health`, `GET /` — meta
- `GET/POST/PATCH/DELETE /products`
- `GET/POST/PATCH/DELETE /orders`
- `GET/POST/DELETE /bom` (filter `?product_id=`)
- `GET/POST /events` (filter `?product_id=`/`?order_id=`)
- `GET /routings`, `GET /routings/{id}` (nested operations)
- `GET /dashboard/summary | /watchlist | /capacity-conflicts | /open-alerts`
- Interactive docs at `/docs`.

## Run locally
```bash
# 1) a PostgreSQL with schema + seed applied (docker compose up -d db does this)
# 2) start the API:
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://plantrack:plantrack@localhost:5432/plantrack
uvicorn app.main:app --reload
```
Or use Docker for the whole stack: `docker compose up` from the repo root.

## Test
```bash
cd backend
pip install -r requirements.txt pgserver
PYTHONPATH=. pytest app/tests -q   # spins up a real embedded Postgres, no mocks
```

## Not yet (later phases)
- Engine orchestration (calling the CP-SAT solver as async jobs) — Phase 2.
- Auth / roles / audit — Phase 4.