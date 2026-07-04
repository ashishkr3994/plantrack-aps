# Deploy PlanTrack free on Render (demo)

This runs the **whole app on one free Render web service** plus a free Postgres
database — no Redis needed. It's meant for demos and trying the system out.

## What "free single-process mode" means
Render's free tier has no Redis, which PlanTrack normally uses for the Celery
worker, the beat scheduler, and WebSocket pub/sub. In single-process mode
(`PLANTRACK_SINGLE_PROCESS=1`):
- solves run **inline** in the web process (no separate worker),
- the deviation / material-risk scan runs on an **in-process timer**,
- live updates use the **in-process** WebSocket hub,
- the built React UI is served by the API itself (one service, same origin).

Everything works; it just runs in one process instead of several.

## Steps
1. Push this repository to GitHub (or GitLab).
2. In Render, choose **New → Blueprint** and select the repo. Render reads
   `render.yaml` and creates the web service + the Postgres database.
3. Wait for the first build (it installs backend deps and builds the frontend).
   On start, the app runs `alembic upgrade head` to create the schema.
4. **Seed demo data + users** (one time): open the service's **Shell** in the
   Render dashboard and run:
   ```bash
   cd backend && python -m app.seed_demo
   ```
   (or psql the two files in `db/seeds/` into the database).
5. Open the service URL. Log in with the demo users
   (admin/admin123, planner/planner123, viewer/viewer123) and change them.

## Known free-tier limits (expected)
- **Spin-down:** the service sleeps after ~15 min idle; the next request takes
  ~1 minute to wake. Normal for free tier.
- **Database expiry:** Render's free Postgres is deleted ~30 days after creation
  (with a grace period to upgrade). Fine for a demo; upgrade the DB (or move to a
  cheap VPS using `docker-compose.prod.yml`) to keep data long-term.
- **Single worker:** one web worker; fine for a couple of users, not for load.

## Moving off free later
Set `PLANTRACK_SINGLE_PROCESS=0`, provide `REDIS_URL`, and run the `worker` and
`beat` process types (see `docker-compose.prod.yml`) for the full multi-process
deployment. No code changes needed — it's all configuration.
