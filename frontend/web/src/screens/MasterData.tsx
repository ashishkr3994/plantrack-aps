import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Pill } from "@/components/ui";
import { downloadCSV, downloadRawCSV, MASTER_TEMPLATES } from "@/lib/csv";
import type { ImportResultT } from "@/api/types";

type Entity = "calendar" | "lead_times" | "routings";

const ENTITIES: Array<{ key: Entity; label: string; desc: string }> = [
  { key: "calendar", label: "Plant calendar", desc: "Working shifts & holidays per plant" },
  { key: "lead_times", label: "Lead-time master", desc: "Inbound / QA / packing / transport / buffer days by product family" },
  { key: "routings", label: "Routing & operations", desc: "Process routings and their operation steps" },
];

const EXPORTERS: Record<Entity, () => Promise<Array<Record<string, unknown>>>> = {
  calendar: api.exportCalendar,
  lead_times: api.exportLeadTimes,
  routings: api.exportRoutings,
};
const IMPORTERS: Record<Entity, (csv: string) => Promise<ImportResultT>> = {
  calendar: api.importCalendar,
  lead_times: api.importLeadTimes,
  routings: api.importRoutings,
};

export function MasterData() {
  const { hasRole } = useAuth();
  const canImport = hasRole("planner");
  const qc = useQueryClient();
  const [entity, setEntity] = useState<Entity>("calendar");
  const [text, setText] = useState("");
  const [result, setResult] = useState<ImportResultT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const meta = ENTITIES.find((e) => e.key === entity)!;

  const doExport = async () => {
    setError(null);
    try {
      const rows = await EXPORTERS[entity]();
      if (rows.length === 0) { setError("Nothing to export — this table is empty."); return; }
      downloadCSV(`${entity}_export.csv`, rows);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Export failed.");
    }
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(f);
  };

  const doImport = async () => {
    setError(null); setResult(null);
    if (!text.trim()) { setError("Paste CSV or choose a file first."); return; }
    setBusy(true);
    try {
      const res = await IMPORTERS[entity](text);
      setResult(res);
      qc.invalidateQueries({ queryKey: ["data-tables"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <h2>Master data</h2>
      <p className="muted" style={{ margin: 0 }}>
        Download the current plant calendar, lead-time master, and routing & operations,
        grab a blank template, or import updated data — all in one place.
      </p>

      {!canImport && <div className="banner err">Importing requires the planner role. You can still download data and templates.</div>}

      <section className="card">
        <div className="hd">Choose a data set</div>
        <div className="bd">
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            {ENTITIES.map((e) => (
              <button key={e.key} className={entity === e.key ? "primary" : "ghost"}
                onClick={() => { setEntity(e.key); setResult(null); setError(null); setText(""); }}>
                {e.label}
              </button>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 10, marginBottom: 0 }}>{meta.desc}</p>
        </div>
      </section>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <section className="card">
          <div className="hd">Download</div>
          <div className="bd stack">
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>Current data or a blank template for {meta.label.toLowerCase()}.</p>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="ghost" onClick={doExport}>Download current data</button>
              <button className="ghost" onClick={() => downloadRawCSV(`${entity}_template.csv`, MASTER_TEMPLATES[entity])}>Download template</button>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="hd">Import</div>
          <div className="bd stack">
            <input type="file" accept=".csv,text/csv" disabled={!canImport}
              onChange={(e) => onFile(e.target.files?.[0])} />
            <textarea rows={6} placeholder={`Paste ${meta.label} CSV here…`} value={text}
              disabled={!canImport} onChange={(e) => setText(e.target.value)}
              style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 12.5, padding: 10,
                       border: "1px solid var(--line)", borderRadius: "var(--r-sm)", resize: "vertical" }} />
            <div className="row" style={{ gap: 8 }}>
              <button className="ghost" onClick={() => setText(MASTER_TEMPLATES[entity])} disabled={!canImport}>Insert template</button>
              <button className="primary" onClick={doImport} disabled={!canImport || busy}>{busy ? "Importing…" : "Import"}</button>
            </div>
          </div>
        </section>
      </div>

      {error && <div className="banner err">{error}</div>}
      {result && (
        <div className={`banner ${result.errors.length ? "err" : "ok"}`}>
          <strong>Imported {result.imported}</strong>, skipped {result.skipped} (duplicates).
          {result.errors.length > 0 && (
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {result.errors.slice(0, 10).map((e, i) => <li key={i} style={{ fontSize: 12.5 }}>{e}</li>)}
              {result.errors.length > 10 && <li style={{ fontSize: 12.5 }}>…and {result.errors.length - 10} more</li>}
            </ul>
          )}
        </div>
      )}

      <section className="card">
        <div className="hd">Template columns</div>
        <div className="bd">
          <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
            <Pill tone="info">{meta.label}</Pill> expects these columns:
          </p>
          <pre className="mono" style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap" }}>
            {MASTER_TEMPLATES[entity].split("\n")[0]}
          </pre>
        </div>
      </section>
    </div>
  );
}
