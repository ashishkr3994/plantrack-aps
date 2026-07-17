import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Empty, Pill } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";

function alertTone(t: string): "risk" | "warn" | "info" {
  return t === "crit" ? "risk" : t === "warn" ? "warn" : "info";
}
function sevTone(s: string): "risk" | "warn" | "muted" {
  return s === "Critical" ? "risk" : s === "High" ? "warn" : "muted";
}

export function Alerts() {
  const { hasRole } = useAuth();
  const qc = useQueryClient();
  const [mine, setMine] = useState(true);
  const [hideClosed, setHideClosed] = useState(true);

  const alerts = useQuery({
    queryKey: ["alerts", mine],
    queryFn: () => api.alerts(mine),
  });
  const canRun = hasRole("planner");

  const ack = useMutation({
    mutationFn: (key: string) => api.ackAlert(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const close = useMutation({
    mutationFn: (key: string) => api.closeAlert(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const runEngine = useMutation({
    mutationFn: () => api.runAlertEngine(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["deviations"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["gantt"] });
    },
  });

  const rows = (alerts.data ?? []).filter((a) => !hideClosed || a.status !== "closed");

  return (
    <div className="stack">
      <div className="spread">
        <h2>Alerts</h2>
        <div className="row" style={{ gap: 10 }}>
          {canRun && (
            <button onClick={() => runEngine.mutate()} disabled={runEngine.isPending}>
              {runEngine.isPending ? "Checking" : "Check for deviations now"}
            </button>
          )}
        </div>
      </div>

      <div className="row" style={{ gap: 16 }}>
        <label className="row" style={{ gap: 6, fontSize: 13 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={mine} onChange={(e) => setMine(e.target.checked)} />
          Only alerts for my role
        </label>
        <label className="row" style={{ gap: 6, fontSize: 13 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={hideClosed} onChange={(e) => setHideClosed(e.target.checked)} />
          Hide closed
        </label>
      </div>

      <section className="card">
        <div className="hd">Active alerts</div>
        <div className="bd" style={{ padding: 0 }}>
          {alerts.isLoading && <Loading />}
          {alerts.isError && <ErrorState message="Couldn't load alerts." onRetry={() => alerts.refetch()} />}
          {alerts.data && rows.length === 0 && (
            <Empty message={mine ? "No alerts for your role right now." : "No alerts. Run a solve, then check for deviations."} />
          )}
          {rows.length > 0 && (
            <table>
              <thead>
                <tr><th>Severity</th><th>Alert</th><th>Detail</th><th>Status</th><th style={{ width: 150 }}>Actions</th></tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.dedup_key}>
                    <td><Pill tone={alertTone(a.alert_type)}>{a.alert_type}</Pill></td>
                    <td>{a.title}</td>
                    <td className="muted" style={{ fontSize: 12.5 }}>{a.meta}</td>
                    <td>
                      {a.status === "open" && <Pill tone="warn">open</Pill>}
                      {a.status === "ack" && <Pill tone="info">acknowledged</Pill>}
                      {a.status === "closed" && <Pill tone="muted">closed</Pill>}
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        {a.status === "open" && (
                          <button className="ghost" onClick={() => ack.mutate(a.dedup_key)} disabled={ack.isPending}>Ack</button>
                        )}
                        {a.status !== "closed" && (
                          <button className="ghost" onClick={() => close.mutate(a.dedup_key)} disabled={close.isPending}>Close</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <Deviations />
    </div>
  );
}

function Deviations() {
  const devs = useQuery({ queryKey: ["deviations"], queryFn: api.deviations });
  return (
    <section className="card">
      <div className="hd">Deviations vs baseline</div>
      <div className="bd" style={{ padding: 0 }}>
        {devs.isLoading && <Loading />}
        {devs.isError && <ErrorState message="Couldn't load deviations." onRetry={() => devs.refetch()} />}
        {devs.data && devs.data.length === 0 && <div className="state">No forecast deviations from baseline.</div>}
        {devs.data && devs.data.length > 0 && (
          <table>
            <thead>
              <tr><th>Severity</th><th>Milestone</th><th className="num">Slip (min)</th><th>Root cause</th><th>Owner</th><th>Status</th></tr>
            </thead>
            <tbody>
              {devs.data.map((d) => (
                <tr key={d.deviation_id}>
                  <td><Pill tone={sevTone(d.severity)}>{d.severity}</Pill></td>
                  <td>{d.milestone_name}</td>
                  <td className="num">{Math.round(d.deviation_minutes)}</td>
                  <td className="muted">{d.root_cause_code ?? "-"}</td>
                  <td>{d.action_owner ?? "-"}</td>
                  <td>{d.resolution_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
