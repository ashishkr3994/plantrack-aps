import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState } from "@/components/ui";
import { GanttChart } from "@/components/GanttChart";

export function Timeline() {
  const gantt = useQuery({ queryKey: ["gantt"], queryFn: api.ganttData });
  const [search, setSearch] = useState("");

  const allOrderIds = useMemo(() => {
    const set = new Set((gantt.data?.operations ?? []).map((o) => o.order_id));
    return Array.from(set).sort();
  }, [gantt.data]);

  const filteredOps = useMemo(() => {
    const ops = gantt.data?.operations ?? [];
    if (!search.trim()) return ops;
    const q = search.trim().toLowerCase();
    return ops.filter((o) => o.order_id.toLowerCase().includes(q));
  }, [gantt.data, search]);

  // downtime is shown regardless of the order filter: a machine-wide outage
  // affects every order on that machine, not just the one that logged it, so
  // filtering it out by order would misrepresent the outage's real scope.
  const downtime = gantt.data?.downtime ?? [];

  const unplacedDowntimeCount = downtime.filter((d) => !d.work_center).length;

  return (
    <div className="stack">
      <div className="spread">
        <h2>Schedule timeline</h2>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Every machine's current schedule, side by side. Gaps are idle capacity; hatched bars are
        logged downtime. Click a block for details.
      </p>

      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input type="search" placeholder="Filter by Order ID..." value={search}
          onChange={(e) => setSearch(e.target.value)} style={{ width: 220 }} />
        {search && <button className="ghost" onClick={() => setSearch("")}>Clear</button>}
        {search && (
          <span className="muted" style={{ fontSize: 12 }}>
            {new Set(filteredOps.map((o) => o.order_id)).size} of {allOrderIds.length} orders shown
          </span>
        )}
      </div>

      <div className="gantt-legend">
        <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-high" />High priority</span>
        <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-med" />Medium priority</span>
        <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-low" />Low priority</span>
        <span className="gantt-legend-item"><i className="gantt-swatch gantt-swatch-downtime" />Downtime</span>
      </div>

      <section className="card">
        <div className="bd" style={{ padding: 0 }}>
          {gantt.isLoading && <Loading />}
          {gantt.isError && <ErrorState message="Couldn't load the timeline." onRetry={() => gantt.refetch()} />}
          {gantt.data && filteredOps.length === 0 && (
            <div className="state">
              {search ? "No operations match that Order ID filter." : "No scheduled operations yet. Run a solve to populate the timeline."}
            </div>
          )}
          {filteredOps.length > 0 && (
            <div style={{ padding: 12 }}>
              <GanttChart operations={filteredOps} downtime={downtime} />
            </div>
          )}
        </div>
      </section>

      {unplacedDowntimeCount > 0 && (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          {unplacedDowntimeCount} logged pause{unplacedDowntimeCount > 1 ? "s" : ""} couldn't be matched to a
          machine on the current schedule (the referenced operation may no longer exist) and aren't shown.
        </p>
      )}
    </div>
  );
}
