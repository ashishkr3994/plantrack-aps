
#!/usr/bin/env python3
# =====================================================================
#  Validate the SQL schema by executing it against a real (embedded)
#  PostgreSQL instance and asserting the expected objects were created.
#  Used both locally and in CI as a Phase 0/1 gate.
#
#  Run:  python3 scripts/validate_schema.py
#  Deps: pip install pgserver
# =====================================================================

import sys
import os
import tempfile

MIGRATIONS = [os.path.join(os.path.dirname(__file__), "..", "db", "migrations", f)
              for f in ("0001_initial_schema.sql", "0002_solve_jobs.sql", "0003_auth_audit_stale.sql", "0004_solver_eligibility_setup.sql", "0005_auth_hardening.sql")]

EXPECTED_TABLES = {
    "plant", "plant_calendar", "lead_time_master", "alert_threshold",
    "routing", "routing_operation", "product", "bom_line",
    "order_header", "planned_schedule", "order_operation", "solve_job",
    "material_status", "actual_event", "deviation_log", "alert_log",
    "capacity_load", "reschedule_log", "app_user", "audit_log",
}
EXPECTED_VIEWS = {
    "v_current_schedule", "v_order_watchlist",
    "v_capacity_conflicts", "v_open_alerts",
}


def main():
    try:
        import pgserver
    except ImportError:
        print("pgserver not installed. `pip install pgserver`")
        sys.exit(2)

    data_dir = tempfile.mkdtemp(prefix="pgdata_validate_")
    srv = pgserver.get_server(data_dir)
    try:
        for m in MIGRATIONS:
            srv.psql(open(m).read())

        def names(query):
            out = srv.psql(query).strip().splitlines()
            # strip header + separator + trailing count line
            body = [ln.strip() for ln in out[2:] if ln.strip()
                    and not ln.strip().startswith("(")]
            return set(body)

        tables = names("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;")
        views = names("SELECT viewname FROM pg_views WHERE schemaname='public' ORDER BY 1;")

        ok = True
        missing_t = EXPECTED_TABLES - tables
        missing_v = EXPECTED_VIEWS - views
        if missing_t:
            ok = False
            print(f"❌ missing tables: {sorted(missing_t)}")
        if missing_v:
            ok = False
            print(f"❌ missing views: {sorted(missing_v)}")

        if ok:
            print(f"✅ schema valid: {len(tables)} tables, {len(views)} views created")
            print(f"   tables: {', '.join(sorted(tables))}")
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print("❌ schema failed to execute:")
        print(e)
        sys.exit(1)
    finally:
        srv.cleanup()


if __name__ == "__main__":
    main()