import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Loading, ErrorState, Modal } from "@/components/ui";
import { downloadCSV } from "@/lib/csv";

function cellText(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "yes" : "no";
  const s = String(v);
  return s.length > 60 ? s.slice(0, 57) + "" : s;
}

export function DataModel() {
  const tables = useQuery({ queryKey: ["data-tables"], queryFn: api.dataTables });
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="stack">
      <p className="muted" style={{ margin: 0 }}>
        Every table in the system with its live row count. Click a table to view its rows.
      </p>

      <section className="card">
        <div className="hd">
          Tables
          {tables.isFetching && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>refreshing</span>}
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {tables.isLoading && <Loading />}
          {tables.isError && <ErrorState message="Couldn't load the data model." onRetry={() => tables.refetch()} />}
          {tables.data && (
            <table>
              <thead><tr><th>Table</th><th>Description</th><th className="num">Rows</th><th></th></tr></thead>
              <tbody>
                {tables.data.map((t) => (
                  <tr key={t.table} style={{ cursor: "pointer" }} onClick={() => setOpen(t.table)} title="View rows">
                    <td className="mono">{t.table}</td>
                    <td>{t.description}</td>
                    <td className="num"><strong>{t.row_count ?? "-"}</strong></td>
                    <td style={{ color: "var(--teal)", fontSize: 12 }}>view </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {open && <TableRowsModal table={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function TableRowsModal({ table, onClose }: { table: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["table-rows", table], queryFn: () => api.tableRows(table) });
  const d = q.data;
  return (
    <Modal
      title={`${table}${d ? ` - ${d.total} rows` : ""}`}
      onClose={onClose}
      footer={
        <>
          {d && d.rows.length > 0 && (
            <button className="ghost" onClick={() => downloadCSV(`${table}.csv`, d.rows, d.columns)}>Download CSV</button>
          )}
          <button className="primary" onClick={onClose}>Close</button>
        </>
      }
    >
      {q.isLoading && <Loading label="Loading rows" />}
      {d && (
        <div style={{ overflowX: "auto", maxHeight: "65vh" }}>
          {d.rows.length === 0 ? (
            <div className="state">This table is empty.</div>
          ) : (
            <table>
              <thead><tr>{d.columns.map((c) => <th key={c} style={{ whiteSpace: "nowrap" }}>{c}</th>)}</tr></thead>
              <tbody>
                {d.rows.map((row, i) => (
                  <tr key={i}>
                    {d.columns.map((c) => <td key={c} title={String(row[c] ?? "")} style={{ whiteSpace: "nowrap" }}>{cellText(row[c])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {d.total > d.rows.length && (
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              Showing the first {d.rows.length} of {d.total} rows. Download CSV for the full set (up to 1000).
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
