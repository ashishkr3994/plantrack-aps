import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Loading, ErrorState, Pill, Modal, statusTone } from "@/components/ui";
import type { DelayedOrderRow, RecommendationResult } from "@/api/types";

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function fmtDT(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function DelayedOrders() {
  const q = useQuery({ queryKey: ["delayed-orders"], queryFn: api.delayedOrders });
  const [open, setOpen] = useState<DelayedOrderRow | null>(null);

  return (
    <div className="stack">
      <h2>Delayed &amp; critical orders</h2>
      <p className="muted" style={{ margin: 0 }}>
        Every order carrying an open High or Critical deviation. Click one to see why it's
        delayed and get a recommended recovery you can apply directly.
      </p>

      <section className="card">
        <div className="hd">
          Open deviations
          {q.isFetching && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>refreshing…</span>}
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {q.isLoading && <Loading />}
          {q.isError && <ErrorState message="Couldn't load delayed orders." onRetry={() => q.refetch()} />}
          {q.data && q.data.length === 0 && (
            <div className="state">No orders are currently delayed or critical. Nothing needs attention.</div>
          )}
          {q.data && q.data.length > 0 && (
            <table>
              <thead>
                <tr><th>Order</th><th>Customer</th><th>Priority</th><th>Severity</th><th>Milestone</th><th>Root cause</th><th className="num">Deviation</th><th></th></tr>
              </thead>
              <tbody>
                {q.data.map((row, i) => (
                  <tr key={i} style={{ cursor: "pointer" }} onClick={() => setOpen(row)} title="See why and get a recommendation">
                    <td className="mono">{row.order_id}</td>
                    <td>{row.customer}</td>
                    <td><Pill tone={statusTone(row.priority)}>{row.priority}</Pill></td>
                    <td><Pill tone={row.severity === "Critical" ? "risk" : "warn"}>{row.severity}</Pill></td>
                    <td>{row.milestone_name}</td>
                    <td className="muted" style={{ fontSize: 12.5 }}>{row.root_cause_code ?? "—"}</td>
                    <td className="num">{row.deviation_minutes ? `${Math.round(row.deviation_minutes)}m` : "—"}</td>
                    <td style={{ color: "var(--teal)", fontSize: 12 }}>details →</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {open && <DelayDrillDown row={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function DelayDrillDown({ row, onClose }: { row: DelayedOrderRow; onClose: () => void }) {
  const { hasRole } = useAuth();
  const canAct = hasRole("planner");
  const qc = useQueryClient();

  const rec = useQuery({
    queryKey: ["recommend", row.order_id],
    queryFn: () => api.recommendRecovery(row.order_id),
  });

  const [overtimeHrs, setOvertimeHrs] = useState(4);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [mode, setMode] = useState("forward");
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ newDelivery: string | null; onTime: boolean | null } | null>(null);

  const rd: RecommendationResult | undefined = rec.data;

  const applyRecommended = () => {
    if (rd?.recommended_overtime_hrs != null) setOvertimeHrs(rd.recommended_overtime_hrs || 1);
  };

  const apply = async () => {
    setApplyError(null);
    setApplying(true);
    try {
      const res = await api.recoverOrder(row.order_id, {
        overtime: overtimeHrs > 0, overtime_hrs: overtimeHrs,
        overtime_from: from || null, overtime_to: to || null,
        mode, time_budget_s: 15,
      });
      if (!res.feasible) {
        setApplyError(res.message ?? "No feasible recovery with these options.");
      } else {
        setApplied({ newDelivery: res.new_delivery ?? null, onTime: res.on_time ?? null });
        qc.invalidateQueries({ queryKey: ["delayed-orders"] });
        qc.invalidateQueries({ queryKey: ["kpis"] });
        qc.invalidateQueries({ queryKey: ["watchlist"] });
      }
    } catch (e) {
      setApplyError(e instanceof ApiError ? e.message : "Recovery failed.");
    } finally {
      setApplying(false);
    }
  };

  return (
    <Modal title={`Why ${row.order_id} is ${row.severity.toLowerCase()}`} onClose={onClose}
      footer={<button className="primary" onClick={onClose}>Close</button>}>
      <div className="stack">
        <div>
          <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--teal)", marginBottom: 6 }}>Order & status</div>
          <table><tbody>
            <tr><td className="muted" style={{ width: "40%" }}>Customer</td><td>{row.customer}</td></tr>
            <tr><td className="muted">Priority</td><td><Pill tone={statusTone(row.priority)}>{row.priority}</Pill></td></tr>
            <tr><td className="muted">Committed delivery</td><td>{fmtDate(row.committed_delivery_date)}</td></tr>
            <tr><td className="muted">Milestone affected</td><td>{row.milestone_name}</td></tr>
            <tr><td className="muted">Root cause</td><td>{row.root_cause_code ?? "—"}</td></tr>
            <tr><td className="muted">Deviation</td><td>{row.deviation_minutes ? `${Math.round(row.deviation_minutes)} min` : "—"}</td></tr>
            <tr><td className="muted">Detected</td><td>{fmtDT(row.generated_at)}</td></tr>
          </tbody></table>
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--teal)", marginBottom: 6 }}>Recommended action</div>
          {rec.isLoading && <Loading label="Computing recommendation…" />}
          {rec.isError && <div className="banner err">Couldn't compute a recommendation.</div>}
          {rd && (
            <div className={`banner ${rd.projected_on_time ? "ok" : rd.feasible ? "warn" : "err"}`}>
              {rd.message}
              {rd.feasible && rd.recommended_overtime_hrs != null && rd.recommended_overtime_hrs > 0 && (
                <div style={{ marginTop: 8 }}>
                  <button className="ghost" onClick={applyRecommended}>
                    Use recommended {rd.recommended_overtime_hrs}h/day →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--teal)", marginBottom: 6 }}>Recover this order</div>
          {!canAct && <div className="banner err">Requires the planner role.</div>}
          <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ width: 140 }}>
              <label>Overtime hrs/day</label>
              <input type="number" min={0} max={12} value={overtimeHrs} disabled={!canAct}
                onChange={(e) => setOvertimeHrs(Number(e.target.value))} />
            </div>
            <div style={{ width: 150 }}>
              <label>Apply from</label>
              <input type="date" value={from} disabled={!canAct} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div style={{ width: 150 }}>
              <label>Apply to</label>
              <input type="date" value={to} disabled={!canAct} onChange={(e) => setTo(e.target.value)} />
            </div>
            <div style={{ width: 170 }}>
              <label>Mode</label>
              <select value={mode} disabled={!canAct} onChange={(e) => setMode(e.target.value)}>
                <option value="forward">Forward</option>
                <option value="backward">Backward</option>
              </select>
            </div>
            <button className="primary" onClick={apply} disabled={!canAct || applying}>
              {applying ? "Applying…" : "Apply recovery"}
            </button>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The date range is recorded with the recovery for reference; the solver applies the
            overtime uplift for this targeted solve (see Reschedule history for details).
          </p>
          {applyError && <div className="banner err">{applyError}</div>}
          {applied && (
            <div className="banner ok">
              Recovery applied. New delivery: <strong>{fmtDate(applied.newDelivery)}</strong>
              {" "}— {applied.onTime ? "now on time." : "still late; consider a different lever."}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
