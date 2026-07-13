import { useMemo, useState } from "react";
import { useOrders, useProducts, useCreateOrder } from "@/hooks/queries";
import { Loading, ErrorState, PriorityPill, Modal } from "@/components/ui";
import { fmtDate, fmtNum } from "@/lib/format";
import { ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import type { OrderCreate, Priority, SchedMode } from "@/api/types";

type SortKey = "order_id" | "committed_delivery_date" | "priority" | "order_qty";

export function Orders() {
  const orders = useOrders();
  const { hasRole } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [prioFilter, setPrioFilter] = useState<"all" | "HIGH" | "MED" | "LOW">("all");
  const [sortKey, setSortKey] = useState<SortKey>("committed_delivery_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const toggleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("asc"); }
  };
  const caret = (k: SortKey) => (k === sortKey ? (sortDir === "asc" ? "\u25B2" : "\u25BC") : "\u2195");

  const rows = useMemo(() => {
    let r = orders.data ?? [];
    const q = search.trim().toLowerCase();
    if (q) r = r.filter((o) => o.order_id.toLowerCase().includes(q));
    if (prioFilter !== "all") r = r.filter((o) => (o.priority ?? "").toUpperCase() === prioFilter);
    const prioRank: Record<string, number> = { HIGH: 0, MED: 1, LOW: 2 };
    const sorted = [...r].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "order_id") cmp = a.order_id.localeCompare(b.order_id);
      else if (sortKey === "committed_delivery_date")
        cmp = new Date(a.committed_delivery_date).getTime() - new Date(b.committed_delivery_date).getTime();
      else if (sortKey === "priority")
        cmp = (prioRank[(a.priority ?? "").toUpperCase()] ?? 9) - (prioRank[(b.priority ?? "").toUpperCase()] ?? 9);
      else if (sortKey === "order_qty") cmp = Number(a.order_qty) - Number(b.order_qty);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [orders.data, search, prioFilter, sortKey, sortDir]);

  return (
    <div className="stack">
      <div className="spread">
        <h2>Orders</h2>
        {hasRole("planner") && <button className="primary" onClick={() => setShowCreate(true)}>New order</button>}
      </div>

      <section className="card">
        <div className="hd">
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input type="search" placeholder="Search Order ID..." value={search}
              onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
            <select value={prioFilter} onChange={(e) => setPrioFilter(e.target.value as typeof prioFilter)} style={{ width: 150 }}>
              <option value="all">All priorities</option>
              <option value="HIGH">HIGH only</option>
              <option value="MED">MED only</option>
              <option value="LOW">LOW only</option>
            </select>
          </div>
        </div>
        <div className="bd" style={{ padding: 0 }}>
          {orders.isLoading && <Loading />}
          {orders.isError && <ErrorState message="Couldn't load orders." onRetry={() => orders.refetch()} />}
          {orders.data && orders.data.length === 0 && <div className="state">No orders yet. Create one to begin.</div>}
          {orders.data && orders.data.length > 0 && rows.length === 0 && (
            <div className="state">No orders match your search or filter.</div>
          )}
          {rows.length > 0 && (
            <table className="roomy">
              <thead>
                <tr>
                  <th className="sortable" onClick={() => toggleSort("order_id")}>Order <span className="sort-caret">{caret("order_id")}</span></th>
                  <th className="num">Product #</th><th>Customer</th>
                  <th className="num sortable" onClick={() => toggleSort("order_qty")}>Qty <span className="sort-caret">{caret("order_qty")}</span></th>
                  <th>Order date</th>
                  <th className="sortable" onClick={() => toggleSort("committed_delivery_date")}>Committed <span className="sort-caret">{caret("committed_delivery_date")}</span></th>
                  <th className="sortable" onClick={() => toggleSort("priority")}>Priority <span className="sort-caret">{caret("priority")}</span></th>
                  <th>Mode</th><th className="num">Replans</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id}>
                    <td className="mono">{o.order_id}</td>
                    <td className="num">{o.product_id}</td>
                    <td>{o.customer}</td>
                    <td className="num">{fmtNum(o.order_qty)}</td>
                    <td>{fmtDate(o.order_date)}</td>
                    <td>{fmtDate(o.committed_delivery_date)}</td>
                    <td><PriorityPill priority={o.priority} /></td>
                    <td className="muted">{o.sched_mode}</td>
                    <td className="num">{o.replan_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {showCreate && <CreateOrderModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

interface FormState {
  order_id: string;
  product_id: string;
  customer: string;
  order_qty: string;
  order_date: string;
  committed_delivery_date: string;
  priority: Priority;
  sched_mode: SchedMode;
}

function CreateOrderModal({ onClose }: { onClose: () => void }) {
  const products = useProducts();
  const create = useCreateOrder();
  const [form, setForm] = useState<FormState>({
    order_id: "",
    product_id: "",
    customer: "",
    order_qty: "",
    order_date: new Date().toISOString().slice(0, 10),
    committed_delivery_date: "",
    priority: "MED",
    sched_mode: "backward",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const validate = (): boolean => {
    const e: Partial<Record<keyof FormState, string>> = {};
    if (!form.order_id.trim()) e.order_id = "Required.";
    if (!form.product_id) e.product_id = "Choose a product.";
    if (!form.customer.trim()) e.customer = "Required.";
    const qty = Number(form.order_qty);
    if (!form.order_qty || Number.isNaN(qty) || qty <= 0) e.order_qty = "Must be a positive number.";
    if (!form.committed_delivery_date) e.committed_delivery_date = "Required.";
    else if (form.order_date && form.committed_delivery_date < form.order_date)
      e.committed_delivery_date = "Cannot be before the order date.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    setSubmitError(null);
    if (!validate()) return;
    const payload: OrderCreate = {
      order_id: form.order_id.trim(),
      product_id: Number(form.product_id),
      customer: form.customer.trim(),
      order_qty: Number(form.order_qty),
      order_date: form.order_date,
      committed_delivery_date: form.committed_delivery_date,
      priority: form.priority,
      sched_mode: form.sched_mode,
    };
    try {
      await create.mutateAsync(payload);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setSubmitError(err.message);
      else setSubmitError("Couldn't create the order.");
    }
  };

  const productOptions = useMemo(() => products.data ?? [], [products.data]);

  return (
    <Modal
      title="New order"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={create.isPending}>Cancel</button>
          <button className="primary" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Creating..." : "Create order"}
          </button>
        </>
      }
    >
      {submitError && <div className="banner err">{submitError}</div>}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Field label="Order ID" error={errors.order_id}>
          <input value={form.order_id} onChange={(e) => set("order_id", e.target.value)} placeholder="ORD-5001" />
        </Field>
        <Field label="Customer" error={errors.customer}>
          <input value={form.customer} onChange={(e) => set("customer", e.target.value)} />
        </Field>
        <Field label="Product" error={errors.product_id}>
          <select value={form.product_id} onChange={(e) => set("product_id", e.target.value)}>
            <option value="">{products.isLoading ? "Loading..." : "Select..."}</option>
            {productOptions.map((p) => (
              <option key={p.id} value={p.id}>{p.product_id} - {p.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Quantity" error={errors.order_qty}>
          <input type="number" min={1} value={form.order_qty} onChange={(e) => set("order_qty", e.target.value)} />
        </Field>
        <Field label="Order date">
          <input type="date" value={form.order_date} onChange={(e) => set("order_date", e.target.value)} />
        </Field>
        <Field label="Committed delivery" error={errors.committed_delivery_date}>
          <input type="date" value={form.committed_delivery_date} onChange={(e) => set("committed_delivery_date", e.target.value)} />
        </Field>
        <Field label="Priority">
          <select value={form.priority} onChange={(e) => set("priority", e.target.value as Priority)}>
            <option value="HIGH">HIGH</option><option value="MED">MED</option><option value="LOW">LOW</option>
          </select>
        </Field>
        <Field label="Scheduling mode">
          <select value={form.sched_mode} onChange={(e) => set("sched_mode", e.target.value as SchedMode)}>
            <option value="backward">Backward (from due date)</option>
            <option value="forward">Forward (earliest finish)</option>
          </select>
        </Field>
      </div>
    </Modal>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label>{label}</label>
      {children}
      {error && <div className="field-err">{error}</div>}
    </div>
  );
}
