// Small shared presentational components used across screens.
import type { ReactNode } from "react";

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />;
}

export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="state">
      <Spinner /> <span style={{ marginLeft: 8 }}>{label}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state">
      <div className="banner err" style={{ display: "inline-block", textAlign: "left" }}>
        {message}
      </div>
      {onRetry && (
        <div style={{ marginTop: 12 }}>
          <button onClick={onRetry}>Try again</button>
        </div>
      )}
    </div>
  );
}

export function Empty({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="state">
      <p>{message}</p>
      {action}
    </div>
  );
}

type Tone = "ok" | "warn" | "risk" | "info" | "muted";
export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

// Map a status/priority string to a pill tone.
export function statusTone(status: string | null | undefined): Tone {
  // Health/status severity ONLY. Red (risk) = bad, amber (warn) = at-risk,
  // green (ok) = good. Priority is handled separately by PriorityPill so that
  // priority level never borrows a health colour.
  switch ((status ?? "").toLowerCase()) {
    case "ready":
    case "feasible":
    case "on":
    case "on track":
    case "ok":
      return "ok";
    case "risk":
    case "at risk":
      return "warn";
    case "late":
    case "delay":
    case "crit":
    case "critical":
    case "infeasible":
      return "risk";
    default:
      return "muted";
  }
}

/**
 * Priority pill with its own neutral, weight-based styling -- deliberately
 * separate from health colours so a HIGH-priority healthy order is not shown
 * in a warning/alert colour. HIGH reads as emphasised, LOW as muted.
 */
export function PriorityPill({ priority }: { priority: string | null | undefined }) {
  const p = (priority ?? "").toUpperCase();
  const cls = p === "HIGH" ? "pill-prio-high" : p === "LOW" ? "pill-prio-low" : "pill-prio-med";
  return <span className={`pill ${cls}`}>{p || "-"}</span>;
}

export function Modal({
  title, children, footer, onClose, size,
}: { title: string; children: ReactNode; footer?: ReactNode; onClose: () => void; size?: "lg" }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className={`modal${size === "lg" ? " modal-lg" : ""}`} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="hd">{title}</div>
        <div className="bd">{children}</div>
        {footer && <div className="ft">{footer}</div>}
      </div>
    </div>
  );
}
