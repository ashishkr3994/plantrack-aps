"""Session Postgres + per-test clean re-seed + authenticated clients.

Applies all migrations + data seed + user seed. Provides:
  - client:        unauthenticated TestClient
  - planner_client: TestClient with a planner Bearer token
  - admin_client:   TestClient with an admin Bearer token
No mocks - real embedded Postgres.
"""
import os
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
MIGRATIONS = [
    REPO / "db" / "migrations" / "0001_initial_schema.sql",
    REPO / "db" / "migrations" / "0002_solve_jobs.sql",
    REPO / "db" / "migrations" / "0003_auth_audit_stale.sql",
    REPO / "db" / "migrations" / "0004_solver_eligibility_setup.sql",
    REPO / "db" / "migrations" / "0005_auth_hardening.sql",
    REPO / "db" / "migrations" / "0006_dashboard_snapshots.sql",
]
SEED = REPO / "db" / "seeds" / "0001_sample_data.sql"
USER_SEED = REPO / "db" / "seeds" / "0002_users.sql"


@pytest.fixture(scope="session")
def _server():
    import pgserver
    data_dir = "/tmp/_p4_pytest_pg"
    os.makedirs(data_dir, exist_ok=True)
    srv = pgserver.get_server(data_dir)
    try:
        srv.psql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for m in MIGRATIONS:
            srv.psql(m.read_text())
        os.environ["DATABASE_URL"] = srv.get_uri().replace("postgresql://", "postgresql+psycopg://")
        os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"
        srv._seed = SEED.read_text()
        srv._users = USER_SEED.read_text()
        yield srv
    finally:
        srv.cleanup()


@pytest.fixture(autouse=True)
def _clean_state(_server):
    _server.psql("""
        TRUNCATE audit_log, solve_job, reschedule_log, alert_log, deviation_log,
                 capacity_load, actual_event, material_status, order_operation,
                 planned_schedule, order_header, bom_line, product,
                 routing_operation, routing, alert_threshold, lead_time_master,
                 plant_calendar, plant, app_user, changeover_matrix, refresh_token RESTART IDENTITY CASCADE;
    """)
    _server.psql(_server._seed)
    _server.psql(_server._users)
    try:
        from app import ratelimit
        ratelimit._hits.clear()
    except Exception:
        pass
    yield


@pytest.fixture(scope="session")
def client(_server):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _auth_client(username, password):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


@pytest.fixture()
def planner_client(_server):
    return _auth_client("planner", "planner123")


@pytest.fixture()
def admin_client(_server):
    return _auth_client("admin", "admin123")


@pytest.fixture()
def db_session(_server):
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
