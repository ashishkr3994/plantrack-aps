import { useState } from "react";
import { ImportData } from "./ImportData";
import { MasterDataImportPanel } from "./MasterData";

type Tab = "orders" | "master";

export function ImportExport() {
  const [tab, setTab] = useState<Tab>("orders");
  return (
    <div className="stack">
      <h2>Import &amp; export</h2>
      <div className="row" style={{ gap: 8 }}>
        <button className={tab === "orders" ? "primary" : ""} onClick={() => setTab("orders")}>
          Orders, products &amp; BOM
        </button>
        <button className={tab === "master" ? "primary" : ""} onClick={() => setTab("master")}>
          Master data templates
        </button>
      </div>
      {tab === "orders" ? <ImportData /> : <MasterDataImportPanel />}
    </div>
  );
}
