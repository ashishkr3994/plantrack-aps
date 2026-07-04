
# PlanTrack — Deployment & Hardening Guide

This describes how to run PlanTrack in production and what hardening is built in
versus what you must provide for your specific host.

## What's built in (code, tested)

- **Fail-fast config safety.** In `PLANTRACK_ENV=production` the app refuses to
  start if the JWT secret is the dev default, if CORS is wildcard, or if the
  database URL still points at the local dev database. (`app/config.py`)
- **Secret from environment.** `PLANTRACK_SECRET_KEY` signs JWTs; never hardcoded.
- **Short-lived access tokens + refresh tokens.** Access tokens default to 30 min;
  refresh tokens (opaque, stored only as SHA-256 hashes) default to 14 days and are
  revocable. `/auth/refresh`, `/auth/logout`.
- **Account lockout + login rate-limiting.** N failed logins lock an account for a
  cooldown; per-IP login rate limit blunts guessing. Tunable via env.
- **Password change** with session revocation (`/auth/change-password`).
- **Liveness vs readiness.** `/health` is cheap (process up); `/ready` checks the
  DB and returns 503 when not ready — wire these to your platform's probes.
- **Alembic migrations.** `alembic upgrade head` applies the schema; runs
  automatically on API container start (see `entrypoint.sh`).
- **Container process types.** One image, four roles via the entrypoint:
  `api` (gunicorn + uvicorn workers, runs migrations first), `worker` (Celery),
  `beat` (periodic deviation scan), `migrate` (migrations only).
- **Production compose** (`docker-compose.prod.yml`): Postgres, Redis, api, worker,
  beat, with healthchecks, restart policies, and secrets from `.env`.
- **Optional Sentry.** Set `SENTRY_DSN` to enable error tracking.

## Quick start

```bash
cp .env.example .env
# edit .env: set a strong PLANTRACK_SECRET_KEY, DB password, and ALLOWED_ORIGINS
python -c "import secrets; print(secrets.token_urlsafe(48))"   # generate a secret
docker compose -f docker-compose.prod.yml up -d --build
```

The API listens on :8000. Put a TLS-terminating reverse proxy in front of it.

## What you must provide for your host (not in this repo)

- **TLS / HTTPS.** Terminate TLS at a reverse proxy (nginx, Caddy) or your cloud
  load balancer; forward to the API on :8000. Never serve auth over plain HTTP.
- **Secrets management.** `.env` is fine for a single VM; for cloud use a secrets
  manager (AWS Secrets Manager, GCP Secret Manager, Vault) and inject as env vars.
- **Database backups.** Schedule `pg_dump`/managed snapshots with a tested restore.
  The app does not manage backups.
- **Monitoring & metrics.** Sentry hook is built in (set `SENTRY_DSN`). For metrics
  (latency, solve times, queue depth) add Prometheus/Grafana around the stack.
- **Default users.** Seed (`db/seeds/0002_users.sql`) creates admin/planner/viewer
  with known passwords for first login. Change them immediately (or don't load the
  seed in production and create the first admin manually). The login screen only
  shows demo credentials in development builds.
- **Scaling.** The login rate-limiter and in-process WebSocket fallback are
  per-process; with multiple web workers set `REDIS_URL` (already wired) so live
  updates use Redis pub/sub, and consider a shared rate-limit store.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PLANTRACK_ENV` | development | `production` enables fail-fast safety checks |
| `PLANTRACK_SECRET_KEY` | (dev default) | JWT signing secret — REQUIRED in prod |
| `PLANTRACK_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins — explicit in prod |
| `DATABASE_URL` | local dev | Postgres connection (SQLAlchemy/psycopg URL) |
| `PLANTRACK_TOKEN_TTL_MIN` | 30 | Access-token lifetime (minutes) |
| `PLANTRACK_REFRESH_TTL_DAYS` | 14 | Refresh-token lifetime (days) |
| `PLANTRACK_MAX_FAILED_LOGINS` | 5 | Failures before lockout |
| `PLANTRACK_LOCKOUT_MINUTES` | 15 | Lockout duration |
| `PLANTRACK_LOGIN_RATE_PER_MIN` | 10 | Login attempts per IP per minute |
| `REDIS_URL` / `CELERY_BROKER_URL` | memory/none | Redis for Celery + WS pub/sub |
| `PLANTRACK_SCAN_INTERVAL_S` | 300 | Periodic deviation-scan interval |
| `SENTRY_DSN` | (none) | Enable Sentry error tracking |
| `WEB_CONCURRENCY` | 3 | Gunicorn worker count |
