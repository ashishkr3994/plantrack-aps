// Shared display formatters. Centralising these keeps dates, numbers and
// durations consistent across every screen (previously fmtDate was duplicated
// per-screen with slightly different behaviour).

/** Absolute date, e.g. "13 Jul 2026". Safe on null/invalid input. */
export function fmtDate(s: unknown): string {
  if (s == null || s === "") return "-";
  const d = new Date(s as string);
  if (isNaN(d.getTime())) return String(s);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/** Date + time, e.g. "13 Jul 2026, 14:30". */
export function fmtDateTime(s: unknown): string {
  if (s == null || s === "") return "-";
  const d = new Date(s as string);
  if (isNaN(d.getTime())) return String(s);
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/**
 * Relative date phrase from now, e.g. "due in 3 days", "2 days ago", "today".
 * Rounds to whole days. Returns "" for null/invalid so callers can omit it.
 */
export function fmtRelativeDate(s: unknown): string {
  if (s == null || s === "") return "";
  const d = new Date(s as string);
  if (isNaN(d.getTime())) return "";
  const days = Math.round((d.getTime() - Date.now()) / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  if (days > 1) return `in ${days} days`;
  return `${Math.abs(days)} days ago`;
}

/** Integer/float with thousands separators, e.g. 12500 -> "12,500". */
export function fmtNum(n: number | string | null | undefined, digits = 0): string {
  if (n == null || n === "") return "-";
  const v = typeof n === "string" ? Number(n) : n;
  if (isNaN(v as number)) return String(n);
  return (v as number).toLocaleString(undefined, {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

/**
 * Human-friendly duration from hours. Prefers days when large:
 *   3   -> "3h"
 *   48  -> "2 days"
 *   52  -> "2 days 4h"
 * Negative buffer (lateness) is the common caller; pass Math.abs and label.
 */
export function fmtHours(hrs: number | string | null | undefined): string {
  if (hrs == null || hrs === "") return "-";
  const h = typeof hrs === "string" ? Number(hrs) : hrs;
  if (isNaN(h as number)) return String(hrs);
  const abs = Math.abs(h as number);
  if (abs < 24) return `${Math.round(abs * 10) / 10}h`;
  const days = Math.floor(abs / 24);
  const rem = Math.round(abs - days * 24);
  return rem > 0 ? `${days} day${days > 1 ? "s" : ""} ${rem}h`
                 : `${days} day${days > 1 ? "s" : ""}`;
}

/**
 * Buffer/lateness phrase from hours: positive -> "2 days early",
 * negative -> "2 days late", ~0 -> "on time".
 */
export function fmtBufferPhrase(hrs: number | string | null | undefined): string {
  if (hrs == null || hrs === "") return "-";
  const h = typeof hrs === "string" ? Number(hrs) : hrs;
  if (isNaN(h as number)) return String(hrs);
  if (Math.abs(h as number) < 1) return "on time";
  const mag = fmtHours(Math.abs(h as number));
  return (h as number) < 0 ? `${mag} late` : `${mag} early`;
}

/**
 * Fine-grained relative time for freshness labels: "just now", "3 min ago",
 * "2 hours ago", falling back to a date for older timestamps.
 */
export function fmtRelativeTime(s: unknown): string {
  if (s == null || s === "") return "";
  const d = new Date(s as string);
  if (isNaN(d.getTime())) return "";
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs > 1 ? "s" : ""} ago`;
  return fmtDate(s);
}
