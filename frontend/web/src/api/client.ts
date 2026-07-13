// Typed fetch wrapper + endpoint functions. All API calls go through here so
// error handling and the base URL live in one place.
import type {
  Product, Order, OrderCreate, BomLine, BomCreate, BomUpdate, Routing, RoutingOp,
  RoutingCreate, RoutingOpCreate, RoutingOpUpdate, ActualEvent, EventCreate,
  DashboardSummary, WatchlistRow, SolveJob, SolveRequest, OrderSchedule,
  AuthUser, TokenResponse, AuditEntry,
  MaterialStatusRow, ImportResult, SandboxOverride, SandboxResult,
  AlertRow, DeviationRow, RecoveryResult, RescheduleLogRow, DelayedOrderRow, RecommendationResult,
  DashboardKpis, KpiDrilldown, BottleneckRec, OvertimeRec, LeadTimeRow, CapacityHeatmap, OrderDetail, CapacityCell, ImportResultT,
} from "./types";

// In dev, Vite proxies /api -> backend. In prod, set VITE_API_BASE.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

// Bearer token holder. Set by the auth layer; attached to every request.
let authToken: string | null = null;
let refreshToken: string | null = null;
let onTokenRefreshed: ((access: string) => void) | null = null;
let onAuthLost: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}
export function setRefreshToken(token: string | null) {
  refreshToken = token;
}
export function setAuthCallbacks(opts: { onRefreshed?: (a: string) => void; onLost?: () => void }) {
  onTokenRefreshed = opts.onRefreshed ?? null;
  onAuthLost = opts.onLost ?? null;
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    authToken = data.access_token;
    onTokenRefreshed?.(data.access_token);
    return true;
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch (e) {
    // network-level failure (server down, CORS, offline)
    throw new ApiError(0, "Can't reach the server. Check that the API is running.", e);
  }
  // transparently refresh the access token once on a 401, then retry
  if (res.status === 401 && refreshToken && !path.startsWith("/auth/")) {
    const ok = await tryRefresh();
    if (ok) {
      return request<T>(path, init);
    }
    onAuthLost?.();
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const detail = (body && (body.detail ?? body.message)) ?? res.statusText;
    const msg = typeof detail === "string" ? detail : "Request failed";
    throw new ApiError(res.status, msg, body);
  }
  return body as T;
}

export const api = {
  // dashboard
  summary: () => request<DashboardSummary>("/dashboard/summary"),
  watchlist: () => request<WatchlistRow[]>("/dashboard/watchlist"),
  capacityConflicts: () => request<Record<string, unknown>[]>("/dashboard/capacity-conflicts"),
  openAlerts: () => request<Record<string, unknown>[]>("/dashboard/open-alerts"),
  kpis: () => request<DashboardKpis>("/dashboard/kpis"),
  kpiDrilldown: (key: string) => request<KpiDrilldown>(`/dashboard/kpi-drilldown/${key}`),
  bottleneckRecommendations: () => request<BottleneckRec[]>("/dashboard/bottleneck-recommendations"),
  overtimeRecommendations: () => request<OvertimeRec[]>("/dashboard/overtime-recommendations"),
  leadTimes: () => request<LeadTimeRow[]>("/lead-times"),
  updateLeadTime: (family: string, body: LeadTimeRow) =>
    request<{ ok: boolean; delivery_lead_days: number }>(`/lead-times/${encodeURIComponent(family)}`,
      { method: "PUT", body: JSON.stringify(body) }),
  delayReasons: () => request<Array<{ root_cause: string; count: number; total_hours: number }>>("/dashboard/delay-reasons"),
  recoveryPipeline: () => request<Array<Record<string, unknown>>>("/dashboard/recovery-pipeline"),
  capacityHeatmap: () => request<CapacityHeatmap>("/dashboard/capacity-heatmap"),
  orderDetail: (orderId: string) => request<OrderDetail>(`/dashboard/order-detail/${orderId}`),
  capacityCell: (workCenter: string, loadDate: string) =>
    request<CapacityCell>(`/dashboard/capacity-cell?work_center=${encodeURIComponent(workCenter)}&load_date=${loadDate}`),
  // data model browser
  dataTables: () => request<Array<{ table: string; description: string; row_count: number | null }>>("/datamodel/tables"),
  tableRows: (table: string) => request<{ table: string; columns: string[]; rows: Array<Record<string, unknown>>; total: number }>(`/datamodel/rows/${table}`),
  // master-data export
  exportLeadTimes: () => request<Array<Record<string, unknown>>>("/import/lead-times/export"),
  exportCalendar: () => request<Array<Record<string, unknown>>>("/import/calendar/export"),
  exportRoutings: () => request<Array<Record<string, unknown>>>("/import/routings/export"),
  // master-data import
  importLeadTimes: (csv: string) => request<ImportResultT>("/import/lead-times", { method: "POST", body: JSON.stringify({ csv }) }),
  importCalendar: (csv: string) => request<ImportResultT>("/import/calendar", { method: "POST", body: JSON.stringify({ csv }) }),
  importRoutings: (csv: string) => request<ImportResultT>("/import/routings", { method: "POST", body: JSON.stringify({ csv }) }),

  // products
  listProducts: () => request<Product[]>("/products"),
  createProduct: (p: { product_id: string; name: string; family: string; routing_id?: number | null }) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(p) }),
  deleteProduct: (pk: number) => request<void>(`/products/${pk}`, { method: "DELETE" }),

  // orders
  listOrders: () => request<Order[]>("/orders"),
  getOrder: (pk: number) => request<Order>(`/orders/${pk}`),
  createOrder: (o: OrderCreate) => request<Order>("/orders", { method: "POST", body: JSON.stringify(o) }),
  updateOrder: (pk: number, patch: Partial<OrderCreate>) =>
    request<Order>(`/orders/${pk}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteOrder: (pk: number) => request<void>(`/orders/${pk}`, { method: "DELETE" }),

  // bom
  listBom: (productId?: number) =>
    request<BomLine[]>(`/bom${productId != null ? `?product_id=${productId}` : ""}`),
  createBom: (b: BomCreate) => request<BomLine>("/bom", { method: "POST", body: JSON.stringify(b) }),
  updateBom: (pk: number, patch: BomUpdate) =>
    request<BomLine>(`/bom/${pk}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteBom: (pk: number) => request<void>(`/bom/${pk}`, { method: "DELETE" }),

  // events
  listEvents: (orderId?: number) =>
    request<ActualEvent[]>(`/events${orderId != null ? `?order_id=${orderId}` : ""}`),
  createEvent: (e: EventCreate) => request<ActualEvent>("/events", { method: "POST", body: JSON.stringify(e) }),

  // routings
  listRoutings: () => request<Routing[]>("/routings"),
  createRouting: (r: RoutingCreate) =>
    request<Routing>("/routings", { method: "POST", body: JSON.stringify(r) }),
  deleteRouting: (pk: number) => request<void>(`/routings/${pk}`, { method: "DELETE" }),
  addOperation: (routingPk: number, op: RoutingOpCreate) =>
    request<RoutingOp>(`/routings/${routingPk}/operations`, { method: "POST", body: JSON.stringify(op) }),
  updateOperation: (routingPk: number, opPk: number, patch: RoutingOpUpdate) =>
    request<RoutingOp>(`/routings/${routingPk}/operations/${opPk}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteOperation: (routingPk: number, opPk: number) =>
    request<void>(`/routings/${routingPk}/operations/${opPk}`, { method: "DELETE" }),

  // scheduling (async solve)
  solve: (req: SolveRequest) =>
    request<SolveJob>("/schedule/solve", { method: "POST", body: JSON.stringify(req) }),
  getJob: (jobId: string) => request<SolveJob>(`/schedule/jobs/${jobId}`),
  getOrderSchedule: (orderId: string) => request<OrderSchedule>(`/schedule/orders/${orderId}`),

  // auth
  login: (username: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: () => request<AuthUser>("/auth/me"),
  refresh: (token: string) => request<{ access_token: string }>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: token }) }),
  logout: (token: string) => request<void>("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: token }) }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  listUsers: () => request<AuthUser[]>("/auth/users"),
  resetDemoData: () => request<{ status: string; scripts_applied: string[]; material_counts: Record<string, number>; note: string }>("/admin/reset-demo-data", { method: "POST" }),
  createUser: (u: { username: string; password: string; full_name?: string; role: string }) =>
    request<AuthUser>("/auth/users", { method: "POST", body: JSON.stringify(u) }),
  auditTrail: (limit = 100) => request<AuditEntry[]>(`/audit?limit=${limit}`),

  // materials / risk
  materialStatus: () => request<MaterialStatusRow[]>("/materials/status"),
  evaluateRisk: () => request<{ counts: Record<string, number> }>("/materials/evaluate-risk", { method: "POST" }),

  // CSV import
  importProducts: (csv: string) => request<ImportResult>("/import/products", { method: "POST", body: JSON.stringify({ csv }) }),
  importBom: (csv: string) => request<ImportResult>("/import/bom", { method: "POST", body: JSON.stringify({ csv }) }),
  importOrders: (csv: string) => request<ImportResult>("/import/orders", { method: "POST", body: JSON.stringify({ csv }) }),

  // what-if sandbox
  simulate: (body: { overrides: SandboxOverride[]; mode?: string; time_budget_s?: number; overtime_hrs_per_day?: number }) =>
    request<SandboxResult>("/sandbox/simulate", { method: "POST", body: JSON.stringify(body) }),

  // alerts & deviations
  alerts: (mine = false, status?: string) =>
    request<AlertRow[]>(`/alerts?mine=${mine}${status ? `&status=${status}` : ""}`),
  ackAlert: (key: string) => request<AlertRow>(`/alerts/${key}/ack`, { method: "POST" }),
  closeAlert: (key: string) => request<AlertRow>(`/alerts/${key}/close`, { method: "POST" }),
  deviations: () => request<DeviationRow[]>("/alerts/deviations"),
  runAlertEngine: () => request<{ capacity: unknown; deviation: unknown }>("/alerts/run-engine", { method: "POST" }),

  // single-order recovery
  recoverOrder: (orderId: string, opts: {
    overtime?: boolean; overtime_hrs?: number; overtime_from?: string | null;
    overtime_to?: string | null; partial_qty?: number | null; mode?: string; time_budget_s?: number;
  }) => request<RecoveryResult>(`/schedule/orders/${orderId}/recover`, { method: "POST", body: JSON.stringify(opts) }),
  rescheduleLog: (orderId: string) =>
    request<RescheduleLogRow[]>(`/schedule/orders/${orderId}/reschedule-log`),
  delayedOrders: () => request<DelayedOrderRow[]>("/dashboard/delayed-orders"),
  recommendRecovery: (orderId: string) =>
    request<RecommendationResult>(`/schedule/orders/${orderId}/recommend`, { method: "POST" }),

  // user admin
  updateUser: (id: number, patch: { full_name?: string; role?: string; is_active?: boolean; password?: string }) =>
    request<AuthUser>(`/auth/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
};

