import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import type { ImportResult } from "@/api/types";
import { useAuth } from "@/hooks/useAuth";
import { downloadRawCSV, downloadCSV, IMPORT_TEMPLATES } from "@/lib/csv";

type Kind = "orders" | "products" | "bom";

const TEMPLATES: Record<Kind, string> = {
  orders: "order_id,product_id,customer,order_qty,order_date,committed_delivery_date,priority,plant\nORD-9001,P-1001,Acme,250,2026-07-05,2026-07-30,HIGH,Plant A",
  products: "product_id,name,family,route_id\nP-2001,New Widget,Mechanical,R-STD-01",
  bom: "product_id,material,qty_per_unit,uom,supplier,lead_days\nP-2001,Steel plate,1.5,kg,SteelCo,5",
};

const LABELS: Record<Kind, string> = { orders: "Orders", products: "Products", bom: "Bill of materials" };

export function ImportData() {
  const { hasRole } = useAuth();
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>("orders");
  const [text, setText] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canImport = hasRole("planner");

  const onFile = async (file: File) => {
    setText(await file.text());
    setResult(null);
    setError(null);
  };

  const run = async () => {
    setError(null);
    setResult(null);
    if (!text.trim()) {
      setError("Paste CSV or choose a file first.");
      return;
    }
    setBusy(true);
    try {
      const fn = kind === "orders" ? api.importOrders : kind === "products" ? api.importProducts : api.importBom;
      const res = await fn(text);
      setResult(res);
      // refresh affected views
      qc.invalidateQueries();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {!canImport && <div className="banner err">Importing requires the planner role. You can view templates below.</div>}

      <section className="card">
        <div className="hd">CSV import</div>
        <div className="bd stack">
          <p className="muted" style={{ margin: 0 }}>
            Bring in orders, products, or bills of materials from CSV - the data feed
            for now, standing in for an ERP connection. Imports skip rows whose key
            already exists, and report any row-level problems.
          </p>

          <div className="row" style={{ gap: 12 }}>
            <div style={{ width: 220 }}>
              <label>What are you importing?</label>
              <select value={kind} onChange={(e) => { setKind(e.target.value as Kind); setResult(null); setError(null); }}>
                <option value="orders">Orders</option>
                <option value="products">Products</option>
                <option value="bom">Bill of materials</option>
              </select>
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <input type="file" accept=".csv,text/csv" disabled={!canImport}
                onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
            </div>
          </div>

          <div>
            <label>{LABELS[kind]} CSV</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={!canImport}
              spellCheck={false}
              style={{ width: "100%", minHeight: 160, fontFamily: "var(--mono)", fontSize: 12.5,
                       padding: 10, border: "1px solid var(--line)", borderRadius: "var(--r-sm)", resize: "vertical" }}
              placeholder={TEMPLATES[kind]}
            />
            <div className="row" style={{ justifyContent: "space-between", marginTop: 6 }}>
              <div className="row" style={{ gap: 8 }}>
                <button className="ghost" onClick={() => setText(TEMPLATES[kind])}>Insert template</button>
                <button className="ghost" onClick={() => downloadRawCSV(`${kind}_template.csv`, IMPORT_TEMPLATES[kind])}>
                  Download template
                </button>
              </div>
              <button className="primary" onClick={run} disabled={!canImport || busy}>
                {busy ? "Importing" : `Import ${LABELS[kind].toLowerCase()}`}
              </button>
            </div>
          </div>

          {error && <div className="banner err">{error}</div>}
          {result && (
            <div className={`banner ${result.errors.length ? "live" : "ok"}`}>
              <strong>Imported {result.imported}</strong>, skipped {result.skipped} (already existed).
              {result.errors.length > 0 && (
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {result.errors.map((er, i) => <li key={i} style={{ fontSize: 12.5 }}>{er}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="hd">Export current data</div>
        <div className="bd stack">
          <p className="muted" style={{ margin: 0 }}>
            Download what's in the system now as CSV - useful for backups, sharing,
            or re-importing into another environment.
          </p>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="ghost" onClick={async () => {
              const orders = await api.listOrders();
              downloadCSV("orders_export.csv", orders as unknown as Record<string, unknown>[],
                ["order_id", "customer", "order_qty", "priority", "order_date", "committed_delivery_date", "status"]);
            }}>Export orders</button>
            <button className="ghost" onClick={async () => {
              const products = await api.listProducts();
              downloadCSV("products_export.csv", products as unknown as Record<string, unknown>[],
                ["product_id", "name", "family"]);
            }}>Export products</button>
            <button className="ghost" onClick={async () => {
              const mat = await api.materialStatus();
              downloadCSV("material_status_export.csv", mat as unknown as Record<string, unknown>[],
                ["order_id", "status", "planned_ready_dt", "actual_ready_dt", "slip_days", "risk_reason"]);
            }}>Export material status</button>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="hd">Expected columns</div>
        <div className="bd">
          <pre className="mono" style={{ margin: 0, fontSize: 12.5, whiteSpace: "pre-wrap", color: "var(--ink-2)" }}>
            {TEMPLATES[kind]}
          </pre>
        </div>
      </section>
    </div>
  );
}
