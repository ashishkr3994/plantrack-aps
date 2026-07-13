// Types mirroring the backend Pydantic schemas (backend/app/schemas.py).
export type Priority = "HIGH" | "MED" | "LOW";
export type SchedMode = "backward" | "forward";

export interface Product {
  id: number;
  product_id: string;
  name: string;
  family: string;
  routing_id: number | null;
  is_active: boolean;
}

export interface Order {
  id: number;
  order_id: string;
  product_id: number;
  customer: string;
  order_qty: number;
  order_date: string;
  committed_delivery_date: string;
  priority: Priority;
  plant_id: number | null;
  sched_mode: SchedMode;
  replan_count: number;
}

export interface OrderCreate {
  order_id: string;
  product_id: number;
  customer: string;
  order_qty: number;
  order_date: string;
  committed_delivery_date: string;
  priority?: Priority;
  plant_id?: number | null;
  sched_mode?: SchedMode;
}

export interface BomLine {
  id: number;
  product_id: number;
  material: string;
  qty_per_unit: number;
  uom: string;
  supplier: string | null;
  lead_days: number;
}

export interface BomCreate {
  product_id: number;
  material: string;
  qty_per_unit: number;
  uom: string;
  supplier?: string | null;
  lead_days?: number;
}

export interface BomUpdate {
  material?: string;
  qty_per_unit?: number;
  uom?: string;
  supplier?: string | null;
  lead_days?: number;
}

export interface RoutingOp {
  id: number;
  operation_seq: number;
  work_center: string;
  setup_min: number | null;
  run_per_unit_min: number | null;
  queue_min: number | null;
  move_min: number | null;
  predecessor_seq: number | null;
  parallel_group: string | null;
}

export interface Routing {
  id: number;
  route_id: string;
  description: string | null;
  operations: RoutingOp[];
}

export interface RoutingCreate {
  route_id: string;
  description?: string | null;
}

export interface RoutingOpCreate {
  operation_seq: number;
  work_center: string;
  setup_min?: number;
  run_per_unit_min?: number;
  queue_min?: number;
  move_min?: number;
  predecessor_seq?: number | null;
  parallel_group?: string | null;
}

export type RoutingOpUpdate = Partial<RoutingOpCreate>;

export interface EventCreate {
  event_id: string;
  order_id: number;
  operation_seq?: number | null;
  event_type: string;
  event_timestamp: string;
  event_qty?: number | null;
  downtime_reason?: string | null;
  downtime_mins?: number;
  downtime_whole_wc?: boolean;
  entered_by?: string | null;
}

export interface ActualEvent extends EventCreate {
  id: number;
}

export interface DashboardSummary {
  orders: number;
  products: number;
  open_alerts: number;
  capacity_conflicts: number;
  material_at_risk: number;
}

export interface WatchlistRow {
  order_id: string;
  customer: string;
  order_qty: number;
  priority: Priority;
  committed_delivery_date: string;
  product_name: string;
  product_family: string;
  buffer_hrs: number | null;
  schedule_status: string | null;
  material_status: string | null;
  planned_delivery_dt: string | null;
}

// --- scheduling / async solve ---
export type SolveStatus = "queued" | "running" | "succeeded" | "failed";

export interface SolveJob {
  job_id: string;
  status: SolveStatus;
  result: {
    status: string;
    feasible: boolean;
    makespan: number | null;
    weighted_tardiness: number;
    wall_time_s: number;
    orders_total: number;
    orders_on_time: number;
    bottleneck_machine?: string | null;
    machine_load_min?: Record<string, number>;
    late_orders?: Array<{ order_id: string; reason: string | null }>;
  } | null;
  error: string | null;
}

export interface SolveRequest {
  mode?: SchedMode;
  time_budget_s?: number;
  order_ids?: string[] | null;
  leveling?: "off" | "soft" | "strict";
}

export interface OrderSchedule {
  order_id: string;
  schedule: Record<string, unknown> | null;
  operations: Array<{
    operation_seq: number;
    work_center: string;
    parallel_group: string | null;
    predecessor_operation_seq: number | null;
    planned_start: string;
    planned_end: string;
    duration_mins: number;
  }>;
}


// --- auth ---
export type Role = "admin" | "planner" | "supervisor" | "procurement" | "viewer";

export interface AuthUser {
  id: number;
  username: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: Role;
  username: string;
}

export interface AuditEntry {
  id: number;
  actor_username: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  at: string | null;
}


// --- Phase 5: materials, import, sandbox ---
export interface MaterialStatusRow {
  order_id: string;
  material_count: number;
  max_lead_days: number;
  planned_ready_dt: string | null;
  actual_ready_dt: string | null;
  status: "ordered" | "ready" | "risk" | "late";
  slip_days: number;
  risk_reason: string | null;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface SandboxOverride {
  order_id: string;
  qty?: number | null;
  priority?: string | null;
  committed_due_dt?: string | null;
  exclude?: boolean;
  partial_qty?: number | null;
}

export interface SandboxSummary {
  status: string;
  feasible: boolean;
  makespan: number | null;
  weighted_tardiness: number;
  orders_total: number;
  orders_on_time: number;
  wall_time_s: number;
  bottleneck?: string | null;
}

export interface SandboxOrderResult {
  order_id: string;
  mode: string;
  start_dt: string | null;
  finish_dt: string | null;
  due_dt: string | null;
  on_time: boolean;
  lateness_min: number;
  baseline_finish_dt: string | null;
  baseline_lateness_min: number | null;
  changed: boolean;
  reason: string | null;
}

export interface SandboxOpResult {
  order_id: string;
  operation_seq: number;
  work_center: string;
  start_dt: string | null;
  finish_dt: string | null;
  baseline_work_center: string | null;
  baseline_start_dt: string | null;
  moved: boolean;
}

export interface SandboxResult {
  mode: string;
  question: string;
  baseline: SandboxSummary;
  scenario: SandboxSummary;
  orders: SandboxOrderResult[];
  operations: SandboxOpResult[];
  applied_changes: string[];
  note: string;
  baseline_order_count: number;
}


// --- Phase 6: alerts & deviations ---
export interface AlertRow {
  alert_id: string;
  dedup_key: string;
  alert_type: "crit" | "warn" | "info";
  title: string;
  meta: string | null;
  status: "open" | "ack" | "closed";
  raised_at: string | null;
}

export interface DeviationRow {
  deviation_id: string;
  order_id: number;
  milestone_name: string;
  baseline_dt: string | null;
  latest_forecast_dt: string | null;
  deviation_minutes: number;
  severity: "Medium" | "High" | "Critical";
  root_cause_code: string | null;
  action_owner: string | null;
  resolution_status: string;
}


// --- Phase 7: recovery ---
export interface RecoveryResult {
  feasible: boolean;
  status?: string;
  message?: string;
  order_id?: string;
  version?: number;
  baseline_delivery?: string | null;
  new_delivery?: string | null;
  on_time?: boolean | null;
  lateness_min?: number | null;
  bottleneck?: string | null;
  options?: Record<string, unknown>;
}

export interface RescheduleLogRow {
  version: number;
  options: Record<string, unknown>;
  baseline_delivery: string | null;
  new_delivery: string | null;
  performed_by: string | null;
  performed_at: string | null;
}

// --- Tier 2: richer dashboard ---
export interface DashboardKpis {
  orders: number;
  products: number;
  scheduled: number;
  schedule_adherence_pct: number | null;
  on_time_delivery_pct: number | null;
  orders_at_risk: number;
  delayed_critical: number;
  material_at_risk: number;
  capacity_conflicts: number;
  open_alerts: number;
  last_updated?: string | null;
}

export interface KpiReason { type: "time" | "buffer" | "material" | "capacity"; text: string; }
export interface KpiDrillRow {
  order_id?: string; product_id?: number; customer?: string; priority?: string;
  status?: string; slip_hrs?: number; buffer_health?: number; reasons?: KpiReason[];
  // capacity rows
  work_center?: string; load_date?: string; demand_min?: number; available_min?: number;
}
export interface KpiDrilldown { title: string; subtitle: string; rows: KpiDrillRow[]; }

export interface BottleneckRec {
  work_center: string;
  overloaded_days: number;
  total_days: number;
  peak_load_pct: number;
  avg_overload_pct: number;
  recommendation: string;
}

export interface HeatmapCell { date: string; load_pct: number | null; overloaded: boolean; }
export interface CapacityHeatmap {
  work_centers: string[];
  dates: string[];
  grid: Array<{ work_center: string; cells: HeatmapCell[] }>;
}

export interface OrderDetail {
  order: Record<string, unknown> | null;
  product: Record<string, unknown> | null;
  schedule: Record<string, unknown> | null;
  operations: Array<Record<string, unknown>>;
  risk_signals: Array<Record<string, unknown>>;
  material: Record<string, unknown> | null;
  bom: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
}

// --- Tier 2b: capacity cell drill-down + event logging ---
export interface CapacityCell {
  work_center: string;
  load_date: string;
  load: { available_min: number; demand_min: number; load_pct: number; overloaded: boolean } | null;
  operations: Array<{
    order_id: string; customer: string; priority: string;
    operation_seq: number; work_center: string; duration_mins: number;
    planned_start: string; planned_end: string;
  }>;
}

// --- master-data import result ---
export interface ImportResultT {
  imported: number;
  skipped: number;
  errors: string[];
}

// --- delayed/critical drill-down + recommendation ---
export interface DelayedOrderRow {
  order_id: string;
  customer: string;
  priority: string;
  order_qty: number;
  committed_delivery_date: string;
  milestone_name: string;
  severity: string;
  root_cause_code: string | null;
  deviation_minutes: number | null;
  action_owner: string | null;
  generated_at: string;
}

export interface RecommendationResult {
  feasible: boolean;
  order_id?: string;
  recommended_overtime_hrs?: number;
  projected_on_time?: boolean;
  baseline_lateness_hrs?: number;
  projected_lateness_hrs?: number;
  hours_recovered?: number;
  bottleneck_machine?: string | null;
  message: string;
}
