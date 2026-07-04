import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSolve } from "@/hooks/useSolve";
import { useOrders } from "@/hooks/queries";
import { Pill } from "@/components/ui";
import type { SchedMode, RecoveryResult } from "@/api/types";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

export function Reschedule() {
  const solve = useSolve();
  const { hasRole } = useAuth();
  const canSolve = hasRole("planner");
  const [mode, setMode] = useState<SchedMode>("forward");
  const [budget, setBudget] = useState(30);

  return (
    <div className="stack">
      <h2>Reschedule / optimise</h2>

      <section className="card">
        <div className="hd">Run the optimiser</div>
        <div className="bd stack">
          <p className="muted" style={{ margin: 0 }}>
            Generates an optimised, capacity-feasible schedule across all open orders using
            the CP-SAT engine. The solve runs in the background — you'll see progress here and
            connected planners are notified when it finishes.
          </p>
          <div className="row" style={{ gap: 16 }}>
            <div style={{ width: 220 }}>
              <label>Scheduling mode</label>
              <select value={mode} onChange={(e) => setMode(e.target.value as SchedMode)} disabled={solve.busy}>
                <option value="forward">Forward (earliest finish)</option>
                <option value="backward">Backward (from due dates)</option>
              </select>
            </div>
            <div style={{ width: 220 }}>
              <label>Time budget (seconds)</label>
              <input
                type="number" min={5} max={120} value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                disabled={solve.busy}
              />
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              {!canSolve ? (
                <button disabled title="Requires planner role">Run optimiser</button>
              ) : !solve.busy ? (
                <button className="primary" onClick={() => solve.start({ mode, time_budget_s: budget })}>
                  Run optimiser
                </button>
              ) : (
                <button disabled>Solving…</button>
              )}
            </div>
          </div>

          <SolveProgress solve={solve} />
        </div>
      </section>

      <RecoveryPanel canRun={canSolve} />
    </div>
  );
}

function SolveProgress({ solve }: { solve: ReturnType<typeof useSolve> }) {
  const { phase, job, error, elapsed } = solve;
  if (phase === "idle") return null;

  if (phase === "queued" || phase === "running") {
    return (
      <div className="banner live">
        <span className="spinner" /> &nbsp;
        {phase === "queued" ? "Queued — starting solver…" : "Solving…"}{" "}
        <span className="mono">{elapsed}s elapsed</span>
        <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
          You can keep working; this runs in the background.
        </div>
      </div>
    );
  }

  if (phase === "failed") {
    return (
      <div className="banner err">
        Solve failed: {error ?? "unknown error"}.{" "}
        <button className="ghost" onClick={solve.reset}>Dismiss</button>
      </div>
    );
  }

  // succeeded
  const r = job?.result;
  return (
    <div className="banner ok">
      <div className="spread">
        <strong>Schedule updated.</strong>
        <button className="ghost" onClick={solve.reset}>Dismiss</button>
      </div>
      {r && (
        <div className="row" style={{ gap: 18, marginTop: 8, flexWrap: "wrap" }}>
          <Metric label="Status" value={r.status} />
          <Metric label="On time" value={`${r.orders_on_time}/${r.orders_total}`} />
          <Metric label="Weighted tardiness" value={String(r.weighted_tardiness)} />
          <Metric label="Makespan (min)" value={r.makespan == null ? "—" : String(r.makespan)} />
          <Metric label="Solve time" value={`${r.wall_time_s}s`} />
          <Pill tone={r.feasible ? "ok" : "risk"}>{r.feasible ? "Feasible" : "Infeasible"}</Pill>
        </div>
      )}
      {r && r.bottleneck_machine && (
        <div style={{ marginTop: 10, fontSize: 13 }}>
          <span className="muted">Bottleneck: </span>
          <strong>{r.bottleneck_machine}</strong>
          {r.machine_load_min && Object.keys(r.machine_load_min).length > 0 && (
            <span className="muted"> · busiest machines: {Object.entries(r.machine_load_min).slice(0, 3).map(([m, v]) => `${m} (${v}m)`).join(", ")}</span>
          )}
        </div>
      )}
      {r && r.late_orders && r.late_orders.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          <div className="muted" style={{ marginBottom: 4 }}>Why some orders are late:</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {r.late_orders.slice(0, 8).map((lo) => (
              <li key={lo.order_id}><span className="mono">{lo.order_id}</span> — {lo.reason ?? "late"}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="muted" style={{ fontSize: 12 }}>{label}: </span>
      <strong className="mono">{value}</strong>
    </span>
  );
}

function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function RecoveryPanel({ canRun }: { canRun: boolean }) {
  const qc = useQueryClient();
  const orders = useOrders();
  const [orderId, setOrderId] = useState("");
  const [overtime, setOvertime] = useState(false);
  const [overtimeHrs, setOvertimeHrs] = useState(4);
  const [partial, setPartial] = useState(false);
  const [partialQty, setPartialQty] = useState<number | "">("");
  const [mode, setMode] = useState("forward");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RecoveryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const log = useQuery({
    queryKey: ["reschedule-log", orderId],
    queryFn: () => api.rescheduleLog(orderId),
    enabled: !!orderId,
  });

  const run = async () => {
    setError(null);
    setResult(null);
    if (!orderId) { setError("Pick an order to recover."); return; }
    setBusy(true);
    try {
      const res = await api.recoverOrder(orderId, {
        overtime, overtime_hrs: overtimeHrs,
        partial_qty: partial && partialQty ? Number(partialQty) : null,
        mode, time_budget_s: 15,
      });
      setResult(res);
      qc.invalidateQueries({ queryKey: ["reschedule-log", orderId] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Recovery failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="hd">Single-order recovery</div>
      <div className="bd stack">
        <p className="muted" style={{ margin: 0 }}>
          Recover one order in trouble without re-solving the whole plan. Apply overtime,
          reschedule a partial quantity, or change the scheduling mode. Each recovery saves a
          new schedule version and is logged below.
        </p>

        <div className="row" style={{ gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 240 }}>
            <label>Order</label>
            <select value={orderId} onChange={(e) => { setOrderId(e.target.value); setResult(null); }} disabled={!canRun}>
              <option value="">Select an order…</option>
              {orders.data?.map((o) => (
                <option key={o.order_id} value={o.order_id}>{o.order_id} — {o.customer}</option>
              ))}
            </select>
          </div>
          <div style={{ width: 200 }}>
            <label>Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={!canRun}>
              <option value="forward">Forward (earliest finish)</option>
              <option value="backward">Backward (from due date)</option>
            </select>
          </div>
        </div>

        <div className="row" style={{ gap: 24, flexWrap: "wrap" }}>
          <div className="stack" style={{ gap: 6 }}>
            <label className="row" style={{ gap: 6, fontSize: 13 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={overtime} onChange={(e) => setOvertime(e.target.checked)} disabled={!canRun} />
              Add overtime
            </label>
            {overtime && (
              <div style={{ width: 160 }}>
                <label>Extra hours / day</label>
                <input type="number" min={1} max={12} value={overtimeHrs} onChange={(e) => setOvertimeHrs(Number(e.target.value))} />
              </div>
            )}
          </div>
          <div className="stack" style={{ gap: 6 }}>
            <label className="row" style={{ gap: 6, fontSize: 13 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={partial} onChange={(e) => setPartial(e.target.checked)} disabled={!canRun} />
              Reschedule partial quantity
            </label>
            {partial && (
              <div style={{ width: 160 }}>
                <label>Quantity</label>
                <input type="number" min={1} value={partialQty} onChange={(e) => setPartialQty(e.target.value ? Number(e.target.value) : "")} />
              </div>
            )}
          </div>
        </div>

        <div>
          <button className="primary" onClick={run} disabled={!canRun || busy}>
            {busy ? "Recovering…" : "Generate recovery plan"}
          </button>
        </div>

        {error && <div className="banner err">{error}</div>}
        {result && !result.feasible && (
          <div className="banner err">{result.message ?? "No feasible recovery with these options."}</div>
        )}
        {result && result.feasible && (
          <div className="banner ok">
            <strong>Recovery plan saved (version {result.version}).</strong>{" "}
            Delivery {fmtDate(result.baseline_delivery)} → {fmtDate(result.new_delivery)} ·{" "}
            {result.on_time ? "now on time" : `still late ${Math.round((result.lateness_min ?? 0) / 60)}h`}
            {result.bottleneck ? ` · ${result.bottleneck}` : ""}
          </div>
        )}

        {orderId && log.data && log.data.length > 0 && (
          <div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>Reschedule history for {orderId}</div>
            <table>
              <thead><tr><th className="num">Version</th><th>When</th><th>By</th><th>Options</th><th>Baseline → New delivery</th></tr></thead>
              <tbody>
                {log.data.map((r) => (
                  <tr key={r.version}>
                    <td className="num">{r.version}</td>
                    <td>{r.performed_at ? new Date(r.performed_at).toLocaleString() : "—"}</td>
                    <td className="mono">{r.performed_by ?? "—"}</td>
                    <td className="muted" style={{ fontSize: 12.5 }}>
                      {[
                        (r.options as Record<string, unknown>).overtime ? `overtime ${(r.options as Record<string, unknown>).overtime_hrs}h` : null,
                        (r.options as Record<string, unknown>).partial_qty ? `partial ${(r.options as Record<string, unknown>).partial_qty}` : null,
                        `mode ${(r.options as Record<string, unknown>).mode}`,
                      ].filter(Boolean).join(" · ")}
                    </td>
                    <td>{fmtDate(r.baseline_delivery)} → {fmtDate(r.new_delivery)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
