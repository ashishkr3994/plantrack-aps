import { useState } from "react";
import {
  useRoutings, useCreateRouting, useDeleteRouting,
  useAddOperation, useUpdateOperation, useDeleteOperation,
} from "@/hooks/queries";
import { Loading, ErrorState, Empty, Pill, Modal } from "@/components/ui";
import { ApiError } from "@/api/client";
import type { Routing, RoutingOp } from "@/api/types";
import { useAuth } from "@/hooks/useAuth";

export function Configuration() {
  const routings = useRoutings();
  const { hasRole } = useAuth();
  const canEdit = hasRole("planner");
  const [creatingRouting, setCreatingRouting] = useState(false);

  return (
    <div className="stack">
      <div className="spread">
        <div />
        {canEdit && <button className="primary" onClick={() => setCreatingRouting(true)}>New routing</button>}
      </div>

      <section className="card">
        <div className="hd">Routings & operations</div>
        <div className="bd stack">
          {routings.isLoading && <Loading />}
          {routings.isError && <ErrorState message="Couldn't load routings." onRetry={() => routings.refetch()} />}
          {routings.data && routings.data.length === 0 && (
            <Empty
              message="No routings yet."
              action={<button className="primary" onClick={() => setCreatingRouting(true)}>Create the first routing</button>}
            />
          )}
          {routings.data?.map((r) => <RoutingCard key={r.id} routing={r} />)}
        </div>
      </section>

      {creatingRouting && <RoutingModal onClose={() => setCreatingRouting(false)} />}
    </div>
  );
}

function RoutingCard({ routing }: { routing: Routing }) {
  const delRouting = useDeleteRouting();
  const delOp = useDeleteOperation();
  const [addingOp, setAddingOp] = useState(false);
  const [editingOp, setEditingOp] = useState<RoutingOp | null>(null);
  const [confirmDeleteRouting, setConfirmDeleteRouting] = useState(false);
  const [confirmDeleteOp, setConfirmDeleteOp] = useState<RoutingOp | null>(null);

  return (
    <div className="card">
      <div className="hd">
        <span className="row" style={{ gap: 10 }}>
          <span className="mono">{routing.route_id}</span>
          <span className="muted" style={{ fontWeight: 400 }}>{routing.description}</span>
        </span>
        <span className="row" style={{ gap: 6 }}>
          <button className="ghost" onClick={() => setAddingOp(true)}>Add operation</button>
          <button className="ghost danger" onClick={() => setConfirmDeleteRouting(true)}>Delete routing</button>
        </span>
      </div>
      <div className="bd" style={{ padding: 0 }}>
        {routing.operations.length === 0 ? (
          <div className="state">No operations. Add the first step.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="num">Seq</th><th>Work center</th><th className="num">Setup</th>
                <th className="num">Run/unit</th><th className="num">Queue</th><th className="num">Move</th>
                <th className="num">Pred</th><th>Group</th><th style={{ width: 130 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {routing.operations.map((op) => (
                <tr key={op.id}>
                  <td className="num mono">{op.operation_seq}</td>
                  <td>{op.work_center}</td>
                  <td className="num">{op.setup_min ?? 0}</td>
                  <td className="num">{op.run_per_unit_min ?? 0}</td>
                  <td className="num">{op.queue_min ?? 0}</td>
                  <td className="num">{op.move_min ?? 0}</td>
                  <td className="num">{op.predecessor_seq ?? "-"}</td>
                  <td>{op.parallel_group ? <Pill tone="info">{op.parallel_group}</Pill> : "-"}</td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <button className="ghost" onClick={() => setEditingOp(op)}>Edit</button>
                      <button className="ghost danger" onClick={() => setConfirmDeleteOp(op)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {addingOp && <OperationModal routingPk={routing.id} onClose={() => setAddingOp(false)} />}
      {editingOp && <OperationModal routingPk={routing.id} existing={editingOp} onClose={() => setEditingOp(null)} />}

      {confirmDeleteRouting && (
        <Modal
          title="Delete routing"
          onClose={() => setConfirmDeleteRouting(false)}
          footer={
            <>
              <button onClick={() => setConfirmDeleteRouting(false)} disabled={delRouting.isPending}>Cancel</button>
              <button className="primary danger" disabled={delRouting.isPending}
                onClick={async () => { await delRouting.mutateAsync(routing.id); setConfirmDeleteRouting(false); }}>
                {delRouting.isPending ? "Deleting" : "Delete routing"}
              </button>
            </>
          }
        >
          <p>Delete routing <strong>{routing.route_id}</strong> and all {routing.operations.length} of its operations? Products using it will lose their routing link.</p>
        </Modal>
      )}

      {confirmDeleteOp && (
        <Modal
          title="Delete operation"
          onClose={() => setConfirmDeleteOp(null)}
          footer={
            <>
              <button onClick={() => setConfirmDeleteOp(null)} disabled={delOp.isPending}>Cancel</button>
              <button className="primary danger" disabled={delOp.isPending}
                onClick={async () => { await delOp.mutateAsync({ routingPk: routing.id, opPk: confirmDeleteOp.id }); setConfirmDeleteOp(null); }}>
                {delOp.isPending ? "Deleting" : "Delete"}
              </button>
            </>
          }
        >
          <p>Remove operation <strong>{confirmDeleteOp.operation_seq}</strong> ({confirmDeleteOp.work_center}) from this routing?</p>
        </Modal>
      )}
    </div>
  );
}

function RoutingModal({ onClose }: { onClose: () => void }) {
  const create = useCreateRouting();
  const [routeId, setRouteId] = useState("");
  const [desc, setDesc] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [fieldErr, setFieldErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (!routeId.trim()) { setFieldErr("Required."); return; }
    try {
      await create.mutateAsync({ route_id: routeId.trim(), description: desc.trim() || null });
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't create the routing.");
    }
  };

  return (
    <Modal
      title="New routing"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={create.isPending}>Cancel</button>
          <button className="primary" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Creating" : "Create routing"}
          </button>
        </>
      }
    >
      {err && <div className="banner err">{err}</div>}
      <div>
        <label>Route ID</label>
        <input value={routeId} onChange={(e) => { setRouteId(e.target.value); setFieldErr(null); }} placeholder="R-STD-03" />
        {fieldErr && <div className="field-err">{fieldErr}</div>}
      </div>
      <div>
        <label>Description</label>
        <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="optional" />
      </div>
    </Modal>
  );
}

interface OpForm {
  operation_seq: string;
  work_center: string;
  setup_min: string;
  run_per_unit_min: string;
  queue_min: string;
  move_min: string;
  predecessor_seq: string;
  parallel_group: string;
}

function OperationModal({
  routingPk, existing, onClose,
}: { routingPk: number; existing?: RoutingOp; onClose: () => void }) {
  const isEdit = !!existing;
  const add = useAddOperation();
  const update = useUpdateOperation();
  const busy = add.isPending || update.isPending;

  const [form, setForm] = useState<OpForm>({
    operation_seq: existing ? String(existing.operation_seq) : "",
    work_center: existing?.work_center ?? "",
    setup_min: existing ? String(existing.setup_min ?? 0) : "0",
    run_per_unit_min: existing ? String(existing.run_per_unit_min ?? 0) : "0",
    queue_min: existing ? String(existing.queue_min ?? 0) : "0",
    move_min: existing ? String(existing.move_min ?? 0) : "0",
    predecessor_seq: existing?.predecessor_seq != null ? String(existing.predecessor_seq) : "",
    parallel_group: existing?.parallel_group ?? "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof OpForm, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const set = <K extends keyof OpForm>(k: K, v: OpForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  const validate = () => {
    const e: Partial<Record<keyof OpForm, string>> = {};
    const seq = Number(form.operation_seq);
    if (form.operation_seq === "" || Number.isNaN(seq) || seq < 0) e.operation_seq = "Must be 0 or more.";
    if (!form.work_center.trim()) e.work_center = "Required.";
    for (const k of ["setup_min", "run_per_unit_min", "queue_min", "move_min"] as const) {
      const n = Number(form[k]);
      if (form[k] === "" || Number.isNaN(n) || n < 0) e[k] = "Must be 0 or more.";
    }
    if (form.predecessor_seq !== "" && (Number.isNaN(Number(form.predecessor_seq)) || Number(form.predecessor_seq) < 0))
      e.predecessor_seq = "Must be a sequence number.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    setSubmitError(null);
    if (!validate()) return;
    const payload = {
      operation_seq: Number(form.operation_seq),
      work_center: form.work_center.trim(),
      setup_min: Number(form.setup_min),
      run_per_unit_min: Number(form.run_per_unit_min),
      queue_min: Number(form.queue_min),
      move_min: Number(form.move_min),
      predecessor_seq: form.predecessor_seq === "" ? null : Number(form.predecessor_seq),
      parallel_group: form.parallel_group.trim() || null,
    };
    try {
      if (isEdit && existing) {
        await update.mutateAsync({ routingPk, opPk: existing.id, patch: payload });
      } else {
        await add.mutateAsync({ routingPk, op: payload });
      }
      onClose();
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : "Couldn't save the operation.");
    }
  };

  return (
    <Modal
      title={isEdit ? "Edit operation" : "Add operation"}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={busy}>
            {busy ? "Saving" : isEdit ? "Save changes" : "Add operation"}
          </button>
        </>
      }
    >
      {submitError && <div className="banner err">{submitError}</div>}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <OpField label="Sequence" error={errors.operation_seq}>
          <input type="number" min={0} value={form.operation_seq} onChange={(e) => set("operation_seq", e.target.value)} placeholder="10" />
        </OpField>
        <OpField label="Work center" error={errors.work_center}>
          <input value={form.work_center} onChange={(e) => set("work_center", e.target.value)} placeholder="Machining" />
        </OpField>
        <OpField label="Setup (min)" error={errors.setup_min}>
          <input type="number" min={0} step="any" value={form.setup_min} onChange={(e) => set("setup_min", e.target.value)} />
        </OpField>
        <OpField label="Run per unit (min)" error={errors.run_per_unit_min}>
          <input type="number" min={0} step="any" value={form.run_per_unit_min} onChange={(e) => set("run_per_unit_min", e.target.value)} />
        </OpField>
        <OpField label="Queue (min)" error={errors.queue_min}>
          <input type="number" min={0} step="any" value={form.queue_min} onChange={(e) => set("queue_min", e.target.value)} />
        </OpField>
        <OpField label="Move (min)" error={errors.move_min}>
          <input type="number" min={0} step="any" value={form.move_min} onChange={(e) => set("move_min", e.target.value)} />
        </OpField>
        <OpField label="Predecessor seq" error={errors.predecessor_seq}>
          <input type="number" min={0} value={form.predecessor_seq} onChange={(e) => set("predecessor_seq", e.target.value)} placeholder="none" />
        </OpField>
        <OpField label="Parallel group">
          <input value={form.parallel_group} onChange={(e) => set("parallel_group", e.target.value)} placeholder="e.g. G1 (optional)" />
        </OpField>
      </div>
    </Modal>
  );
}

function OpField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label>{label}</label>
      {children}
      {error && <div className="field-err">{error}</div>}
    </div>
  );
}
