# 15. Deployment hardening

**Status:** Accepted

## Context
The system was functionally complete but built/verified in a controlled
environment: a hardcoded JWT secret, minimal auth, raw-SQL migrations, a basic
dev Dockerfile, wildcard CORS, and a single health check. None of that is safe to
expose to real users over a network.

## Decisions
- **Fail-fast production config** (`config.py`): central settings with an
  environment flag; `enforce_production_safety()` aborts startup if the secret is
  the dev default, CORS is wildcard, or the DB URL is the dev one.
- **Token model:** short-lived access JWTs (30 min) + opaque, hashed, revocable
  refresh tokens (14 days). `/auth/refresh`, `/auth/logout`. The frontend
  transparently refreshes on a 401 and signs out if that fails.
- **Brute-force defences:** account lockout after N failed logins (cooldown) and a
  per-IP login rate limiter. Both env-tunable.
- **Password change** with refresh-token revocation.
- **Probes:** `/health` (cheap liveness) split from `/ready` (DB-backed readiness,
  503 when down) for correct load-balancer / orchestrator behaviour.
- **Alembic:** wraps the existing raw-SQL migrations as forward-only revisions
  (each executes its `.sql`), giving versioned, ordered, automatable migrations
  without rewriting working SQL. Runs on API container start.
- **Containerisation:** one production image (`Dockerfile.prod`, non-root,
  gunicorn) with an entrypoint selecting api/worker/beat/migrate; a
  `docker-compose.prod.yml` wiring Postgres + Redis + the three process types with
  healthchecks and `.env`-sourced secrets.
- **Optional Sentry** via `SENTRY_DSN`.

## Consequences
- Host-specific concerns (TLS certs, a real secrets manager, database backups, a
  metrics stack) are intentionally NOT in the repo — they depend on the deployment
  target. They're documented in `docs/DEPLOYMENT.md` with the hooks wired
  (Sentry, readiness probe, Redis pub/sub) so they're a configuration step, not a
  code change.
- Alembic downgrades for the baseline migrations are not provided (forward-only +
  restore-from-backup); future schema changes get normal up/down revisions.
- The rate limiter is per-process; multi-worker deployments should move it to Redis.

