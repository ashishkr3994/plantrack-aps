import { useState } from "react";
import { useOrders, useOrderSchedule } from "@/hooks/queries";
import { Loading, ErrorState, Empty, Pill } from "@/components/ui";

function fmtDt(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function Schedule() {
  const orders = useOrders();
  const [selected, setSelected] = useState<string>("");

  // default to first order once loaded
  const orderId = selected || orders.data?.[0]?.order_id || "";
  const sched = useOrderSchedule(orderId);

  return (
    <div className="stack">
      <div className="spread">
        <h2>Schedule</h2>
        <div style={{ width: 280 }}>
          <select
            value={orderId}
            onChange={(e) => setSelected(e.target.value)}
            disabled={orders.isLoading}
          >
            {orders.isLoading && <option>Loading orders…</option>}
            {orders.data?.map((o) => (
              <option key={o.order_id} value={o.order_id}>
                {o.order_id} — {o.customer}
              </option>
            ))}
          </select>
        </div>
      </div>

      <section className="card">
        <div className="hd">Operation sequence {orderId && <span className="mono muted">{orderId}</span>}</div>
        <div className="bd" style={{ padding: 0 }}>
          {sched.isLoading && <Loading label="Loading schedule…" />}
          {sched.isError && <ErrorState message="Couldn't load the schedule." onRetry={() => sched.refetch()} />}
          {sched.data && !sched.data.schedule && (
            <Empty message="This order hasn't been scheduled yet. Run the optimiser from the Reschedule screen." />
          )}
          {sched.data && sched.data.schedule && (
            <>
              {(sched.data.schedule as { is_stale?: boolean }).is_stale && (
                <div className="banner err" style={{ margin: 16 }}>
                  This schedule is out of date — {String((sched.data.schedule as { stale_reason?: string }).stale_reason ?? "the routing changed")}.
                  Re-run the optimiser from the Reschedule screen to refresh it.
                </div>
              )}
              <table>
              <thead>
                <tr>
                  <th className="num">Seq</th>
                  <th>Work center</th>
                  <th>Group</th>
                  <th className="num">Pred</th>
                  <th>Start</th>
                  <th>End</th>
                  <th className="num">Duration (min)</th>
                </tr>
              </thead>
              <tbody>
                {sched.data.operations.map((op) => (
                  <tr key={op.operation_seq}>
                    <td className="num mono">{op.operation_seq}</td>
                    <td>{op.work_center}</td>
                    <td>{op.parallel_group ? <Pill tone="info">{op.parallel_group}</Pill> : "—"}</td>
                    <td className="num">{op.predecessor_operation_seq ?? "—"}</td>
                    <td>{fmtDt(op.planned_start)}</td>
                    <td>{fmtDt(op.planned_end)}</td>
                    <td className="num">{Math.round(op.duration_mins)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
