import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Modal, PriorityPill } from "@/components/ui";
import { fmtDateTime, fmtHours } from "@/lib/format";
import type { GanttOp, GanttDowntime } from "@/api/types";

// Zoom presets: pixels-per-hour. "Comfortable" is the default -- wide enough
// to read order IDs on typical operations without excessive horizontal scroll.
const ZOOM = { compact: 5, comfortable: 10, wide: 18 } as const;
type ZoomKey = keyof typeof ZOOM;

const ROW_H = 44;
const LABEL_W = 168;
const DAY_MS = 86_400_000;

function startOfDay(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
}

export function Timeline() {
  const gantt = useQuery({ queryKey: ["gantt"], queryFn: api.ganttData });
  const [zoom, setZoom] = useState<ZoomKey>("comfortable");
  const [selected, setSelected] = useState<GanttOp | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pxPerHour = ZOOM[zoom];

  const { workCenters, opsByWc, downtimeByWc, rangeStart, totalWidth, dayTicks, nowLeft } = useMemo(() => {
    const ops = gantt.data?.operations ?? [];
    const downtime = gantt.data?.downtime ?? [];
    if (ops.length === 0) {
      return { workCenters: [] as string[], opsByWc: new Map<string, GanttOp[]>(),
        downtimeByWc: new Map<string, GanttDowntime[]>(), rangeStart: new Date(),
        totalWidth: 0, dayTicks: [] as { left: number; label: string }[], nowLeft: null as number | null };
    }
    const starts = ops.map((o) => new Date(o.start).getTime());
    const ends = ops.map((o) => new Date(o.end).getTime());
    const dtStarts = downtime.map((d) => new Date(d.start).getTime());
    const dtEnds = downtime.map((d) => new Date(d.start).getTime() + d.duration_mins * 60_000);
    const rawStart = Math.min(...starts, ...dtStarts.filter((n) => !isNaN(n)));
    const rawEnd = Math.max(...ends, ...dtEnds.filter((n) => !isNaN(n)));
    const rangeStart = startOfDay(new Date(rawStart));
    const rangeEndPadded = new Date(rawEnd + DAY_MS * 0.5);

    const totalHours = (rangeEndPadded.getTime() - rangeStart.getTime()) / 3_600_000;
    const totalWidth = Math.max(200, Math.ceil(totalHours * pxPerHour));

    const wcSet = new Set<string>();
    ops.forEach((o) => wcSet.add(o.work_center));
    const workCenters = Array.from(wcSet).sort();

    const opsByWc = new Map<string, GanttOp[]>();
    for (const wc of workCenters) opsByWc.set(wc, ops.filter((o) => o.work_center === wc));

    const downtimeByWc = new Map<string, GanttDowntime[]>();
    for (const d of downtime) {
      if (!d.work_center) continue;
      const list = downtimeByWc.get(d.work_center) ?? [];
      list.push(d);
      downtimeByWc.set(d.work_center, list);
    }

    const dayTicks: { left: number; label: string }[] = [];
    for (let t = rangeStart.getTime(); t < rangeEndPadded.getTime(); t += DAY_MS) {
      const left = ((t - rangeStart.getTime()) / 3_600_000) * pxPerHour;
      dayTicks.push({
        left,
        label: new Date(t).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
      });
    }

    const now = Date.now();
    const nowLeft = now >= rangeStart.getTime() && now <= rangeEndPadded.getTime()
      ? ((now - rangeStart.getTime()) / 3_600_000) * pxPerHour
      : null;

    return { workCenters, opsByWc, downtimeByWc, rangeStart, totalWidth, dayTicks, nowLeft };
  }, [gantt.data, pxPerHour]);

  const xFor = (iso: string) => ((new Date(iso).getTime() - rangeStart.getTime()) / 3_600_000) * pxPerHour;

  const jumpToNow = () => {
    if (nowLeft == null || !scrollRef.current) return;
    scrollRef.current.scrollTo({ left: Math.max(0, nowLeft - 200), behavior: "smooth" });
  };

  const unplacedDowntimeCount = (gantt.data?.downtime ?? []).filter((d) => !d.work_center).length;

  return (
    <div className="stack">
      <div className="spread">
        <h2>Schedule timeline</h2>
        <div className="row" style={{ gap: 8 }}>
          {(["compact", "comfortable", "wide"] as ZoomKey[]).map((z) => (
            <button key={z} className={zoom === z ? "primary" : ""} onClick={() => setZoom(z)}>
              {z[0].toUpperCase() + z.slice(1)}
            </button>
          ))}
          {nowLeft != null && <button onClick={jumpToNow}>Jump to now</button>}
        </div>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Every machine's current schedule, side by side. Gaps are idle capacity; hatched bars are
        logged downtime. Click a block for details.
      </p>

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
          {gantt.data && workCenters.length === 0 && (
            <div className="state">No scheduled operations yet. Run a solve to populate the timeline.</div>
          )}
          {workCenters.length > 0 && (
            <div className="gantt-scroll" ref={scrollRef}>
              <div className="gantt-grid" style={{ gridTemplateColumns: `${LABEL_W}px 1fr` }}>
                <div className="gantt-corner" />
                <div className="gantt-header-track" style={{ width: totalWidth }}>
                  {dayTicks.map((t, i) => (
                    <div key={i} className="gantt-day-tick" style={{ left: t.left }}>
                      <span className="gantt-day-line" />
                      <span className="gantt-day-label">{t.label}</span>
                    </div>
                  ))}
                  {nowLeft != null && (
                    <div className="gantt-now-line" style={{ left: nowLeft }}>
                      <span className="gantt-now-label">Now</span>
                    </div>
                  )}
                </div>

                {workCenters.map((wc) => (
                  <div className="gantt-row-pair" key={wc}>
                    <div className="gantt-row-label" style={{ height: ROW_H }}>{wc}</div>
                    <div className="gantt-row-track" style={{ width: totalWidth, height: ROW_H }}>
                      {(downtimeByWc.get(wc) ?? []).map((d, i) => {
                        const left = xFor(d.start);
                        const width = Math.max(6, (d.duration_mins / 60) * pxPerHour);
                        const cleanReason = d.reason.replace(/^\[.*?\]\s*/, "") || "logged pause";
                        const scope = d.whole_wc ? "whole machine down" : `${d.order_id ?? "this order"} only`;
                        return (
                          <div key={`dt-${i}`} className="gantt-downtime" style={{ left, width }}
                            title={`Downtime (${scope}): ${cleanReason}`} />
                        );
                      })}
                      {(opsByWc.get(wc) ?? []).map((op, i) => {
                        const left = xFor(op.start);
                        const width = Math.max(4, xFor(op.end) - left);
                        const cls = op.priority === "HIGH" ? "gantt-block-high"
                          : op.priority === "LOW" ? "gantt-block-low" : "gantt-block-med";
                        return (
                          <button key={i} className={`gantt-block ${cls}`} style={{ left, width }}
                            onClick={() => setSelected(op)}
                            title={`${op.order_id} - ${op.customer}`}>
                            {width > 34 && <span className="gantt-block-label">{op.order_id}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
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

      {selected && (
        <Modal title={selected.order_id} onClose={() => setSelected(null)}>
          <div className="stack">
            <div style={{ marginBottom: 4 }}><PriorityPill priority={selected.priority} /></div>
            <table><tbody>
              <tr><td className="muted">Customer</td><td>{selected.customer}</td></tr>
              <tr><td className="muted">Work centre</td><td>{selected.work_center}</td></tr>
              <tr><td className="muted">Operation seq</td><td>{selected.operation_seq}</td></tr>
              <tr><td className="muted">Start</td><td>{fmtDateTime(selected.start)}</td></tr>
              <tr><td className="muted">End</td><td>{fmtDateTime(selected.end)}</td></tr>
              <tr><td className="muted">Duration</td><td>{fmtHours(
                (new Date(selected.end).getTime() - new Date(selected.start).getTime()) / 3_600_000)}</td></tr>
            </tbody></table>
          </div>
        </Modal>
      )}
    </div>
  );
}
