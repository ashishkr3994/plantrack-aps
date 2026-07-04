import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Empty, Modal, Pill } from "@/components/ui";

function fmtDate(s: unknown): string {
  if (!s || typeof s !== "string") return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(s);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function fmtDT(s: unknown): string {
  if (!s || typeof s !== "string") return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(s);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function Capacity() {
  const conflicts = useQuery({ queryKey: ["capacity-conflicts"], queryFn: api.capacityConflicts });
  const [cell, setCell] = useState<{ wc: string; date: string } | null>(null);

  return (
    <div className="stack">
      <h2>Capacity</h2>

      <CapacityHeatmapPanel onCell={(wc, date) => setCell({ wc, date })} />

      <section className="card">
        <div className="hd">Work-center conflicts</div>
        <div className="bd" style={{ padding: 0 }}>
          {conflicts.isLoading && <Loading />}
          {conflicts.isError && <ErrorState message="Couldn't load capacity data." onRetry={() => conflicts.refetch()} />}
          {conflicts.data && conflicts.data.length === 0 && (
            <Empty message="No capacity conflicts. Every work-center day is within available minutes." />
          )}
          {conflicts.data && conflicts.data.length > 0 && (
            <table>
              <thead>
                <tr><th>Work center</th><th>Date</th><th className="num">Available (min)</th><th className="num">Demand (min)</th><th className="num">Load %</th></tr>
              </thead>
              <tbody>
                {conflicts.data.map((c, i) => (
                  <tr key={i} style={{ cursor: "pointer" }}
                      onClick={() => setCell({ wc: String(c.work_center), date: String(c.load_date) })}
                      title="Click to see the orders loading this cell">
                    <td>{String(c.work_center)}</td>
                    <td>{fmtDate(c.load_date)}</td>
                    <td className="num">{String(c.available_min)}</td>
                    <td className="num">{String(c.demand_min)}</td>
                    <td className="num">{String(c.load_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {cell && <CellDrillDown wc={cell.wc} date={cell.date} onClose={() => setCell(null)} />}
    </div>
  );
}

function CapacityHeatmapPanel({ onCell }: { onCell: (wc: string, date: string) => void }) {
  const q = useQuery({ queryKey: ["capacity-heatmap"], queryFn: api.capacityHeatmap });
  if (q.isLoading) return <section className="card"><div className="hd">Capacity heatmap</div><div className="bd"><Loading /></div></section>;
  const data = q.data;
  if (!data || data.grid.length === 0) return (
    <section className="card"><div className="hd">Capacity heatmap</div><div className="state">No capacity data yet — run the optimiser to populate it.</div></section>
  );
  const heatColor = (v: number | null) => {
    if (v == null) return "var(--canvas)";
    if (v >= 100) return "rgba(180,35,24,0.85)";
    if (v >= 85) return "rgba(180,105,14,0.75)";
    if (v >= 60) return "rgba(180,105,14,0.35)";
    return "rgba(34,124,78,0.30)";
  };
  return (
    <section className="card">
      <div className="hd">Capacity heatmap — load % by work centre & day (click a cell)</div>
      <div className="bd" style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 2 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Work centre</th>
              {data.dates.map((d) => <th key={d} style={{ fontSize: 10, textAlign: "center" }}>{fmtDate(d)}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.grid.map((row) => (
              <tr key={row.work_center}>
                <td style={{ fontSize: 12, whiteSpace: "nowrap", borderBottom: "none" }}>{row.work_center}</td>
                {row.cells.map((c) => (
                  <td key={c.date}
                      onClick={() => c.load_pct != null && onCell(row.work_center, c.date)}
                      title={`${row.work_center} · ${fmtDate(c.date)} · ${c.load_pct == null ? "no load" : c.load_pct + "%"} — click for detail`}
                      style={{ background: heatColor(c.load_pct), textAlign: "center", fontSize: 10.5, minWidth: 44,
                               color: (c.load_pct ?? 0) >= 85 ? "#fff" : "var(--ink)", borderRadius: 3, border: "none",
                               cursor: c.load_pct != null ? "pointer" : "default",
                               fontWeight: c.overloaded ? 700 : 400 }}>
                    {c.load_pct == null ? "" : `${c.load_pct}`}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 14, marginTop: 12, fontSize: 11.5, color: "var(--ink-2)", flexWrap: "wrap" }}>
          <Legend color="rgba(34,124,78,0.30)" label="< 60%" />
          <Legend color="rgba(180,105,14,0.35)" label="60–85%" />
          <Legend color="rgba(180,105,14,0.75)" label="85–100%" />
          <Legend color="rgba(180,35,24,0.85)" label="≥ 100% (overloaded)" />
        </div>
      </div>
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
    <span style={{ width: 14, height: 14, background: color, borderRadius: 3, display: "inline-block" }} /> {label}
  </span>;
}

function CellDrillDown({ wc, date, onClose }: { wc: string; date: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["capacity-cell", wc, date], queryFn: () => api.capacityCell(wc, date) });
  const d = q.data;
  return (
    <Modal title={`${wc} — ${fmtDate(date)}`} onClose={onClose} footer={<button className="primary" onClick={onClose}>Close</button>}>
      {q.isLoading && <Loading label="Loading cell detail…" />}
      {d && (
        <div className="stack">
          {d.load && (
            <div className="banner info">
              Load <strong>{d.load.load_pct}%</strong> — {d.load.demand_min} of {d.load.available_min} available minutes
              {d.load.overloaded && <Pill tone="risk">overloaded</Pill>}
            </div>
          )}
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            Orders whose operations load this work centre on this day:
          </p>
          {d.operations.length === 0 ? (
            <Empty message="No operations found for this cell." />
          ) : (
            <table>
              <thead><tr><th>Order</th><th>Customer</th><th>Priority</th><th className="num">Op</th><th className="num">Mins</th><th>Window</th></tr></thead>
              <tbody>
                {d.operations.map((op, i) => (
                  <tr key={i}>
                    <td className="mono">{op.order_id}</td>
                    <td>{op.customer}</td>
                    <td><Pill tone={op.priority === "HIGH" ? "risk" : op.priority === "MED" ? "warn" : "muted"}>{op.priority}</Pill></td>
                    <td className="num">{op.operation_seq}</td>
                    <td className="num">{Math.round(op.duration_mins)}</td>
                    <td style={{ fontSize: 12 }}>{fmtDT(op.planned_start)} → {fmtDT(op.planned_end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted" style={{ fontSize: 12 }}>
            To relieve this cell, use Reschedule → single-order recovery (add overtime or shift a partial quantity).
          </p>
        </div>
      )}
    </Modal>
  );
}
