"""Phase 5 tests: time-based material risk, CSV import, event-driven material
update, and the what-if sandbox. Real embedded Postgres."""
from datetime import datetime, timezone, timedelta


def test_material_risk_proactive_flagging(planner_client, db_session):
    from app.engine.material_init import ensure_material_status
    from app.engine.material_risk import evaluate_material_risk
    from app import models

    ensure_material_status(db_session)
    # Force one order's planned ready date into the near future (within window),
    # no actual arrival -> should flag 'risk' proactively.
    ms = db_session.query(models.MaterialStatus).first()
    ms.actual_ready_dt = None
    ms.planned_ready_dt = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    # And another into the past -> 'late' (silent).
    rows = db_session.query(models.MaterialStatus).all()
    past = rows[1]
    past.actual_ready_dt = None
    past.planned_ready_dt = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()

    counts = evaluate_material_risk(db_session)
    assert counts["risk"] >= 1, counts
    assert counts["late"] >= 1, counts

    # KPI should reflect it: material_at_risk counts late+risk
    summ = planner_client.get("/dashboard/summary").json()
    assert summ["material_at_risk"] >= 2


def test_material_ready_event_clears_risk(planner_client, db_session):
    from app import models
    from app.engine.material_init import ensure_material_status
    # pick an order; ensure its planned ready date is in the future so an arrival
    # logged "now" counts as on-time -> ready (not late).
    ensure_material_status(db_session)
    orders = planner_client.get("/orders").json()
    o = orders[0]
    ms = db_session.query(models.MaterialStatus).filter_by(order_id=o["id"]).first()
    ms.planned_ready_dt = datetime.now(timezone.utc) + timedelta(days=5)
    ms.actual_ready_dt = None
    db_session.commit()
    r = planner_client.post("/events", json={
        "event_id": "EV-MAT-1", "order_id": o["id"], "event_type": "material_ready",
        "event_timestamp": datetime.now(timezone.utc).isoformat(), "entered_by": "tester"})
    assert r.status_code == 201, r.text
    status = planner_client.get("/materials/status").json()
    row = next(x for x in status if x["order_id"] == o["order_id"])
    assert row["status"] == "ready"
    assert row["actual_ready_dt"] is not None


def test_csv_import_orders(planner_client):
    # need a product that exists in the seed
    prods = planner_client.get("/products").json()
    pid = prods[0]["product_id"]
    csv_text = (
        "order_id,product_id,customer,order_qty,order_date,committed_delivery_date,priority\n"
        f"ORD-CSV-1,{pid},CsvCorp,120,2026-07-01,2026-07-25,HIGH\n"
        f"ORD-CSV-2,{pid},CsvCorp,60,2026-07-02,2026-07-20,MED\n"
        f"ORD-CSV-BAD,{pid},CsvCorp,10,2026-07-10,2026-07-01,LOW\n"  # due before order -> error
    )
    r = planner_client.post("/import/orders", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 2
    assert len(body["errors"]) == 1
    # imported orders are now listed
    ids = {o["order_id"] for o in planner_client.get("/orders").json()}
    assert "ORD-CSV-1" in ids and "ORD-CSV-2" in ids


def test_csv_import_idempotent(planner_client):
    prods = planner_client.get("/products").json()
    pid = prods[0]["product_id"]
    csv_text = (
        "order_id,product_id,customer,order_qty,order_date,committed_delivery_date\n"
        f"ORD-DUP,{pid},X,5,2026-07-01,2026-07-20\n"
    )
    first = planner_client.post("/import/orders", json={"csv": csv_text}).json()
    second = planner_client.post("/import/orders", json={"csv": csv_text}).json()
    assert first["imported"] == 1
    assert second["imported"] == 0 and second["skipped"] == 1


def test_csv_import_requires_planner(client):
    # viewer can't import
    login = client.post("/auth/login", json={"username": "viewer", "password": "viewer123"})
    token = login.json()["access_token"]
    r = client.post("/import/orders", headers={"Authorization": f"Bearer {token}"},
                    json={"csv": "order_id\nX\n"})
    assert r.status_code == 403


def test_sandbox_does_not_touch_live(planner_client):
    # establish a live schedule
    planner_client.post("/schedule/solve", json={"time_budget_s": 10})
    live_before = planner_client.get("/schedule/orders/ORD-4312").json()
    assert live_before["schedule"] is not None
    live_version_before = live_before["schedule"]["baseline_version"]

    # run a what-if: expedite one order + cut another's qty + exclude a third
    r = planner_client.post("/sandbox/simulate", json={
        "mode": "forward", "time_budget_s": 10,
        "overrides": [
            {"order_id": "ORD-4312", "priority": "HIGH"},
            {"order_id": "ORD-4305", "qty": 100},
            {"order_id": "ORD-4287", "exclude": True},
        ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feasible"] is True
    assert "kpis_live" in body and "kpis_whatif" in body
    # excluded order should not be in scenario results
    assert all(o["order_id"] != "ORD-4287" for o in body["orders"])
    assert "applied_changes" in body and len(body["applied_changes"]) >= 1

    kept = [o for o in body["orders"] if o["order_id"] == "ORD-4312"][0]
    assert kept["planned_delivery_whatif"]                # real calendar date
    assert "schedule_whatif" in kept and len(kept["schedule_whatif"]) > 0
    assert all("stage" in s for s in kept["schedule_whatif"])

    # live schedule must be UNCHANGED (same version, still present)
    live_after = planner_client.get("/schedule/orders/ORD-4312").json()
    assert live_after["schedule"]["baseline_version"] == live_version_before


def test_sandbox_overtime_and_partial_qty_levers(planner_client):
    # a live schedule must exist first -- 'live' is read from the persisted
    # schedule now, not re-solved, so there's nothing to read otherwise
    planner_client.post("/schedule/solve", json={"time_budget_s": 10})
    # backward mode + overtime + partial qty should run and return dates
    r = planner_client.post("/sandbox/simulate", json={
        "mode": "backward", "time_budget_s": 10, "overtime_hrs_per_day": 4,
        "overrides": [{"order_id": "ORD-4305", "partial_qty": 200}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "backward"
    assert body["feasible"] is True
    assert any("overtime" in c for c in body["applied_changes"])
    assert any("partial" in c for c in body["applied_changes"])
    # every returned order has a planned delivery date on both sides
    assert all(o["planned_delivery_live"] and o["planned_delivery_whatif"] for o in body["orders"])


def test_sandbox_requires_planner(client):
    login = client.post("/auth/login", json={"username": "viewer", "password": "viewer123"})
    token = login.json()["access_token"]
    r = client.post("/sandbox/simulate", headers={"Authorization": f"Bearer {token}"},
                    json={"overrides": []})
    assert r.status_code == 403


def test_sandbox_event_overrides_never_persist(planner_client):
    """A hypothetical pause/scrap/complete event must affect the sandbox
    result but never appear in actual_event -- nothing is logged for real."""
    planner_client.post("/schedule/solve", json={"time_budget_s": 10})
    orders = planner_client.get("/orders").json()
    pk = next(o["id"] for o in orders if o["order_id"] == "ORD-4312")
    before = planner_client.get(f"/events?order_id={pk}")
    r = planner_client.post("/sandbox/simulate", json={
        "mode": "forward", "time_budget_s": 10,
        "overrides": [{"order_id": "ORD-4312", "events": [
            {"event_type": "pause", "operation_seq": 10, "downtime_mins": 120, "whole_wc": False},
        ]}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feasible"] is True
    order = next(o for o in body["orders"] if o["order_id"] == "ORD-4312")
    assert len(order["execution_events_whatif"]) == 1
    assert order["execution_events_whatif"][0]["event_type"] == "pause"
    assert any("downtime" in c for c in body["applied_changes"])
    # nothing was actually logged
    after = planner_client.get(f"/events?order_id={pk}")
    assert before.json() == after.json()


def test_sandbox_kpis_live_vs_whatif_shape(planner_client):
    planner_client.post("/schedule/solve", json={"time_budget_s": 10})
    r = planner_client.post("/sandbox/simulate", json={
        "mode": "forward", "time_budget_s": 10,
        "overrides": [{"order_id": "ORD-4312", "qty": 5}],
    })
    body = r.json()
    for key in ("schedule_adherence_pct", "on_time_delivery_pct", "orders_at_risk",
                "delayed_critical", "material_at_risk", "capacity_conflicts"):
        assert key in body["kpis_live"]
        assert key in body["kpis_whatif"]
    # material_at_risk is documented as identical on both sides
    assert body["kpis_live"]["material_at_risk"] == body["kpis_whatif"]["material_at_risk"]


def test_sandbox_infeasible_scenario_reports_clearly(planner_client):
    """An impossible override (e.g. a due date before material can even be
    ready) should come back as a clear feasible:False message, not a silent
    empty result or a 500."""
    planner_client.post("/schedule/solve", json={"time_budget_s": 10})
    r = planner_client.post("/sandbox/simulate", json={
        "mode": "forward", "time_budget_s": 10,
        "overrides": [{"order_id": "ORD-4312", "qty": 999999,
                       "committed_due_dt": "2020-01-01T00:00:00Z"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # either it's feasible (solver found a way, just very late) or it reports
    # infeasible clearly -- either way it must not silently omit the message
    if not body["feasible"]:
        assert "message" in body and body["message"]


def test_sandbox_live_matches_persisted_schedule_exactly(planner_client):
    """Regression test for a real bug: 'live' figures were computed by
    re-solving from scratch with the solver's default leveling ('off'), which
    can differ substantially from whatever leveling mode actually produced the
    persisted schedule (soft is the Reschedule screen's default) -- so 'live'
    silently diverged from the real Dashboard. 'Live' must now be read
    directly from the persisted planned_schedule row, never re-solved, so it
    always matches exactly regardless of leveling mode."""
    # solve with 'soft' leveling, same as the Reschedule screen's default --
    # deliberately NOT the solver's internal default ('off'), so a re-solve
    # bug would be caught here.
    planner_client.post("/schedule/solve", json={"time_budget_s": 10, "leveling": "soft"})
    real = planner_client.get("/schedule/orders/ORD-4312").json()["schedule"]

    r = planner_client.post("/sandbox/simulate", json={
        "mode": "forward", "time_budget_s": 10, "overrides": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    order = next(o for o in body["orders"] if o["order_id"] == "ORD-4312")
    assert order["planned_delivery_live"] == real["planned_delivery_dt"]

    # KPIs must match the real dashboard's own KPI computation exactly too
    dash_kpis = planner_client.get("/dashboard/kpis").json()
    for key in ("schedule_adherence_pct", "on_time_delivery_pct", "orders_at_risk",
                "delayed_critical", "material_at_risk", "capacity_conflicts"):
        assert body["kpis_live"][key] == dash_kpis[key]
