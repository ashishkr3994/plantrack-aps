// Small shared presentational components used across screens.
import type { ReactNode } from "react";

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
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
  switch ((status ?? "").toLowerCase()) {
    case "ready":
    case "feasible":
    case "on":
    case "ok":
      return "ok";
    case "risk":
    case "at risk":
    case "med":
      return "warn";
    case "late":
    case "delay":
    case "crit":
    case "critical":
    case "infeasible":
      return "risk";
    case "high":
      return "info";
    default:
      return "muted";
  }
}

export function Modal({
  title, children, footer, onClose,
}: { title: string; children: ReactNode; footer?: ReactNode; onClose: () => void }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="hd">{title}</div>
        <div className="bd">{children}</div>
        {footer && <div className="ft">{footer}</div>}
      </div>
    </div>
  );
}
