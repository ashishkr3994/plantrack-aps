import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Empty } from "@/components/ui";

export function Capacity() {
  const conflicts = useQuery({ queryKey: ["capacity-conflicts"], queryFn: api.capacityConflicts });

  return (
    <div className="stack">
      <h2>Capacity</h2>
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
                  <tr key={i}>
                    <td>{String(c.work_center)}</td>
                    <td>{String(c.load_date)}</td>
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
    </div>
  );
}
