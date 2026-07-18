import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, RadialBarChart, RadialBar } from "recharts";
import { api } from "@/api/client";
import { Loading, ErrorState, Pill, statusTone, PriorityPill, Modal } from "@/components/ui";
import { fmtDate, fmtDateTime as fmtDT, fmtRelativeTime, fmtHours } from "@/lib/format";
import type { WatchlistRow } from "@/api/types";

export function Dashboard() {
  const nav = useNavigate();
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: api.kpis });
  const watch = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const digest = useQuery({ queryKey: ["digest"], queryFn: api.digest });
  const [drillOrder, setDrillOrder] = useState<string | null>(null);
  const [drillKey, setDrillKey] = useState<string | null>(null);

  return (
    <div className="stack">
      {kpis.data?.last_updated && (
        <div className="muted" style={{ fontSize: 12, marginBottom: -6 }}>
          Schedule last updated {fmtRelativeTime(kpis.data.last_updated)}
        </div>
      )}

      <Digest digest={digest.data} onOpenOrder={setDrillOrder} />

      {/* Charts row: 2 gauges (target metrics), a health-distribution donut, and
          an issues-by-category bar -- replaces the old plain 7-KPI-card grid.
          Every segment/bar is clickable and goes to the exact same
          destination its old KPI card did. */}
      <section className="grid" style={{ gridTemplateColumns: "150px 150px 1fr 1fr", gap: 14 }}>
        {kpis.isLoading && <Loading label="Loading metrics..." />}
        {kpis.isError && <ErrorState message="Couldn't load metrics." onRetry={() => kpis.refetch()} />}
        {kpis.data && (
          <>
            <Gauge label="Schedule adherence" pct={kpis.data.schedule_adherence_pct}
              trend={kpis.data.trend?.schedule_adherence_pct}
              onClick={() => setDrillKey("adherence")} />
            <Gauge label="On-time delivery" pct={kpis.data.on_time_delivery_pct}
              trend={kpis.data.trend?.on_time_delivery_pct}
              onClick={() => setDrillKey("otd")} />
            <HealthDonut kpis={kpis.data} onSetDrillKey={setDrillKey} onNav={nav} />
            <IssuesBar kpis={kpis.data} onSetDrillKey={setDrillKey} onNav={nav} />
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

      <DelayedCriticalPanel onViewAll={() => nav("/delayed")} />

      <OrderWatchlist watch={watch} onOpenOrder={setDrillOrder} />

      {/* Insight panels */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
        <RecoveryPipelinePanel onOpen={() => nav("/reschedule")} />
        <MaterialRiskPanel onOpen={() => nav("/materials")} />
      </div>

      {drillOrder && <OrderDrillDown orderId={drillOrder} onClose={() => setDrillOrder(null)} />}
    </div>
  );
}

function Digest({ digest, onOpenOrder }: {
  digest?: { new: string[]; resolved: string[]; since: string | null };
  onOpenOrder: (oid: string) => void;
}) {
  if (!digest || (digest.new.length === 0 && digest.resolved.length === 0)) return null;
  const since = digest.since ? fmtRelativeTime(digest.since) : "your last check";
  return (
    <div className="banner" style={{ background: "var(--surface-1, #f4f6f7)", border: "1px solid var(--line)", fontSize: 12.5 }}>
      Since {since}:{" "}
      {digest.new.length > 0 && (
        <span style={{ color: "var(--risk)", fontWeight: 650 }}>+{digest.new.length} new critical</span>
      )}
      {digest.new.length > 0 && digest.resolved.length > 0 && ", "}
      {digest.resolved.length > 0 && (
        <span style={{ color: "var(--ok)", fontWeight: 650 }}>{digest.resolved.length} resolved</span>
      )}
      {digest.new.length > 0 && (
        <span className="muted" style={{ marginLeft: 8 }}>
          ({digest.new.map((oid, i) => (
            <span key={oid}>
              {i > 0 && ", "}
              <span style={{ color: "var(--teal)", cursor: "pointer" }} onClick={() => onOpenOrder(oid)}>{oid}</span>
            </span>
          ))})
        </span>
      )}
    </div>
  );
}

function TrendTag({ trend, higherIsBetter = true }: { trend?: number; higherIsBetter?: boolean }) {
  if (trend == null || trend === 0) return null;
  const better = higherIsBetter ? trend > 0 : trend < 0;
  const arrow = trend > 0 ? "\u2191" : "\u2193";
  return (
    <span style={{ fontSize: 10.5, color: better ? "var(--ok)" : "var(--risk)", fontWeight: 600 }}>
      {arrow}{Math.abs(trend)} vs yesterday
    </span>
  );
}

function Gauge({ label, pct, trend, onClick }: {
  label: string; pct: number | null; trend?: number; onClick: () => void;
}) {
  const v = pct ?? 0;
  const color = v >= 90 ? "var(--ok)" : v >= 80 ? "var(--warn)" : "var(--risk)";
  const data = [{ value: v }];
  return (
    <div className="card" style={{ cursor: "pointer", textAlign: "center", padding: "10px 6px" }}
      onClick={onClick} title="Click for the orders behind this metric.">
      <div style={{ position: "relative", width: 84, height: 84, margin: "0 auto" }}>
        <RadialBarChart width={84} height={84} cx="50%" cy="50%" innerRadius="72%" outerRadius="100%"
          barSize={7} data={data} startAngle={90} endAngle={-270}>
          <RadialBar dataKey="value" cornerRadius={4} fill={color} background={{ fill: "var(--line)" }}
            isAnimationActive={false} />
        </RadialBarChart>
        <div style={{
          position: "absolute", top: 0, left: 0, width: "100%", height: "100%",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 16, fontWeight: 700,
        }}>
          {pct == null ? "-" : `${pct}%`}
        </div>
      </div>
      <div className="l" style={{ marginTop: 4 }}>{label}</div>
      <div><TrendTag trend={trend} /></div>
    </div>
  );
}

const HEALTH_COLORS = { on: "var(--ok)", unconfirmed: "#8a97a0", risk: "var(--warn)", delayed: "var(--risk)" };

function HealthDonut({ kpis, onSetDrillKey, onNav }: {
  kpis: { orders: number; orders_at_risk: number; delayed_critical: number; unconfirmed: number };
  onSetDrillKey: (k: string) => void; onNav: (path: string) => void;
}) {
  const onTrack = Math.max(0, kpis.orders - kpis.orders_at_risk - kpis.unconfirmed);
  const segments = [
    { key: "on", label: "On track", value: onTrack, color: HEALTH_COLORS.on, onClick: undefined },
    { key: "unconfirmed", label: "Watch list", value: kpis.unconfirmed, color: HEALTH_COLORS.unconfirmed,
      onClick: () => onSetDrillKey("unconfirmed") },
    { key: "risk", label: "At risk", value: kpis.orders_at_risk, color: HEALTH_COLORS.risk,
      onClick: () => onSetDrillKey("risk") },
    { key: "delayed", label: "Delayed/critical", value: kpis.delayed_critical, color: HEALTH_COLORS.delayed,
      onClick: () => onNav("/delayed") },
  ].filter((s) => s.value > 0);

  return (
    <div className="card" style={{ padding: "10px 14px" }}>
      <div className="l" style={{ marginBottom: 4 }}>Order health distribution</div>
      <div className="row" style={{ gap: 12, alignItems: "center" }}>
        <div style={{ width: 90, height: 90, flex: "none" }}>
          <PieChart width={90} height={90}>
            <Pie data={segments} dataKey="value" innerRadius={26} outerRadius={42} isAnimationActive={false}
              onClick={(entry) => { const fn = (entry as { payload?: { onClick?: () => void } })?.payload?.onClick; if (fn) fn(); }}>
              {segments.map((s) => (
                <Cell key={s.key} fill={s.color} cursor={s.onClick ? "pointer" : "default"} />
              ))}
            </Pie>
          </PieChart>
        </div>
        <div style={{ fontSize: 11 }}>
          {segments.map((s) => (
            <div key={s.key} style={{ cursor: s.onClick ? "pointer" : "default", marginBottom: 2 }}
              onClick={s.onClick} title={s.onClick ? "Click for the orders behind this" : undefined}>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: s.color, marginRight: 5 }} />
              {s.label} - {s.value}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function IssuesBar({ kpis, onSetDrillKey, onNav }: {
  kpis: { material_at_risk: number; capacity_conflicts: number; unconfirmed: number; delayed_critical: number };
  onSetDrillKey: (k: string) => void; onNav: (path: string) => void;
}) {
  const items = [
    { label: "Material", value: kpis.material_at_risk, color: "var(--warn)", onClick: () => onSetDrillKey("material") },
    { label: "Capacity", value: kpis.capacity_conflicts, color: "#2a78d6", onClick: () => onNav("/capacity") },
    { label: "Watch list", value: kpis.unconfirmed, color: HEALTH_COLORS.unconfirmed, onClick: () => onSetDrillKey("unconfirmed") },
    { label: "Delayed", value: kpis.delayed_critical, color: "var(--risk)", onClick: () => onNav("/delayed") },
  ];
  return (
    <div className="card" style={{ padding: "10px 14px" }}>
      <div className="l" style={{ marginBottom: 4 }}>Issues by category</div>
      <BarChart width={220} height={100} data={items} layout="vertical"
        margin={{ top: 2, right: 10, bottom: 2, left: 0 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="label" width={62} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
        <Bar dataKey="value" radius={3} barSize={14} isAnimationActive={false}
          onClick={(entry) => { const fn = (entry as { payload?: { onClick?: () => void } })?.payload?.onClick; if (fn) fn(); }}>
          {items.map((it, i) => <Cell key={i} fill={it.color} cursor="pointer" />)}
        </Bar>
      </BarChart>
    </div>
  );
}


function OrderWatchlist({ watch, onOpenOrder }: {
  watch: { data?: WatchlistRow[]; isLoading: boolean; isError: boolean; isFetching: boolean; refetch: () => void };
  onOpenOrder: (oid: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [workCentre, setWorkCentre] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 10;

  const allWorkCentres = useMemo(() => {
    const set = new Set<string>();
    (watch.data ?? []).forEach((r) => (r.work_centers ?? []).forEach((wc) => set.add(wc)));
    return Array.from(set).sort();
  }, [watch.data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (watch.data ?? []).filter((r) => {
      if (q && !r.order_id.toLowerCase().includes(q) && !r.customer.toLowerCase().includes(q)) return false;
      if (priority && r.priority !== priority) return false;
      if (workCentre && !(r.work_centers ?? []).includes(workCentre)) return false;
      return true;
    });
  }, [watch.data, search, priority, workCentre]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const resetPage = () => setPage(0);

  return (
    <section className="card">
      <div className="hd">
        Order watchlist
        {watch.isFetching && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>refreshing...</span>}
      </div>
      <div className="bd" style={{ padding: "10px 16px 0" }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <input type="search" placeholder="Search order or customer..." value={search}
            onChange={(e) => { setSearch(e.target.value); resetPage(); }} style={{ width: 200 }} />
          <select value={priority} onChange={(e) => { setPriority(e.target.value); resetPage(); }} style={{ width: 130 }}>
            <option value="">All priorities</option>
            <option value="HIGH">HIGH</option><option value="MED">MED</option><option value="LOW">LOW</option>
          </select>
          <select value={workCentre} onChange={(e) => { setWorkCentre(e.target.value); resetPage(); }} style={{ width: 170 }}>
            <option value="">All work centres</option>
            {allWorkCentres.map((wc) => <option key={wc} value={wc}>{wc}</option>)}
          </select>
          {(search || priority || workCentre) && (
            <button className="ghost" onClick={() => { setSearch(""); setPriority(""); setWorkCentre(""); resetPage(); }}>
              Clear filters
            </button>
          )}
        </div>
      </div>
      <div className="bd" style={{ padding: 0 }}>
        {watch.isLoading && <Loading />}
        {watch.isError && <ErrorState message="Couldn't load the watchlist." onRetry={watch.refetch} />}
        {watch.data && filtered.length === 0 && (
          <div className="state">{watch.data.length === 0 ? "No orders yet." : "No orders match these filters."}</div>
        )}
        {pageRows.length > 0 && (
          <table className="roomy">
            <thead>
              <tr>
                <th>Order</th><th>Product</th><th>Customer</th><th className="num">Qty</th>
                <th>Priority</th><th>Committed</th><th>Planned delivery</th>
                <th>Buffer</th><th>Material</th><th>Schedule</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r) => (
                <tr key={r.order_id} style={{ cursor: "pointer" }} onClick={() => onOpenOrder(r.order_id)}
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
      {filtered.length > PAGE_SIZE && (
        <div className="row" style={{ justifyContent: "flex-end", gap: 8, padding: "10px 16px", borderTop: "1px solid var(--line)" }}>
          <button disabled={page === 0} onClick={() => setPage(0)}>First</button>
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>Page {page + 1} of {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>Next</button>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>Last</button>
        </div>
      )}
    </section>
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

const SEVERITY_RANK: Record<string, number> = { Critical: 0, High: 1, Medium: 2 };

function DelayedCriticalPanel({ onViewAll }: { onViewAll: () => void }) {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["delayed-orders"], queryFn: api.delayedOrders });
  const rows = (q.data ?? [])
    .slice()
    .sort((a, b) => {
      const rankDiff = (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9);
      if (rankDiff !== 0) return rankDiff;
      return (b.deviation_minutes ?? 0) - (a.deviation_minutes ?? 0);
    })
    .slice(0, 5);
  const total = q.data?.length ?? 0;

  return (
    <section className="card" style={{ borderColor: "#f3c9c5" }}>
      <div className="hd" style={{ borderColor: "#f3c9c5", background: "var(--risk-bg)", color: "var(--risk)", cursor: "pointer" }}
        onClick={onViewAll} title="See all delayed & critical orders">
        Delayed & critical orders
        <span style={{ fontSize: 11, fontWeight: 500, color: "var(--ink-2)" }}>View all ({total}) &rarr;</span>
      </div>
      <div className="bd" style={{ padding: 0 }}>
        {q.isLoading && <Loading />}
        {q.isError && <ErrorState message="Couldn't load delayed orders." onRetry={() => q.refetch()} />}
        {q.data && rows.length === 0 && (
          <div className="state">Nothing critical right now.</div>
        )}
        {rows.length > 0 && (
          <table className="roomy">
            <thead>
              <tr>
                <th>Order</th><th>Customer</th><th className="num">Qty</th><th>Deviation</th>
                <th>Priority</th><th>Milestone affected</th><th>Reason</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.order_id} style={{ cursor: "pointer" }}
                  onClick={() => nav(`/delayed?order=${encodeURIComponent(r.order_id)}`)}
                  title="See why and get a recommendation">
                  <td className="mono">{r.order_id}</td>
                  <td>{r.customer}</td>
                  <td className="num">{r.order_qty}</td>
                  <td style={{ color: r.severity === "Critical" ? "var(--risk)" : "var(--warn)", fontWeight: 650 }}>
                    {r.deviation_minutes ? fmtHours(r.deviation_minutes / 60) : "-"}
                  </td>
                  <td><PriorityPill priority={r.priority} /></td>
                  <td>{r.milestone_name}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{r.root_cause_code || "-"}</td>
                  <td style={{ color: "var(--teal)", fontSize: 11 }}>Why &amp; recover &rarr;</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
