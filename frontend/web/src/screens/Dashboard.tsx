import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Pill, statusTone, PriorityPill, Modal } from "@/components/ui";
import { fmtDate, fmtDateTime as fmtDT, fmtRelativeTime } from "@/lib/format";

export function Dashboard() {
  const nav = useNavigate();
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: api.kpis });
  const watch = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const [drillOrder, setDrillOrder] = useState<string | null>(null);
  const [drillKey, setDrillKey] = useState<string | null>(null);

  // adherence/OTD color: green >=90, amber >=80, red below (prototype thresholds)
  const pctTone = (v: number | null) => v == null ? undefined : v >= 90 ? "ok" : v >= 80 ? "warn" : "alert";

  return (
    <div className="stack">
      {kpis.data?.last_updated && (
        <div className="muted" style={{ fontSize: 12, marginBottom: -6 }}>
          Schedule last updated {fmtRelativeTime(kpis.data.last_updated)}
        </div>
      )}
      {/* KPI strip - six prototype KPIs, each opens a drill-down of the orders behind it */}
      <section className="grid kpis">
        {kpis.isLoading && <Loading label="Loading metrics..." />}
        {kpis.isError && <ErrorState message="Couldn't load metrics." onRetry={() => kpis.refetch()} />}
        {kpis.data && (
          <>
            <KpiCard label="Schedule adherence"
              value={kpis.data.schedule_adherence_pct == null ? "-" : `${kpis.data.schedule_adherence_pct}%`}
              sub="vs 95% target" tone={pctTone(kpis.data.schedule_adherence_pct)}
              tip="On-track orders divided by total scheduled, against a 95% target. Measures how well the shop is keeping to plan."
              onClick={() => setDrillKey("adherence")} />
            <KpiCard label="On-time delivery"
              value={kpis.data.on_time_delivery_pct == null ? "-" : `${kpis.data.on_time_delivery_pct}%`}
              sub="customer promise" tone={pctTone(kpis.data.on_time_delivery_pct)}
              tip="Orders whose delivery lands on or before the committed date, divided by total. The customer-facing promise metric."
              onClick={() => setDrillKey("otd")} />
            <KpiCard label="Orders at risk" value={kpis.data.orders_at_risk}
              sub={`of ${kpis.data.orders} active`}
              tone={kpis.data.orders_at_risk > 5 ? "alert" : kpis.data.orders_at_risk > 2 ? "warn" : "ok"}
              tip="Every order not fully on track - slipping, buffer-thin, material-blocked or delayed."
              onClick={() => setDrillKey("risk")} />
            <KpiCard label="Delayed / critical" value={kpis.data.delayed_critical}
              sub="need recovery"
              tone={kpis.data.delayed_critical > 3 ? "alert" : kpis.data.delayed_critical > 1 ? "warn" : "ok"}
              tip="Orders slipping past the delay threshold or predicted to breach delivery - the ones needing a recovery action."
              onClick={() => setDrillKey("delayed")} />
            <KpiCard label="Material at risk" value={kpis.data.material_at_risk}
              sub="orders affected"
              tone={kpis.data.material_at_risk > 2 ? "alert" : kpis.data.material_at_risk > 0 ? "warn" : "ok"}
              tip="Orders whose material is late or at risk - procurement delays that can cascade into production."
              onClick={() => setDrillKey("material")} />
            <KpiCard label="Capacity conflicts" value={kpis.data.capacity_conflicts}
              sub="overloaded WC-days"
              tone={kpis.data.capacity_conflicts > 3 ? "alert" : kpis.data.capacity_conflicts > 0 ? "warn" : "ok"}
              tip="Work-centre days where scheduled demand exceeds available minutes. Click to see the Capacity screen."
              onClick={() => nav("/capacity")} />
          </>
        )}
      </section>

      {drillKey && (
        <KpiDrillModal
          drillKey={drillKey}
          onClose={() => setDrillKey(null)}
          onOpenOrder={(oid) => { setDrillKey(null); setDrillOrder(oid); }}
        />
      )}


      {/* Order watchlist with deep drill-down */}
      <section className="card">
        <div className="hd">
          Order watchlist
          {watch.isFetching && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>refreshing...</span>}
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {watch.isLoading && <Loading />}
          {watch.isError && <ErrorState message="Couldn't load the watchlist." onRetry={() => watch.refetch()} />}
          {watch.data && watch.data.length === 0 && <div className="state">No orders yet.</div>}
          {watch.data && watch.data.length > 0 && (
            <table className="roomy">
              <thead>
                <tr>
                  <th>Order</th><th>Product</th><th>Customer</th><th className="num">Qty</th>
                  <th>Priority</th><th>Committed</th><th>Planned delivery</th>
                  <th>Buffer</th><th>Material</th><th>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {watch.data.map((r) => (
                  <tr key={r.order_id} style={{ cursor: "pointer" }} onClick={() => setDrillOrder(r.order_id)}
                      title="Click for full order detail">
                    <td className="mono">{r.order_id}</td>
                    <td>{r.product_name}</td>
                    <td>{r.customer}</td>
                    <td className="num">{r.order_qty}</td>
                    <td><PriorityPill priority={r.priority} /></td>
                    <td>{fmtDate(r.committed_delivery_date)}</td>
                    <td>{fmtDate(r.planned_delivery_dt)}</td>
                    <td><BufferBar hrs={r.buffer_hrs} /></td>
                    <td>{r.material_status ? <Pill tone={statusTone(r.material_status)}>{r.material_status}</Pill> : "-"}</td>
                    <td>{r.schedule_status
                      ? (Number(r.buffer_hrs) < 0
                          ? <Pill tone="risk">Late</Pill>
                          : <Pill tone="ok">On track</Pill>)
                      : <span className="muted">not scheduled</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Three insight panels */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
        <DelayReasonsPanel onOpen={() => nav("/delayed")} />
        <RecoveryPipelinePanel onOpen={() => nav("/reschedule")} />
        <MaterialRiskPanel onOpen={() => nav("/materials")} />
      </div>

      {drillOrder && <OrderDrillDown orderId={drillOrder} onClose={() => setDrillOrder(null)} />}
    </div>
  );
}


function BufferBar({ hrs }: { hrs: unknown }) {
  if (hrs == null || typeof hrs !== "number") return <span className="muted">-</span>;
  const pctVal = Math.max(0, Math.min(100, (hrs / 72) * 100));
  const color = hrs < 12 ? "var(--risk)" : hrs < 36 ? "var(--warn)" : "var(--ok)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div className="buffer-track" style={{ flex: 1 }}>
        <div className="buffer-fill" style={{ width: `${pctVal}%`, background: color }} />
      </div>
      <span style={{ fontSize: 11, color: "var(--ink-2)", minWidth: 34, textAlign: "right" }}>{hrs.toFixed(0)}h</span>
    </div>
  );
}

function DelayReasonsPanel({ onOpen }: { onOpen: () => void }) {
  const q = useQuery({ queryKey: ["delay-reasons"], queryFn: api.delayReasons });
  const rows = q.data ?? [];
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className="card">
      <div className="hd" style={{ cursor: "pointer" }} onClick={onOpen} title="Open reschedule">Delay reasons &rarr;</div>
      <div className="bd">
        {q.isLoading && <Loading />}
        {!q.isLoading && rows.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No open deviations - nothing delayed.</div>}
        {rows.map((r) => (
          <div key={r.root_cause} style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 3 }}>
              <span>{r.root_cause}</span>
              <span className="muted">{r.count} - {r.total_hours}h</span>
            </div>
            <div className="buffer-track"><div className="buffer-fill" style={{ width: `${(r.count / max) * 100}%`, background: "var(--warn)" }} /></div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RecoveryPipelinePanel({ onOpen }: { onOpen: () => void }) {
  const q = useQuery({ queryKey: ["recovery-pipeline"], queryFn: api.recoveryPipeline });
  const rows = q.data ?? [];
  return (
    <section className="card">
      <div className="hd" style={{ cursor: "pointer" }} onClick={onOpen} title="Open reschedule">Recovery pipeline &rarr;</div>
      <div className="bd" style={{ padding: 0 }}>
        {q.isLoading && <Loading />}
        {!q.isLoading && rows.length === 0 && <div className="state" style={{ padding: 24 }}>No recoveries yet.</div>}
        {rows.length > 0 && (
          <table>
            <thead><tr><th>Order</th><th className="num">v</th><th>By</th><th>New delivery</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{String(r.order_id)}</td>
                  <td className="num">{String(r.version)}</td>
                  <td>{String(r.performed_by ?? "-")}</td>
                  <td>{fmtDate(r.new_delivery)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function MaterialRiskPanel({ onOpen }: { onOpen: () => void }) {
  const q = useQuery({ queryKey: ["material-risk-panel"], queryFn: api.materialStatus });
  const rows = (q.data ?? []).filter((m) => m.status === "risk" || m.status === "late");
  return (
    <section className="card">
      <div className="hd" style={{ cursor: "pointer" }} onClick={onOpen} title="Open materials">Material risk &rarr;</div>
      <div className="bd" style={{ padding: 0 }}>
        {q.isLoading && <Loading />}
        {!q.isLoading && rows.length === 0 && <div className="state" style={{ padding: 24 }}>No material risks.</div>}
        {rows.length > 0 && (
          <table>
            <thead><tr><th>Order</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.order_id}>
                  <td className="mono">{m.order_id}</td>
                  <td><Pill tone={statusTone(m.status)}>{m.status}</Pill></td>
                  <td className="muted" style={{ fontSize: 12 }}>{m.risk_reason ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function OrderDrillDown({ orderId, onClose }: { orderId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["order-detail", orderId], queryFn: () => api.orderDetail(orderId) });
  const d = q.data;
  return (
    <Modal title={`Order ${orderId}`} onClose={onClose} footer={<button className="primary" onClick={onClose}>Close</button>}>
      {q.isLoading && <Loading label="Loading order detail..." />}
      {d && (
        <div className="stack" style={{ maxHeight: "70vh", overflowY: "auto" }}>
          {/* Order & status */}
          <Section title="Order & status">
            <KV pairs={[
              ["Customer", str(d.order?.customer)],
              ["Quantity", str(d.order?.order_qty)],
              ["Priority", str(d.order?.priority)],
              ["Product", str(d.product?.name)],
              ["Committed delivery", fmtDate(d.order?.committed_delivery_date)],
              ["Status", str(d.order?.status)],
            ]} />
          </Section>

          {/* Schedule */}
          <Section title="Schedule">
            {d.schedule ? (
              <KV pairs={[
                ["Version", str(d.schedule.baseline_version)],
                ["Material ready", fmtDT(d.schedule.planned_material_ready_dt)],
                ["Production start", fmtDT(d.schedule.planned_prod_start_dt)],
                ["Production end", fmtDT(d.schedule.planned_prod_end_dt)],
                ["Dispatch", fmtDT(d.schedule.planned_dispatch_dt)],
                ["Delivery", fmtDT(d.schedule.planned_delivery_dt)],
                ["Buffer (hrs)", str(d.schedule.buffer_hrs)],
              ]} />
            ) : <Empty text="Not scheduled yet - run the optimiser." />}
          </Section>

          {/* Risk signals */}
          <Section title={`Risk signals detected (${d.risk_signals.length})`}>
            {d.risk_signals.length === 0 ? <Empty text="No deviations detected." /> : (
              <table><thead><tr><th>Milestone</th><th>Severity</th><th>Cause</th><th>Status</th></tr></thead>
                <tbody>{d.risk_signals.map((r, i) => (
                  <tr key={i}>
                    <td>{str(r.milestone_name)}</td>
                    <td><Pill tone={statusTone(str(r.severity))}>{str(r.severity)}</Pill></td>
                    <td className="muted">{str(r.root_cause_code) || "-"}</td>
                    <td>{str(r.resolution_status)}</td>
                  </tr>
                ))}</tbody></table>
            )}
          </Section>

          {/* Operation sequence */}
          <Section title={`Operation sequence (${d.operations.length})`}>
            {d.operations.length === 0 ? <Empty text="No operations." /> : (
              <table><thead><tr><th className="num">Seq</th><th>Work centre</th><th>Start</th><th>End</th><th className="num">Mins</th></tr></thead>
                <tbody>{d.operations.map((op, i) => (
                  <tr key={i}>
                    <td className="num">{str(op.operation_seq)}</td>
                    <td>{str(op.work_center)}</td>
                    <td>{fmtDT(op.planned_start)}</td>
                    <td>{fmtDT(op.planned_end)}</td>
                    <td className="num">{str(op.duration_mins)}</td>
                  </tr>
                ))}</tbody></table>
            )}
          </Section>

          {/* Material & BOM */}
          <Section title={`Material & BOM (${d.bom.length})`}>
            {d.material && (
              <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
                Material status: <Pill tone={statusTone(str(d.material.status))}>{str(d.material.status)}</Pill>
                {d.material.risk_reason ? ` - ${str(d.material.risk_reason)}` : ""}
              </p>
            )}
            {d.bom.length === 0 ? <Empty text="No bill of materials." /> : (
              <table><thead><tr><th>Material</th><th className="num">Qty/unit</th><th>UoM</th><th>Supplier</th><th className="num">Lead days</th></tr></thead>
                <tbody>{d.bom.map((b, i) => (
                  <tr key={i}>
                    <td>{str(b.material)}</td><td className="num">{str(b.qty_per_unit)}</td>
                    <td>{str(b.uom)}</td><td>{str(b.supplier)}</td><td className="num">{str(b.lead_days)}</td>
                  </tr>
                ))}</tbody></table>
            )}
          </Section>

          {/* Execution events */}
          <Section title={`Execution events (${d.events.length})`}>
            {d.events.length === 0 ? <Empty text="No execution events logged." /> : (
              <table><thead><tr><th>Event</th><th>When</th><th className="num">Op</th><th className="num">Qty</th><th>By</th></tr></thead>
                <tbody>{d.events.map((e, i) => (
                  <tr key={i}>
                    <td><Pill tone="info">{str(e.event_type)}</Pill></td>
                    <td>{fmtDT(e.event_timestamp)}</td>
                    <td className="num">{str(e.operation_seq) || "-"}</td>
                    <td className="num">{str(e.event_qty) || "-"}</td>
                    <td className="muted">{str(e.entered_by) || "-"}</td>
                  </tr>
                ))}</tbody></table>
            )}
          </Section>
        </div>
      )}
    </Modal>
  );
}

function str(v: unknown): string {
  if (v == null) return "";
  return String(v);
}
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--teal)", marginBottom: 6, borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>{title}</div>
      {children}
    </div>
  );
}
function KV({ pairs }: { pairs: Array<[string, string]> }) {
  return (
    <table><tbody>
      {pairs.map(([k, v]) => (
        <tr key={k}><td className="muted" style={{ width: "45%" }}>{k}</td><td>{v || "-"}</td></tr>
      ))}
    </tbody></table>
  );
}
function Empty({ text }: { text: string }) {
  return <p className="muted" style={{ fontSize: 12.5, margin: "4px 0" }}>{text}</p>;
}

function KpiCard({ label, value, sub, tone, onClick, tip }: {
  label: string; value: React.ReactNode; sub?: string;
  tone?: "ok" | "warn" | "alert"; onClick?: () => void; tip?: string;
}) {
  const clickHint = onClick ? "Click for the orders behind this metric." : "";
  const title = [tip, clickHint].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`kpi ${tone === "alert" ? "alert" : tone === "warn" ? "warn" : ""}`}
         onClick={onClick} style={onClick ? { cursor: "pointer" } : undefined}
         title={title}>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
      {sub && <div className="l" style={{ opacity: 0.6, fontSize: 11 }}>{sub}</div>}
    </div>
  );
}

function ReasonChip({ type, text }: { type: string; text: string }) {
  // color by reason type, mirroring the prototype's risk-reason chips
  const bg: Record<string, string> = {
    time: "var(--risk-bg, #fde8e8)", buffer: "#efe7fb",
    material: "rgba(245,158,11,0.18)", capacity: "#e6efff",
  };
  const fg: Record<string, string> = {
    time: "var(--risk, #c0392b)", buffer: "#7c3aed",
    material: "#b45309", capacity: "#2563eb",
  };
  return (
    <span style={{
      display: "inline-block", fontSize: 11, padding: "1px 7px", borderRadius: 8,
      margin: "1px 2px", background: bg[type] || "#eee", color: fg[type] || "#333",
    }}>{text}</span>
  );
}

function KpiDrillModal({ drillKey, onClose, onOpenOrder }: {
  drillKey: string; onClose: () => void; onOpenOrder: (oid: string) => void;
}) {
  const q = useQuery({ queryKey: ["kpi-drill", drillKey], queryFn: () => api.kpiDrilldown(drillKey) });
  const isCapacity = drillKey === "capacity";
  return (
    <Modal title={q.data?.title || "Loading..."} onClose={onClose} size="lg">
      {q.data?.subtitle && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{q.data.subtitle}</div>}
      {q.isLoading && <Loading />}
      {q.isError && <ErrorState message="Couldn't load details." onRetry={() => q.refetch()} />}
      {q.data && q.data.rows.length === 0 && <div className="state">No orders in this category. </div>}
      {q.data && q.data.rows.length > 0 && !isCapacity && (
        <div style={{ maxHeight: 420, overflowY: "auto" }}>
          <table>
            <thead><tr>
              <th>Order</th><th>Customer</th><th>Priority</th><th>Slip</th><th>Reasons</th>
            </tr></thead>
            <tbody>
              {q.data.rows.map((r) => (
                <tr key={r.order_id} style={{ cursor: "pointer" }}
                    onClick={() => r.order_id && onOpenOrder(r.order_id)}>
                  <td style={{ fontWeight: 600 }}>{r.order_id}</td>
                  <td>{r.customer || "-"}</td>
                  <td>{r.priority || "-"}</td>
                  <td>{r.slip_hrs && r.slip_hrs > 0
                    ? <span style={{ color: "var(--risk, #c0392b)" }}>+{r.slip_hrs}h</span> : "-"}</td>
                  <td>{r.reasons && r.reasons.length > 0
                    ? r.reasons.map((x, i) => <ReasonChip key={i} type={x.type} text={x.text} />)
                    : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.data && q.data.rows.length > 0 && isCapacity && (
        <div style={{ maxHeight: 420, overflowY: "auto" }}>
          <table>
            <thead><tr><th>Work centre</th><th>Date</th><th>Demand (min)</th><th>Available (min)</th></tr></thead>
            <tbody>
              {q.data.rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{r.work_center}</td>
                  <td>{fmtDate(r.load_date)}</td>
                  <td style={{ color: "var(--risk, #c0392b)" }}>{r.demand_min != null ? Math.round(Number(r.demand_min)) : "-"}</td>
                  <td>{r.available_min ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
