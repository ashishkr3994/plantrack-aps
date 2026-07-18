import { useState } from "react";
import { Configuration } from "./Configuration";
import { LeadTimesEditor } from "./MasterData";
import { DataModel } from "./DataModel";

type Tab = "routings" | "lead_times" | "data_model";

export function SetupReference() {
  const [tab, setTab] = useState<Tab>("routings");
  return (
    <div className="stack">
      <h2>Setup &amp; reference</h2>
      <div className="row" style={{ gap: 8 }}>
        <button className={tab === "routings" ? "primary" : ""} onClick={() => setTab("routings")}>
          Routings
        </button>
        <button className={tab === "lead_times" ? "primary" : ""} onClick={() => setTab("lead_times")}>
          Lead times
        </button>
        <button className={tab === "data_model" ? "primary" : ""} onClick={() => setTab("data_model")}>
          Data model
        </button>
      </div>
      {tab === "routings" && <Configuration />}
      {tab === "lead_times" && <LeadTimesEditor />}
      {tab === "data_model" && <DataModel />}
    </div>
  );
}
