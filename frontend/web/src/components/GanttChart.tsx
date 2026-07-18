import { useMemo, useRef, useState } from "react";
import { Modal, PriorityPill } from "@/components/ui";
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

export interface GanttRange { start: Date; end: Date; }

/** Compute a shared time range across one or more operation/downtime sets, so
 * multiple GanttChart instances (e.g. live vs what-if side by side) can be
 * aligned on the same X axis for a genuine visual comparison. */
export function computeSharedRange(sets: { operations: GanttOp[]; downtime: GanttDowntime[] }[]): GanttRange | null {
  const starts: number[] = [];
  const ends: number[] = [];
  for (const s of sets) {
    for (const o of s.operations) { starts.push(new Date(o.start).getTime()); ends.push(new Date(o.end).getTime()); }
    for (const d of s.downtime) {
      const t = new Date(d.start).getTime();
      if (!isNaN(t)) { starts.push(t); ends.push(t + d.duration_mins * 60_000); }
    }
  }
  if (starts.length === 0) return null;
  return { start: startOfDay(new Date(Math.min(...starts))), end: new Date(Math.max(...ends) + DAY_MS * 0.5) };
}

export function GanttChart({ operations, downtime, range, zoom, onZoomChange }: {
  operations: GanttOp[]; downtime: GanttDowntime[];
  range?: GanttRange | null;         // shared range override, for aligned comparisons
  zoom?: ZoomKey; onZoomChange?: (z: ZoomKey) => void;
}) {
  const [localZoom, setLocalZoom] = useState<ZoomKey>("comfortable");
  const activeZoom = zoom ?? localZoom;
  const setZoom = onZoomChange ?? setLocalZoom;
  const [selected, setSelected] = useState<GanttOp | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pxPerHour = ZOOM[activeZoom];

  const { workCenters, opsByWc, downtimeByWc, rangeStart, totalWidth, dayTicks, nowLeft } = useMemo(() => {
    if (operations.length === 0) {
      return { workCenters: [] as string[], opsByWc: new Map<string, GanttOp[]>(),
        downtimeByWc: new Map<string, GanttDowntime[]>(), rangeStart: new Date(),
        totalWidth: 0, dayTicks: [] as { left: number; label: string }[], nowLeft: null as number | null };
    }
    const computed = computeSharedRange([{ operations, downtime }]);
    const rangeStart = range?.start ?? computed?.start ?? startOfDay(new Date());
    const rangeEndPadded = range?.end ?? computed?.end ?? new Date();

    const totalHours = (rangeEndPadded.getTime() - rangeStart.getTime()) / 3_600_000;
    const totalWidth = Math.max(200, Math.ceil(totalHours * pxPerHour));

    const wcSet = new Set<string>();
    operations.forEach((o) => wcSet.add(o.work_center));
    const workCenters = Array.from(wcSet).sort();

    const opsByWc = new Map<string, GanttOp[]>();
    for (const wc of workCenters) opsByWc.set(wc, operations.filter((o) => o.work_center === wc));

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
  }, [operations, downtime, pxPerHour, range]);

  const xFor = (iso: string) => ((new Date(iso).getTime() - rangeStart.getTime()) / 3_600_000) * pxPerHour;

  const jumpToNow = () => {
    if (nowLeft == null || !scrollRef.current) return;
    scrollRef.current.scrollTo({ left: Math.max(0, nowLeft - 200), behavior: "smooth" });
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
        {(["compact", "comfortable", "wide"] as ZoomKey[]).map((z) => (
          <button key={z} className={activeZoom === z ? "primary" : ""} onClick={() => setZoom(z)}>
            {z[0].toUpperCase() + z.slice(1)}
          </button>
        ))}
        {nowLeft != null && <button onClick={jumpToNow}>Jump to now</button>}
      </div>

      {workCenters.length === 0 ? (
        <div className="state">No scheduled operations to show.</div>
      ) : (
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
              <tr><td className="muted">Scheduled window</td><td>{fmtHours(
                (new Date(selected.end).getTime() - new Date(selected.start).getTime()) / 3_600_000)}</td></tr>
              {selected.busy_hrs != null && (
                <tr><td className="muted">Busy time</td><td>{fmtHours(selected.busy_hrs)}</td></tr>
              )}
            </tbody></table>
            {selected.busy_hrs != null && (
              (new Date(selected.end).getTime() - new Date(selected.start).getTime()) / 3_600_000
              - selected.busy_hrs > 1 && (
                <p className="muted" style={{ margin: 0, fontSize: 11.5 }}>
                  The scheduled window is longer than the busy time because this operation spans a
                  shift/overnight gap -- the machine wasn't actually working the whole time.
                </p>
              )
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
