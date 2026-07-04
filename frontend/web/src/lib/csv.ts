// CSV export + template download helpers (ported from the prototype's
// downloadCSV / downloadTemplate / entityToCSV). Pure client-side: turns data
// into a CSV blob and triggers a browser download.

function triggerDownload(filename: string, content: string, mime = "text/csv") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Convert an array of row objects to CSV text using the given column order. */
export function toCSV(rows: Record<string, unknown>[], columns?: string[]): string {
  if (rows.length === 0) return columns ? columns.join(",") + "\n" : "";
  const cols = columns ?? Object.keys(rows[0]);
  const header = cols.join(",");
  const body = rows.map((r) => cols.map((c) => escapeCell(r[c])).join(",")).join("\n");
  return `${header}\n${body}\n`;
}

/** Download an array of rows as a CSV file. */
export function downloadCSV(filename: string, rows: Record<string, unknown>[], columns?: string[]) {
  triggerDownload(filename, toCSV(rows, columns));
}

/** Download a raw CSV string (used for templates). */
export function downloadRawCSV(filename: string, csv: string) {
  triggerDownload(filename, csv);
}

// Import templates (header + one example row), matching the importer's expected
// columns.
export const IMPORT_TEMPLATES = {
  orders:
    "order_id,product_id,customer,order_qty,order_date,committed_delivery_date,priority,plant\n" +
    "ORD-9001,P-1001,Acme,250,2026-07-05,2026-07-30,HIGH,Plant A\n",
  products:
    "product_id,name,family,route_id\n" +
    "P-2001,New Widget,Mechanical,R-STD-01\n",
  bom:
    "product_id,material,qty_per_unit,uom,supplier,lead_days\n" +
    "P-2001,Steel plate,1.5,kg,SteelCo,5\n",
} as const;
