import { useWatchlist } from "@/hooks/queries";
import { Loading, ErrorState } from "@/components/ui";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export function Analytics() {
  const watch = useWatchlist();

  // derive a simple buffer-by-order chart from the watchlist
  const data = (watch.data ?? [])
    .filter((r) => r.buffer_hrs != null)
    .map((r) => ({ order: r.order_id, buffer: Number(r.buffer_hrs) }));

  return (
    <div className="stack">
      <h2>Analytics</h2>
      <section className="card">
        <div className="hd">Delivery buffer by order (hours)</div>
        <div className="bd">
          {watch.isLoading && <Loading />}
          {watch.isError && <ErrorState message="Couldn't load analytics." onRetry={() => watch.refetch()} />}
          {watch.data && data.length === 0 && <div className="state">No scheduled orders yet. Run the optimiser to populate buffers.</div>}
          {data.length > 0 && (
            <div style={{ width: "100%", height: 360 }}>
              <ResponsiveContainer>
                <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e3eaec" />
                  <XAxis dataKey="order" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="buffer" fill="#1f6f78" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}