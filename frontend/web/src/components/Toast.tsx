import { createContext, useCallback, useContext, useState, ReactNode } from "react";

// Lightweight, non-blocking toast notifications. A single provider mounted at
// the app root renders a fixed corner stack; any component calls useToast() and
// fires toast.success(...) / toast.error(...) / toast.info(...). Each toast
// auto-dismisses after a few seconds and can be dismissed manually. Toasts
// never block interaction -- they float above the UI and fade on their own.

type ToastKind = "success" | "error" | "info";
interface ToastItem { id: number; kind: ToastKind; message: string; }

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

let _id = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = ++_id;
    setToasts((t) => [...t, { id, kind, message }]);
    // auto-dismiss: errors linger a little longer than confirmations
    const ttl = kind === "error" ? 6000 : 4000;
    window.setTimeout(() => remove(id), ttl);
  }, [remove]);

  const api: ToastApi = {
    success: (m) => push("success", m),
    error: (m) => push("error", m),
    info: (m) => push("info", m),
  };

  const icon = (k: ToastKind) => (k === "success" ? "OK" : k === "error" ? "!" : "i");

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-icon" aria-hidden="true">{icon(t.kind)}</span>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-close" aria-label="Dismiss" onClick={() => remove(t.id)}>&times;</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Access the toast API. Safe no-op if used outside the provider. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return { success: () => {}, error: () => {}, info: () => {} };
  }
  return ctx;
}
