import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSummary, useWatchlist } from "@/hooks/queries";
import { api } from "@/api/client";
import { Loading, ErrorState, Pill, statusTone, Modal } from "@/components/ui";

function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

type Drill = "orders" | "alerts" | "capacity" | "material" | null;

export function Dashboard() {
  const summary = useSummary();
  const watch = useWatchlist();
  const [drill, setDrill] = useState<Drill>(null);

  return (
    <div className="stack">
      <section className="grid kpis">
        {summary.isLoading && <Loading label="Loading metrics…" />}
        {summary.isError && (
          <ErrorState message="Couldn't load dashboard metrics." onRetry={() => summary.refetch()} />
        )}
        {summary.data && (
          <>
            <Kpi label="Active orders" value={summary.data.orders} onClick={() => setDrill("orders")} />
            <Kpi label="Products" value={summary.data.products} />
            <Kpi label="Open alerts" value={summary.data.open_alerts} tone={summary.data.open_alerts > 0 ? "alert" : undefined} onClick={() => setDrill("alerts")} />
            <Kpi label="Capacity conflicts" value={summary.data.capacity_conflicts} tone={summary.data.capacity_conflicts > 0 ? "warn" : undefined} onClick={() => setDrill("capacity")} />
            <Kpi label="Material at risk" value={summary.data.material_at_risk} tone={summary.data.material_at_risk > 0 ? "warn" : undefined} onClick={() => setDrill("material")} />
          </>
        )}
      </section>

      <section className="card">
        <div className="hd">
          Order watchlist
          {watch.isFetching && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>refreshing…</span>}
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {watch.isLoading && <Loading />}
          {watch.isError && <ErrorState message="Couldn't load the watchlist." onRetry={() => watch.refetch()} />}
          {watch.data && watch.data.length === 0 && (
            <div className="state">No orders yet.</div>
          )}
          {watch.data && watch.data.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Customer</th>
                  <th className="num">Qty</th>
                  <th>Priority</th>
                  <th>Committed</th>
                  <th>Planned delivery</th>
                  <th className="num">Buffer (h)</th>
                  <th>Material</th>
                  <th>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {watch.data.map((r) => (
                  <tr key={r.order_id}>
                    <td className="mono">{r.order_id}</td>
                    <td>{r.product_name}</td>
                    <td>{r.customer}</td>
                    <td className="num">{r.order_qty}</td>
                    <td><Pill tone={statusTone(r.priority)}>{r.priority}</Pill></td>
                    <td>{fmtDate(r.committed_delivery_date)}</td>
                    <td>{fmtDate(r.planned_delivery_dt)}</td>
                    <td className="num">{r.buffer_hrs == null ? "—" : r.buffer_hrs.toFixed(1)}</td>
                    <td>{r.material_status ? <Pill tone={statusTone(r.material_status)}>{r.material_status}</Pill> : "—"}</td>
                    <td>{r.schedule_status ? <Pill tone={statusTone(r.schedule_status)}>{r.schedule_status}</Pill> : <span className="muted">not scheduled</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {drill && <DrillModal kind={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}

function DrillModal({ kind, onClose }: { kind: Exclude<Drill, null>; onClose: () => void }) {
  const titles = {
    orders: "Active orders",
    alerts: "Open alerts",
    capacity: "Capacity conflicts",
    material: "Material at risk",
  };
  return (
    <Modal title={titles[kind]} onClose={onClose} footer={<button className="primary" onClick={onClose}>Close</button>}>
      {kind === "orders" && <OrdersDrill />}
      {kind === "alerts" && <AlertsDrill />}
      {kind === "capacity" && <CapacityDrill />}
      {kind === "material" && <MaterialDrill />}
    </Modal>
  );
}

function OrdersDrill() {
  const q = useQuery({ queryKey: ["drill-orders"], queryFn: () => api.listOrders() });
  if (q.isLoading) return <Loading />;
  const rows = q.data ?? [];
  if (rows.length === 0) return <div className="state">No orders.</div>;
  return (
    <table>
      <thead><tr><th>Order</th><th>Customer</th><th className="num">Qty</th><th>Priority</th><th>Due</th></tr></thead>
      <tbody>
        {rows.map((o) => (
          <tr key={o.order_id}>
            <td className="mono">{o.order_id}</td><td>{o.customer}</td>
            <td className="num">{o.order_qty}</td><td>{o.priority}</td>
            <td>{fmtDate(o.committed_delivery_date)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AlertsDrill() {
  const q = useQuery({ queryKey: ["drill-alerts"], queryFn: () => api.alerts(false, "open") });
  if (q.isLoading) return <Loading />;
  const rows = q.data ?? [];
  if (rows.length === 0) return <div className="state">No open alerts.</div>;
  return (
    <table>
      <thead><tr><th>Type</th><th>Alert</th><th>Detail</th></tr></thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.dedup_key}>
            <td><Pill tone={a.alert_type === "crit" ? "risk" : "warn"}>{a.alert_type}</Pill></td>
            <td>{a.title}</td><td className="muted" style={{ fontSize: 12.5 }}>{a.meta}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CapacityDrill() {
  const q = useQuery({ queryKey: ["drill-capacity"], queryFn: () => api.capacityConflicts() });
  if (q.isLoading) return <Loading />;
  const rows = q.data ?? [];
  if (rows.length === 0) return <div className="state">No capacity conflicts.</div>;
  return (
    <table>
      <thead><tr><th>Work center</th><th>Date</th><th className="num">Load %</th></tr></thead>
      <tbody>
        {rows.map((c, i) => (
          <tr key={i}>
            <td>{String(c.work_center)}</td>
            <td>{fmtDate(String(c.load_date))}</td>
            <td className="num">{c.load_pct != null ? `${Number(c.load_pct).toFixed(0)}%` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MaterialDrill() {
  const q = useQuery({ queryKey: ["drill-material"], queryFn: () => api.materialStatus() });
  if (q.isLoading) return <Loading />;
  const rows = (q.data ?? []).filter((m) => m.status === "risk" || m.status === "late");
  if (rows.length === 0) return <div className="state">No orders at material risk.</div>;
  return (
    <table>
      <thead><tr><th>Order</th><th>Status</th><th>Planned ready</th><th>Reason</th></tr></thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.order_id}>
            <td className="mono">{m.order_id}</td>
            <td><Pill tone={statusTone(m.status)}>{m.status}</Pill></td>
            <td>{fmtDate(m.planned_ready_dt)}</td>
            <td className="muted">{m.risk_reason ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Kpi({ label, value, tone, onClick }: { label: string; value: number; tone?: "alert" | "warn"; onClick?: () => void }) {
  return (
    <div
      className={`kpi ${tone ?? ""}`}
      onClick={onClick}
      style={onClick ? { cursor: "pointer" } : undefined}
      title={onClick ? "Click to see details" : undefined}
    >
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}
