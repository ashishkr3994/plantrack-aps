import { useState } from "react";
import { useOrders } from "@/hooks/queries";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Loading, Pill } from "@/components/ui";
import type { SandboxOverride, SandboxResult } from "@/api/types";

interface Row extends SandboxOverride {
  _key: number;
}

export function Sandbox() {
  const { hasRole } = useAuth();
  const canRun = hasRole("planner");
  const orders = useOrders();

  const [rows, setRows] = useState<Row[]>([]);
  const [mode, setMode] = useState("forward");
  const [budget, setBudget] = useState(15);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const addRow = () =>
    setRows((r) => [...r, { _key: Date.now() + Math.random(), order_id: "", exclude: false }]);
  const updateRow = (key: number, patch: Partial<Row>) =>
    setRows((r) => r.map((x) => (x._key === key ? { ...x, ...patch } : x)));
  const removeRow = (key: number) => setRows((r) => r.filter((x) => x._key !== key));

  const run = async () => {
    setError(null);
    setResult(null);
    const overrides: SandboxOverride[] = rows
      .filter((r) => r.order_id)
      .map((r) => ({
        order_id: r.order_id,
        qty: r.qty ? Number(r.qty) : undefined,
        priority: r.priority || undefined,
        committed_due_dt: r.committed_due_dt || undefined,
        exclude: r.exclude || undefined,
      }));
    setBusy(true);
    try {
      const res = await api.simulate({ overrides, mode, time_budget_s: budget });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
      <div className="stack">
      <div className="spread">
        <h2>What-if sandbox</h2>
        <Pill tone="info">Simulation only — live plan untouched</Pill>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Try changes against a copy of the live plan and compare the outcome before
        committing. Adjust an order's quantity, priority, or due date, or exclude it
        entirely, then run the optimiser. Nothing here changes the real schedule.
      </p>

      {!canRun && <div className="banner err">Running simulations requires the planner role.</div>}

      <section className="card">
        <div className="hd">
          Scenario overrides
          <button className="ghost" onClick={addRow} disabled={!canRun}>Add override</button>
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {orders.isLoading && <Loading />}
          {rows.length === 0 && (
            <div className="state">No overrides — running now would just re-solve the live plan as a baseline. Add an override to explore a change.</div>
          )}
          {rows.length > 0 && (
            <table>
              <thead>
                <tr><th>Order</th><th>New qty</th><th>Priority</th><th>New due date</th><th>Exclude</th><th></th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r._key}>
                    <td style={{ minWidth: 180 }}>
                      <select value={r.order_id} onChange={(e) => updateRow(r._key, { order_id: e.target.value })}>
                        <option value="">Select order…</option>
                        {orders.data?.map((o) => (
                          <option key={o.order_id} value={o.order_id}>{o.order_id} — {o.customer}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ width: 110 }}>
                      <input type="number" min={1} placeholder="—" value={r.qty ?? ""} disabled={r.exclude}
                        onChange={(e) => updateRow(r._key, { qty: e.target.value ? Number(e.target.value) : null })} />
                    </td>
                    <td style={{ width: 120 }}>
                      <select value={r.priority ?? ""} disabled={r.exclude}
                        onChange={(e) => updateRow(r._key, { priority: e.target.value || null })}>
                        <option value="">unchanged</option>
                        <option value="HIGH">HIGH</option><option value="MED">MED</option><option value="LOW">LOW</option>
                      </select>
                    </td>
                    <td style={{ width: 160 }}>
                      <input type="date" value={r.committed_due_dt ?? ""} disabled={r.exclude}
                        onChange={(e) => updateRow(r._key, { committed_due_dt: e.target.value || null })} />
                    </td>
                    <td style={{ width: 70, textAlign: "center" }}>
                      <input type="checkbox" style={{ width: "auto" }} checked={!!r.exclude}
                        onChange={(e) => updateRow(r._key, { exclude: e.target.checked })} />
                    </td>
                    <td style={{ width: 40 }}>
                      <button className="ghost danger" onClick={() => removeRow(r._key)}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="card">
        <div className="bd row" style={{ gap: 16, alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label>Scheduling mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={!canRun}>
              <option value="forward">Forward (earliest finish)</option>
              <option value="backward">Backward (from due dates)</option>
            </select>
          </div>
          <div style={{ width: 180 }}>
            <label>Time budget (seconds)</label>
            <input type="number" min={5} max={60} value={budget} disabled={!canRun}
              onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
          <button className="primary" onClick={run} disabled={!canRun || busy}>
            {busy ? "Simulating…" : "Run simulation"}
          </button>
        </div>
      </section>

      {error && <div className="banner err">{error}</div>}
      {busy && <div className="banner live"><span className="spinner" /> &nbsp;Running the optimiser on a copy of the plan…</div>}

      {result && <Comparison result={result} />}
    </div>
  );
}

function Comparison({ result }: { result: SandboxResult }) {
  const changed = result.orders.filter((o) => o.changed);
  return (
    <div className="stack">
      <section className="card">
        <div className="hd">Baseline vs scenario</div>
        <div className="bd" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Metric</th><th className="num">Baseline (live)</th><th className="num">Scenario</th><th>Change</th></tr></thead>
            <tbody>
              <MetricRow label="Orders on time" base={`${result.baseline.orders_on_time}/${result.baseline.orders_total}`} scen={`${result.scenario.orders_on_time}/${result.scenario.orders_total}`} better={result.scenario.orders_on_time >= result.baseline.orders_on_time} />
              <MetricRow label="Weighted tardiness" base={result.baseline.weighted_tardiness} scen={result.scenario.weighted_tardiness} better={result.scenario.weighted_tardiness <= result.baseline.weighted_tardiness} />
              <MetricRow label="Makespan (min)" base={result.baseline.makespan ?? "—"} scen={result.scenario.makespan ?? "—"} better={(result.scenario.makespan ?? 0) <= (result.baseline.makespan ?? 0)} />
              <tr>
                <td>Feasible</td>
                <td className="num"><Pill tone={result.baseline.feasible ? "ok" : "risk"}>{result.baseline.feasible ? "yes" : "no"}</Pill></td>
                <td className="num"><Pill tone={result.scenario.feasible ? "ok" : "risk"}>{result.scenario.feasible ? "yes" : "no"}</Pill></td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="hd">Orders affected ({changed.length})</div>
        <div className="bd" style={{ padding: 0 }}>
          {changed.length === 0 ? (
            <div className="state">No order's lateness changed under this scenario.</div>
          ) : (
            <table>
              <thead><tr><th>Order</th><th>Status</th><th className="num">Baseline late (min)</th><th className="num">Scenario late (min)</th></tr></thead>
              <tbody>
                {changed.map((o) => (
                  <tr key={o.order_id}>
                    <td className="mono">{o.order_id}</td>
                    <td><Pill tone={o.on_time ? "ok" : "risk"}>{o.on_time ? "on time" : "late"}</Pill></td>
                    <td className="num">{o.baseline_lateness_min ?? "—"}</td>
                    <td className="num">{o.lateness_min}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
      <p className="muted" style={{ fontSize: 12 }}>{result.note}</p>
    </div>
  );
}

function MetricRow({ label, base, scen, better }: { label: string; base: React.ReactNode; scen: React.ReactNode; better: boolean }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{base}</td>
      <td className="num"><strong>{scen}</strong></td>
      <td><Pill tone={better ? "ok" : "warn"}>{better ? "same or better" : "worse"}</Pill></td>
    </tr>
  );
}

