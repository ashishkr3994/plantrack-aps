import { useMemo, useState } from "react";
import { useOrders } from "@/hooks/queries";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Loading, Pill, PriorityPill, Modal } from "@/components/ui";
import { GanttChart, computeSharedRange } from "@/components/GanttChart";
import { fmtDate, fmtDateTime, fmtHours } from "@/lib/format";
import type {
  SandboxOverride, SandboxResult, SandboxOrderResult, SandboxEventOverride,
  SandboxScheduleStage, GanttOp, GanttDowntime,
} from "@/api/types";

interface RowState {
  overridden: boolean;
  qty: string;
  partial_qty: string;
  priority: string;
  committed_due_dt: string;
  exclude: boolean;
  event_type: string;
  event_operation_seq: string;
  event_downtime_mins: string;
  event_whole_wc: boolean;
  event_qty: string;
}

const emptyRow: RowState = {
  overridden: false, qty: "", partial_qty: "", priority: "", committed_due_dt: "",
  exclude: false, event_type: "", event_operation_seq: "", event_downtime_mins: "",
  event_whole_wc: false, event_qty: "",
};

const PAGE_SIZE = 20;

export function Sandbox() {
  const { hasRole } = useAuth();
  const canRun = hasRole("planner");
  const orders = useOrders();

  const [visible, setVisible] = useState<string[]>([]);
  const [rows, setRows] = useState<Map<string, RowState>>(new Map());
  const [addPick, setAddPick] = useState("");
  const [mode, setMode] = useState("forward");
  const [budget, setBudget] = useState(20);
  const [overtime, setOvertime] = useState(0);
  const [leveling, setLeveling] = useState<"off" | "soft" | "strict">("off");
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<SandboxOrderResult | null>(null);

  const byId = new Map((orders.data ?? []).map((o) => [o.order_id, o]));

  const addAll = () => setVisible((orders.data ?? []).map((o) => o.order_id));
  const addOne = () => {
    if (!addPick || visible.includes(addPick)) return;
    setVisible((v) => [...v, addPick]);
    setAddPick("");
  };
  const removeOne = (oid: string) => {
    setVisible((v) => v.filter((x) => x !== oid));
    setRows((m) => { const n = new Map(m); n.delete(oid); return n; });
  };
  const rowFor = (oid: string): RowState => rows.get(oid) ?? emptyRow;
  const setRow = (oid: string, patch: Partial<RowState>) =>
    setRows((m) => { const n = new Map(m); n.set(oid, { ...rowFor(oid), ...patch }); return n; });
  const toggleOverride = (oid: string) =>
    setRow(oid, { overridden: !rowFor(oid).overridden });

  const run = async () => {
    setError(null);
    setResult(null);
    const overrides: SandboxOverride[] = [];
    const visibleSet = new Set(visible);
    for (const o of orders.data ?? []) {
      // an order removed from the builder (or never added) must be genuinely
      // excluded from the scenario solve -- not just hidden from the table --
      // so "only the orders I added" is what actually gets planned.
      if (!visibleSet.has(o.order_id)) {
        overrides.push({ order_id: o.order_id, exclude: true });
        continue;
      }
      const r = rows.get(o.order_id);
      if (!r || !r.overridden) continue;
      const events: SandboxEventOverride[] = [];
      if (r.event_type && r.event_operation_seq) {
        events.push({
          event_type: r.event_type as "pause" | "scrap" | "complete",
          operation_seq: Number(r.event_operation_seq),
          downtime_mins: r.event_downtime_mins ? Number(r.event_downtime_mins) : 0,
          whole_wc: r.event_whole_wc,
          qty: r.event_qty ? Number(r.event_qty) : 0,
        });
      }
      overrides.push({
        order_id: o.order_id,
        qty: r.qty ? Number(r.qty) : undefined,
        partial_qty: r.partial_qty ? Number(r.partial_qty) : undefined,
        priority: r.priority || undefined,
        committed_due_dt: r.committed_due_dt || undefined,
        exclude: r.exclude || undefined,
        events: events.length ? events : undefined,
      });
    }
    setBusy(true);
    setPage(0);
    try {
      const res = await api.simulate({ overrides, mode, time_budget_s: budget, overtime_hrs_per_day: overtime, leveling });
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
        <Pill tone="info">Simulation only - live plan untouched</Pill>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Add orders to a scenario, override only the ones you want to test, then run the
        optimiser against a copy of the live plan. Nothing here changes the real schedule.
      </p>

      {!canRun && <div className="banner err">Running simulations requires the planner role.</div>}

      <section className="card">
        <div className="hd">
          <span>Scenario builder{visible.length > 0 && <span className="muted" style={{ fontWeight: 500 }}> - {visible.length} order{visible.length === 1 ? "" : "s"}</span>}</span>
          <div className="row" style={{ gap: 8 }}>
            <select value={addPick} onChange={(e) => setAddPick(e.target.value)} style={{ width: 200 }} disabled={!canRun}>
              <option value="">Add an order...</option>
              {(orders.data ?? []).filter((o) => !visible.includes(o.order_id)).map((o) => (
                <option key={o.order_id} value={o.order_id}>{o.order_id} - {o.customer}</option>
              ))}
            </select>
            <button onClick={addOne} disabled={!canRun || !addPick}>Add</button>
            <button className="primary" onClick={addAll} disabled={!canRun || orders.isLoading}>Add all orders</button>
          </div>
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {orders.isLoading && <Loading />}
          {visible.length === 0 && !orders.isLoading && (
            <div className="state">No orders in the scenario yet. Add all orders, or add a few individually.</div>
          )}
          {visible.length > 0 && (
            <table className="roomy">
              <thead>
                <tr>
                  <th style={{ width: 30 }}></th>
                  <th>Order</th><th>Customer</th><th className="num">Qty</th><th>Priority</th>
                  <th>Committed</th><th>Override</th><th style={{ width: 30 }}></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((oid) => {
                  const o = byId.get(oid);
                  const r = rowFor(oid);
                  if (!o) return null;
                  return (
                    <>
                      <tr key={oid}>
                        <td>
                          <input type="checkbox" style={{ width: "auto" }} checked={r.overridden}
                            disabled={!canRun} onChange={() => toggleOverride(oid)} />
                        </td>
                        <td className="mono">{o.order_id}</td>
                        <td>{o.customer}</td>
                        <td className="num">{o.order_qty}</td>
                        <td><PriorityPill priority={o.priority} /></td>
                        <td>{fmtDate(o.committed_delivery_date)}</td>
                        <td className="muted">{r.overridden ? "Editing below" : "Not modified"}</td>
                        <td><button className="ghost danger" onClick={() => removeOne(oid)} title="Remove from scenario">&times;</button></td>
                      </tr>
                      {r.overridden && (
                        <tr key={`${oid}-edit`}>
                          <td></td>
                          <td colSpan={7} style={{ padding: 8 }}>
                            <div style={{ background: "var(--canvas)", borderRadius: "var(--r-sm)", padding: 10 }}>
                              <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
                                <div style={{ width: 100 }}>
                                  <label>New qty</label>
                                  <input type="number" min={1} placeholder={String(o.order_qty)} value={r.qty}
                                    onChange={(e) => setRow(oid, { qty: e.target.value })} />
                                </div>
                                <div style={{ width: 100 }}>
                                  <label>Partial qty</label>
                                  <input type="number" min={1} placeholder="-" value={r.partial_qty}
                                    onChange={(e) => setRow(oid, { partial_qty: e.target.value })} />
                                </div>
                                <div style={{ width: 110 }}>
                                  <label>Priority</label>
                                  <select value={r.priority} onChange={(e) => setRow(oid, { priority: e.target.value })}>
                                    <option value="">unchanged</option>
                                    <option value="HIGH">HIGH</option><option value="MED">MED</option><option value="LOW">LOW</option>
                                  </select>
                                </div>
                                <div style={{ width: 150 }}>
                                  <label>New due date</label>
                                  <input type="date" value={r.committed_due_dt}
                                    onChange={(e) => setRow(oid, { committed_due_dt: e.target.value })} />
                                </div>
                                <div style={{ width: 130 }}>
                                  <label>Add event</label>
                                  <select value={r.event_type} onChange={(e) => setRow(oid, { event_type: e.target.value })}>
                                    <option value="">none</option>
                                    <option value="pause">Downtime</option>
                                    <option value="scrap">Scrap</option>
                                    <option value="complete">Complete</option>
                                  </select>
                                </div>
                                {r.event_type && (
                                  <div style={{ width: 90 }}>
                                    <label>Op seq</label>
                                    <input type="number" placeholder="e.g. 30" value={r.event_operation_seq}
                                      onChange={(e) => setRow(oid, { event_operation_seq: e.target.value })} />
                                  </div>
                                )}
                                {r.event_type === "pause" && (
                                  <div style={{ width: 100 }}>
                                    <label>Minutes</label>
                                    <input type="number" min={1} value={r.event_downtime_mins}
                                      onChange={(e) => setRow(oid, { event_downtime_mins: e.target.value })} />
                                  </div>
                                )}
                                {r.event_type === "pause" && (
                                  <div style={{ width: 150, alignSelf: "flex-end", paddingBottom: 8 }}>
                                    <label style={{ display: "inline-flex", alignItems: "center", gap: 5, marginBottom: 0 }}>
                                      <input type="checkbox" style={{ width: "auto" }} checked={r.event_whole_wc}
                                        onChange={(e) => setRow(oid, { event_whole_wc: e.target.checked })} />
                                      Whole machine
                                    </label>
                                  </div>
                                )}
                                {r.event_type === "scrap" && (
                                  <div style={{ width: 100 }}>
                                    <label>Scrap qty</label>
                                    <input type="number" min={1} value={r.event_qty}
                                      onChange={(e) => setRow(oid, { event_qty: e.target.value })} />
                                  </div>
                                )}
                              </div>
                              <label style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 10, marginBottom: 0, color: "var(--risk)" }}>
                                <input type="checkbox" style={{ width: "auto" }} checked={r.exclude}
                                  onChange={(e) => setRow(oid, { exclude: e.target.checked })} />
                                Exclude from scenario
                              </label>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="card">
        <div className="bd row" style={{ gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 210 }}>
            <label>Scheduling mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={!canRun}>
              <option value="forward">Forward - earliest finish</option>
              <option value="backward">Backward - from due dates</option>
            </select>
          </div>
          <div style={{ width: 210 }}>
            <label>Load leveling</label>
            <select value={leveling} onChange={(e) => setLeveling(e.target.value as "off" | "soft" | "strict")} disabled={!canRun}>
              <option value="off">Off - earliest finish</option>
              <option value="soft">Soft - JIT, use idle time</option>
              <option value="strict">Strict - hold to promise date</option>
            </select>
          </div>
          <div style={{ width: 150 }}>
            <label>Overtime (hrs/day)</label>
            <input type="number" min={0} max={12} value={overtime} disabled={!canRun}
              onChange={(e) => setOvertime(Number(e.target.value))} />
          </div>
          <div style={{ width: 160 }}>
            <label>Time budget (seconds)</label>
            <input type="number" min={5} max={60} value={budget} disabled={!canRun}
              onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
          <button className="primary" onClick={run} disabled={!canRun || busy || visible.length === 0}>
            {busy ? "Simulating..." : "Run simulation"}
          </button>
        </div>
      </section>

      {error && <div className="banner err">{error}</div>}
      {busy && <div className="banner live"><span className="spinner" /> &nbsp;Running the optimiser on a copy of the plan...</div>}

      {result && !result.feasible && (
        <div className="banner err">{result.message ?? "This scenario has no feasible schedule."}</div>
      )}

      {result && result.feasible && (
        <Results result={result} showAll={showAll} setShowAll={setShowAll}
          page={page} setPage={setPage} onSelect={setSelected} />
      )}

      {selected && <DrillDown order={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function levelingLabel(l: string | null | undefined): string {
  if (l === "off") return "Off";
  if (l === "soft") return "Soft";
  if (l === "strict") return "Strict";
  return "Unknown";
}

function statusTone(s: string): "ok" | "warn" | "risk" {
  if (s === "on") return "ok";
  if (s === "risk") return "warn";
  return "risk";
}

function betterTone(live: number | null, whatif: number | null, higherIsBetter: boolean): "ok" | "warn" | "risk" {
  if (live == null || whatif == null) return "warn";
  if (whatif === live) return "warn";
  const better = higherIsBetter ? whatif > live : whatif < live;
  return better ? "ok" : "risk";
}

function KpiCompareCard({ label, live, whatif, unit, higherIsBetter }: {
  label: string; live: number | null; whatif: number | null; unit?: string; higherIsBetter: boolean;
}) {
  const tone = betterTone(live, whatif, higherIsBetter);
  const color = tone === "ok" ? "var(--ok)" : tone === "risk" ? "var(--risk)" : "var(--ink)";
  return (
    <div className="kpi">
      <div className="l">{label}</div>
      <div className="row" style={{ gap: 6, alignItems: "baseline", marginTop: 2 }}>
        <span className="muted" style={{ fontSize: 12 }}>Live {live ?? "-"}{unit}</span>
        <span className="muted" style={{ fontSize: 11 }}>&rarr;</span>
        <span style={{ fontSize: 20, fontWeight: 700, color }}>{whatif ?? "-"}{unit}</span>
      </div>
    </div>
  );
}

function TimelineComparison({ result }: { result: SandboxResult }) {
  const orders = result.orders ?? [];
  const [zoom, setZoom] = useState<"compact" | "comfortable" | "wide">("comfortable");
  const [search, setSearch] = useState("");

  const allLiveOps = useMemo(() => flattenOps(orders, "live"), [orders]);
  const allWhatifOps = useMemo(() => flattenOps(orders, "whatif"), [orders]);
  const liveDowntime: GanttDowntime[] = result.downtime_live ?? [];
  const whatifDowntime: GanttDowntime[] = result.downtime_whatif ?? [];

  // same filter text applied to both panels, so filtering an order narrows
  // the live AND what-if timelines together -- keeping them comparable.
  const q = search.trim().toLowerCase();
  const liveOps = q ? allLiveOps.filter((o) => o.order_id.toLowerCase().includes(q)) : allLiveOps;
  const whatifOps = q ? allWhatifOps.filter((o) => o.order_id.toLowerCase().includes(q)) : allWhatifOps;

  // shared range across BOTH sides, so the two panels align on the same X
  // axis -- otherwise each would pick its own window and a shift wouldn't be
  // visually comparable at a glance.
  const range = useMemo(() => computeSharedRange([
    { operations: liveOps, downtime: liveDowntime },
    { operations: whatifOps, downtime: whatifDowntime },
  ]), [liveOps, whatifOps, liveDowntime, whatifDowntime]);

  if (allLiveOps.length === 0 && allWhatifOps.length === 0) return null;

  const shownCount = new Set([...liveOps, ...whatifOps].map((o) => o.order_id)).size;
  const totalCount = new Set([...allLiveOps, ...allWhatifOps].map((o) => o.order_id)).size;

  return (
    <section className="card">
      <div className="hd">
        <span>Timeline - live vs what-if</span>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <input type="search" placeholder="Filter by Order ID..." value={search}
            onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
          {search && <button className="ghost" onClick={() => setSearch("")}>Clear</button>}
        </div>
      </div>
      <div className="bd stack">
        {search && (
          <span className="muted" style={{ fontSize: 12 }}>{shownCount} of {totalCount} orders shown</span>
        )}
        <div className="gantt-legend">
          <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-high" />High priority</span>
          <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-med" />Medium priority</span>
          <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-low" />Low priority</span>
          <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-downtime" />Downtime</span>
        </div>
        <div>
          <div className="l" style={{ marginBottom: 6 }}>Live</div>
          {liveOps.length === 0
            ? <div className="state">No operations match that Order ID filter.</div>
            : <GanttChart operations={liveOps} downtime={liveDowntime} range={range} zoom={zoom} onZoomChange={setZoom} />}
        </div>
        <div>
          <div className="l" style={{ marginBottom: 6, color: "var(--teal)" }}>What-if</div>
          {whatifOps.length === 0
            ? <div className="state">No operations match that Order ID filter.</div>
            : <GanttChart operations={whatifOps} downtime={whatifDowntime} range={range} zoom={zoom} onZoomChange={setZoom} />}
        </div>
      </div>
    </section>
  );
}

function Results({ result, showAll, setShowAll, page, setPage, onSelect }: {
  result: SandboxResult; showAll: boolean; setShowAll: (b: boolean) => void;
  page: number; setPage: (n: number) => void; onSelect: (o: SandboxOrderResult) => void;
}) {
  const all = result.orders ?? [];
  const changedOnly = all.filter((o) => o.changed);
  const rows = showAll ? all : changedOnly;
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const kl = result.kpis_live, kw = result.kpis_whatif;

  return (
    <div className="stack">
      {result.applied_changes.length > 0 && (
        <div className="banner live" style={{ fontSize: 13 }}>
          Applied: {result.applied_changes.join("; ")}
        </div>
      )}

      <h3 style={{ margin: 0 }}>Results - live vs what-if</h3>

      {(result.leveling_live !== undefined || result.leveling_whatif) && (
        <div className="row" style={{ gap: 10, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 12 }}>Load leveling:</span>
          <span className="row" style={{ gap: 6 }}>
            <span className="muted" style={{ fontSize: 12 }}>Live</span>
            <Pill tone="muted">{levelingLabel(result.leveling_live)}</Pill>
          </span>
          <span className="muted" style={{ fontSize: 11 }}>&rarr;</span>
          <span className="row" style={{ gap: 6 }}>
            <span className="muted" style={{ fontSize: 12 }}>What-if</span>
            <Pill tone="info">{levelingLabel(result.leveling_whatif)}</Pill>
          </span>
          {result.leveling_live && result.leveling_whatif && result.leveling_live !== result.leveling_whatif && (
            <span className="muted" style={{ fontSize: 11 }}>(different mode - some of the change below may come from this, not just your overrides)</span>
          )}
        </div>
      )}

      {kl && kw && (
        <div className="grid kpis">
          <KpiCompareCard label="Schedule adherence" live={kl.schedule_adherence_pct} whatif={kw.schedule_adherence_pct} unit="%" higherIsBetter />
          <KpiCompareCard label="On-time delivery" live={kl.on_time_delivery_pct} whatif={kw.on_time_delivery_pct} unit="%" higherIsBetter />
          <KpiCompareCard label="Orders at risk" live={kl.orders_at_risk} whatif={kw.orders_at_risk} higherIsBetter={false} />
          <KpiCompareCard label="Delayed / critical" live={kl.delayed_critical} whatif={kw.delayed_critical} higherIsBetter={false} />
          <KpiCompareCard label="Material at risk" live={kl.material_at_risk} whatif={kw.material_at_risk} higherIsBetter={false} />
          <KpiCompareCard label="Capacity conflicts" live={kl.capacity_conflicts} whatif={kw.capacity_conflicts} higherIsBetter={false} />
        </div>
      )}

      <TimelineComparison result={result} />

      <section className="card">
        <div className="hd">
          <div className="row" style={{ gap: 10 }}>
            <span>Order watchlist</span>
            <div className="row" style={{ gap: 0, border: "1px solid var(--line)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
              <button className={!showAll ? "primary" : ""} style={{ border: "none", borderRadius: 0 }}
                onClick={() => { setShowAll(false); setPage(0); }}>
                Changed only ({changedOnly.length})
              </button>
              <button className={showAll ? "primary" : ""} style={{ border: "none", borderRadius: 0, borderLeft: "1px solid var(--line)" }}
                onClick={() => { setShowAll(true); setPage(0); }}>
                Show all ({all.length})
              </button>
            </div>
          </div>
          <span className="muted" style={{ fontSize: 12 }}>
            Showing {rows.length === 0 ? 0 : page * PAGE_SIZE + 1}-{Math.min(rows.length, page * PAGE_SIZE + PAGE_SIZE)} of {rows.length}
          </span>
        </div>
        <div className="bd" style={{ padding: 0, overflowX: "auto" }}>
          {rows.length === 0 ? (
            <div className="state">
              {showAll ? "No orders in this scenario." : "No orders changed between live and what-if. Try \"Show all\" to review every order."}
            </div>
          ) : (
            <table className="roomy" style={{ minWidth: 900 }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ verticalAlign: "bottom" }}>Order</th>
                  <th colSpan={2} style={{ textAlign: "center" }}>Qty</th>
                  <th colSpan={2} style={{ textAlign: "center" }}>Priority</th>
                  <th colSpan={2} style={{ textAlign: "center" }}>Committed</th>
                  <th colSpan={2} style={{ textAlign: "center" }}>Planned delivery</th>
                  <th colSpan={2} style={{ textAlign: "center" }}>Buffer</th>
                  <th rowSpan={2} style={{ verticalAlign: "bottom" }}>Schedule</th>
                </tr>
                <tr>
                  <th className="muted">Live</th><th style={{ color: "var(--teal)" }}>What-if</th>
                  <th className="muted">Live</th><th style={{ color: "var(--teal)" }}>What-if</th>
                  <th className="muted">Live</th><th style={{ color: "var(--teal)" }}>What-if</th>
                  <th className="muted">Live</th><th style={{ color: "var(--teal)" }}>What-if</th>
                  <th className="muted">Live</th><th style={{ color: "var(--teal)" }}>What-if</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((o) => (
                  <tr key={o.order_id}>
                    <td className="mono">{o.order_id}</td>
                    <td className="num">{o.qty_live ?? "-"}</td>
                    <td className="num" style={o.qty_live !== o.qty_whatif ? { background: "var(--warn-bg)", fontWeight: 650 } : undefined}>{o.qty_whatif}</td>
                    <td><PriorityPill priority={o.priority_live} /></td>
                    <td style={o.priority_live !== o.priority_whatif ? { background: "var(--warn-bg)" } : undefined}><PriorityPill priority={o.priority_whatif} /></td>
                    <td>{fmtDate(o.committed_live)}</td>
                    <td style={o.committed_live !== o.committed_whatif ? { background: "var(--warn-bg)", fontWeight: 650 } : undefined}>{fmtDate(o.committed_whatif)}</td>
                    <td>{fmtDate(o.planned_delivery_live)}</td>
                    <td style={o.planned_delivery_live !== o.planned_delivery_whatif ? { background: "var(--warn-bg)", fontWeight: 650 } : undefined}>{fmtDate(o.planned_delivery_whatif)}</td>
                    <td className="num" style={{ color: (o.buffer_hrs_live ?? 0) < 0 ? "var(--risk)" : "var(--ok)" }}>{o.buffer_hrs_live != null ? fmtHours(o.buffer_hrs_live) : "-"}</td>
                    <td className="num" style={{
                      color: (o.buffer_hrs_whatif ?? 0) < 0 ? "var(--risk)" : "var(--ok)",
                      ...(o.buffer_hrs_live != null && o.buffer_hrs_whatif != null && Math.round(o.buffer_hrs_live) !== Math.round(o.buffer_hrs_whatif)
                        ? { background: "var(--warn-bg)", fontWeight: 650 } : {}),
                    }}>{o.buffer_hrs_whatif != null ? fmtHours(o.buffer_hrs_whatif) : "-"}</td>
                    <td><button className="ghost" onClick={() => onSelect(o)}>View</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {rows.length > 0 && (
          <div className="row" style={{ justifyContent: "flex-end", gap: 8, padding: "10px 16px", borderTop: "1px solid var(--line)" }}>
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
            <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>Page {page + 1} of {totalPages}</span>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        )}
      </section>

      {result.note && <p className="muted" style={{ fontSize: 12 }}>{result.note}</p>}
    </div>
  );
}

function flattenOps(orders: SandboxOrderResult[], side: "live" | "whatif"): GanttOp[] {
  const out: GanttOp[] = [];
  for (const o of orders) {
    const stages = side === "live" ? o.schedule_live : o.schedule_whatif;
    const priority = side === "live" ? o.priority_live : o.priority_whatif;
    for (const s of stages) {
      if (s.kind !== "op" || !s.start || !s.end) continue;
      out.push({
        work_center: s.stage, operation_seq: s.operation_seq ?? 0, start: s.start, end: s.end,
        parallel_group: s.parallel_group ?? null, order_id: o.order_id,
        priority: (priority ?? "MED") as GanttOp["priority"], customer: o.customer ?? "",
      });
    }
  }
  return out;
}

function mergeStages(live: SandboxScheduleStage[], whatif: SandboxScheduleStage[]) {
  const key = (s: SandboxScheduleStage) => `${s.kind}:${s.stage}:${s.operation_seq ?? ""}`;
  const liveByKey = new Map(live.map((s) => [key(s), s]));
  const seen = new Set<string>();
  const merged: { label: string; parallel: boolean; live: SandboxScheduleStage | null; whatif: SandboxScheduleStage | null }[] =
    whatif.map((w) => {
      const k = key(w);
      seen.add(k);
      return { label: w.stage, parallel: !!w.parallel_group, live: liveByKey.get(k) ?? null, whatif: w };
    });
  for (const s of live) {
    const k = key(s);
    if (!seen.has(k)) merged.push({ label: s.stage, parallel: !!s.parallel_group, live: s, whatif: null });
  }
  return merged;
}

function DrillDown({ order, onClose }: { order: SandboxOrderResult; onClose: () => void }) {
  const stages = useMemo(() => mergeStages(order.schedule_live, order.schedule_whatif), [order]);
  return (
    <Modal title={`${order.order_id} - live vs what-if`} size="lg" onClose={onClose}>
      <div className="stack">
        <div>
          <div className="l" style={{ marginBottom: 6 }}>Order & status</div>
          <table><tbody>
            <tr><td className="muted">Quantity</td><td>{order.qty_live} &rarr; <strong>{order.qty_whatif}</strong></td></tr>
            <tr><td className="muted">Priority</td><td><PriorityPill priority={order.priority_live} /> &rarr; <PriorityPill priority={order.priority_whatif} /></td></tr>
            <tr><td className="muted">Committed</td><td>{fmtDate(order.committed_live)} &rarr; {fmtDate(order.committed_whatif)}</td></tr>
            <tr><td className="muted">Status (what-if)</td><td><Pill tone={statusTone(order.status_whatif)}>{order.status_whatif}</Pill></td></tr>
          </tbody></table>
        </div>

        <div>
          <div className="l" style={{ marginBottom: 6 }}>Schedule (live vs what-if)</div>
          <div style={{ overflowX: "auto" }}>
            <table className="roomy">
              <thead>
                <tr>
                  <th rowSpan={2} style={{ verticalAlign: "bottom" }}>Stage</th>
                  <th colSpan={2} style={{ textAlign: "center" }} className="muted">Live</th>
                  <th colSpan={2} style={{ textAlign: "center", color: "var(--teal)" }}>What-if</th>
                </tr>
                <tr>
                  <th className="muted">Start</th><th className="muted">End</th>
                  <th style={{ color: "var(--teal)" }}>Start</th><th style={{ color: "var(--teal)" }}>End</th>
                </tr>
              </thead>
              <tbody>
                {stages.map((s, i) => (
                  <tr key={i}>
                    <td>{s.label}{s.parallel && <span className="muted" style={{ fontSize: 10 }}> (parallel)</span>}</td>
                    <td>{s.live?.start ? fmtDateTime(s.live.start) : "-"}</td>
                    <td>{s.live?.end ? fmtDateTime(s.live.end) : "-"}</td>
                    <td>{s.whatif?.start ? fmtDateTime(s.whatif.start) : "-"}</td>
                    <td>{s.whatif?.end ? fmtDateTime(s.whatif.end) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="l" style={{ marginBottom: 6 }}>Risk signal detected (what-if)</div>
          <p style={{ margin: 0, fontSize: 13 }}>{order.risk_signal_whatif ?? "None - within buffer"}</p>
        </div>

        <div>
          <div className="l" style={{ marginBottom: 6 }}>Execution events (what-if)</div>
          {order.execution_events_whatif.length === 0 ? (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>None added.</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {order.execution_events_whatif.map((ev, i) => (
                <li key={i}>
                  {ev.event_type === "pause" && `Downtime, op ${ev.operation_seq}, ${ev.downtime_mins}min${ev.whole_wc ? " (whole machine)" : ""}`}
                  {ev.event_type === "scrap" && `Scrap, op ${ev.operation_seq}, ${ev.qty} units`}
                  {ev.event_type === "complete" && `Marked complete, op ${ev.operation_seq}`}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
