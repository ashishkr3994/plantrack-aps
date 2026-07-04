import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrders } from "@/hooks/queries";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Loading, Pill } from "@/components/ui";

const EVENT_TYPES = [
  { v: "start", label: "Start" },
  { v: "pause", label: "Pause / downtime" },
  { v: "resume", label: "Resume" },
  { v: "complete", label: "Complete" },
  { v: "scrap", label: "Scrap" },
  { v: "material_ready", label: "Material ready" },
  { v: "dispatch", label: "Dispatch" },
  { v: "delivered", label: "Delivered" },
];

function fmtDT(s: unknown): string {
  if (!s || typeof s !== "string") return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(s);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function Events() {
  const { hasRole, user } = useAuth();
  const canLog = hasRole("planner");
  const nav = useNavigate();
  const qc = useQueryClient();
  const orders = useOrders();

  const [orderId, setOrderId] = useState<number | "">("");
  const [eventType, setEventType] = useState("pause");
  const [opSeq, setOpSeq] = useState<number | "">("");
  const [when, setWhen] = useState(() => new Date().toISOString().slice(0, 16));
  const [qty, setQty] = useState<number | "">("");
  const [downtimeReason, setDowntimeReason] = useState("");
  const [downtimeMins, setDowntimeMins] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logged, setLogged] = useState<{ orderId: number; orderBiz: string } | null>(null);

  const events = useQuery({
    queryKey: ["events", orderId],
    queryFn: () => api.listEvents(typeof orderId === "number" ? orderId : undefined),
    enabled: orderId !== "",
  });

  const isDowntime = eventType === "pause";

  const submit = async () => {
    setError(null);
    setLogged(null);
    if (orderId === "") { setError("Pick an order."); return; }
    setBusy(true);
    try {
      const bizId = orders.data?.find((o) => o.id === orderId)?.order_id ?? String(orderId);
      await api.createEvent({
        event_id: `EV-${bizId}-${Date.now()}`,
        order_id: orderId as number,
        operation_seq: opSeq === "" ? null : Number(opSeq),
        event_type: eventType,
        event_timestamp: new Date(when).toISOString(),
        event_qty: qty === "" ? null : Number(qty),
        downtime_reason: isDowntime && downtimeReason ? downtimeReason : null,
        downtime_mins: isDowntime && downtimeMins !== "" ? Number(downtimeMins) : 0,
        entered_by: user?.username ?? null,
      });
      setLogged({ orderId: orderId as number, orderBiz: bizId });
      qc.invalidateQueries({ queryKey: ["events", orderId] });
      qc.invalidateQueries({ queryKey: ["kpis"] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      // reset the volatile fields
      setDowntimeReason(""); setDowntimeMins(""); setQty("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't log the event.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <h2>Execution events</h2>
      <p className="muted" style={{ margin: 0 }}>
        Log what actually happens on the floor — downtime, starts, completions, scrap, material
        arrivals. Events feed the deviation engine; after logging a disruption you can re-plan
        the affected order to see updated dates.
      </p>

      {!canLog && <div className="banner err">Logging events requires the planner role.</div>}

      <section className="card">
        <div className="hd">Log an event</div>
        <div className="bd stack">
          <div className="row" style={{ gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ width: 220 }}>
              <label>Order</label>
              <select value={orderId} onChange={(e) => setOrderId(e.target.value ? Number(e.target.value) : "")} disabled={!canLog}>
                <option value="">Select order…</option>
                {orders.data?.map((o) => <option key={o.id} value={o.id}>{o.order_id} — {o.customer}</option>)}
              </select>
            </div>
            <div style={{ width: 190 }}>
              <label>Event type</label>
              <select value={eventType} onChange={(e) => setEventType(e.target.value)} disabled={!canLog}>
                {EVENT_TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
              </select>
            </div>
            <div style={{ width: 130 }}>
              <label>Operation seq</label>
              <input type="number" min={1} placeholder="—" value={opSeq} disabled={!canLog}
                onChange={(e) => setOpSeq(e.target.value ? Number(e.target.value) : "")} />
            </div>
            <div style={{ width: 200 }}>
              <label>When</label>
              <input type="datetime-local" value={when} disabled={!canLog} onChange={(e) => setWhen(e.target.value)} />
            </div>
          </div>

          {isDowntime && (
            <div className="row" style={{ gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div style={{ width: 260 }}>
                <label>Downtime reason</label>
                <input type="text" placeholder="e.g. Machine breakdown" value={downtimeReason} disabled={!canLog}
                  onChange={(e) => setDowntimeReason(e.target.value)} />
              </div>
              <div style={{ width: 150 }}>
                <label>Downtime (mins)</label>
                <input type="number" min={0} value={downtimeMins} disabled={!canLog}
                  onChange={(e) => setDowntimeMins(e.target.value ? Number(e.target.value) : "")} />
              </div>
            </div>
          )}

          {(eventType === "complete" || eventType === "scrap") && (
            <div style={{ width: 150 }}>
              <label>Quantity</label>
              <input type="number" min={0} value={qty} disabled={!canLog}
                onChange={(e) => setQty(e.target.value ? Number(e.target.value) : "")} />
            </div>
          )}

          <div><button className="primary" onClick={submit} disabled={!canLog || busy}>{busy ? "Logging…" : "Log event"}</button></div>

          {error && <div className="banner err">{error}</div>}
          {logged && (
            <div className="banner ok">
              Event logged for <strong>{logged.orderBiz}</strong>. To see how the plan changes,{" "}
              <button className="ghost" style={{ padding: "2px 8px" }} onClick={() => nav("/reschedule")}>
                run recovery / re-plan →
              </button>
            </div>
          )}
        </div>
      </section>

      {orderId !== "" && (
        <section className="card">
          <div className="hd">Event history for this order</div>
          <div className="bd" style={{ padding: 0 }}>
            {events.isLoading && <Loading />}
            {events.data && events.data.length === 0 && <div className="state">No events logged for this order yet.</div>}
            {events.data && events.data.length > 0 && (
              <table>
                <thead><tr><th>Type</th><th>When</th><th className="num">Op</th><th className="num">Qty</th><th>Downtime</th><th>By</th></tr></thead>
                <tbody>
                  {events.data.map((e) => (
                    <tr key={e.id}>
                      <td><Pill tone={e.event_type === "pause" || e.event_type === "scrap" ? "risk" : "info"}>{e.event_type}</Pill></td>
                      <td>{fmtDT(e.event_timestamp)}</td>
                      <td className="num">{e.operation_seq ?? "—"}</td>
                      <td className="num">{e.event_qty ?? "—"}</td>
                      <td>{e.downtime_mins ? `${e.downtime_mins}m — ${e.downtime_reason ?? ""}` : "—"}</td>
                      <td className="muted">{e.entered_by ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
