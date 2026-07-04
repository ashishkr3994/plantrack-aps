import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { Loading, ErrorState, Pill, Modal } from "@/components/ui";

export function Admin() {
  return (
    <div className="stack">
      <h2>Administration</h2>
      <Users />
      <AuditTrail />
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const [creating, setCreating] = useState(false);

  const create = useMutation({
    mutationFn: (u: { username: string; password: string; full_name?: string; role: string }) => api.createUser(u),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setCreating(false); },
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: { role?: string; is_active?: boolean } }) => api.updateUser(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e) => alert(e instanceof ApiError ? e.message : "Couldn't update user."),
  });

  const ROLES = ["viewer", "procurement", "supervisor", "planner", "admin"];

  return (
    <section className="card">
      <div className="hd">
        Users
        <button className="primary" onClick={() => setCreating(true)}>Add user</button>
      </div>
      <div className="bd" style={{ padding: 0 }}>
        {users.isLoading && <Loading />}
        {users.isError && <ErrorState message="Couldn't load users." onRetry={() => users.refetch()} />}
        {users.data && (
          <table>
            <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th style={{ width: 120 }}>Actions</th></tr></thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.username}</td>
                  <td>{u.full_name ?? "—"}</td>
                  <td style={{ width: 150 }}>
                    <select
                      value={u.role}
                      disabled={update.isPending}
                      onChange={(e) => update.mutate({ id: u.id, patch: { role: e.target.value } })}
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td>{u.is_active ? <Pill tone="ok">active</Pill> : <Pill tone="muted">inactive</Pill>}</td>
                  <td>
                    <button className="ghost" disabled={update.isPending}
                      onClick={() => update.mutate({ id: u.id, patch: { is_active: !u.is_active } })}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {creating && <CreateUserModal onClose={() => setCreating(false)} onSubmit={(u) => create.mutate(u)} busy={create.isPending} error={create.error} />}
    </section>
  );
}

function CreateUserModal({
  onClose, onSubmit, busy, error,
}: {
  onClose: () => void;
  onSubmit: (u: { username: string; password: string; full_name?: string; role: string }) => void;
  busy: boolean;
  error: unknown;
}) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [err, setErr] = useState<string | null>(null);

  const submit = () => {
    setErr(null);
    if (!username.trim()) return setErr("Username required.");
    if (password.length < 6) return setErr("Password must be at least 6 characters.");
    onSubmit({ username: username.trim(), password, full_name: fullName.trim() || undefined, role });
  };

  const apiErr = error instanceof ApiError ? error.message : null;

  return (
    <Modal
      title="Add user"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={busy}>{busy ? "Creating…" : "Create user"}</button>
        </>
      }
    >
      {(err || apiErr) && <div className="banner err">{err ?? apiErr}</div>}
      <div><label>Username</label><input value={username} onChange={(e) => setUsername(e.target.value)} /></div>
      <div><label>Full name</label><input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="optional" /></div>
      <div><label>Password</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
      <div>
        <label>Role</label>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="viewer">viewer (read-only)</option>
          <option value="procurement">procurement</option>
          <option value="supervisor">supervisor</option>
          <option value="planner">planner (edit + solve)</option>
          <option value="admin">admin (full access)</option>
        </select>
      </div>
    </Modal>
  );
}

function AuditTrail() {
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => api.auditTrail(100) });
  const fmt = (s: string | null) => (s ? new Date(s).toLocaleString() : "—");

  return (
    <section className="card">
      <div className="hd">Audit trail</div>
      <div className="bd" style={{ padding: 0 }}>
        {audit.isLoading && <Loading />}
        {audit.isError && <ErrorState message="Couldn't load the audit trail." onRetry={() => audit.refetch()} />}
        {audit.data && audit.data.length === 0 && <div className="state">No activity recorded yet.</div>}
        {audit.data && audit.data.length > 0 && (
          <table>
            <thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th><th>ID</th></tr></thead>
            <tbody>
              {audit.data.map((a) => (
                <tr key={a.id}>
                  <td>{fmt(a.at)}</td>
                  <td className="mono">{a.actor_username ?? "—"}</td>
                  <td>{a.action}</td>
                  <td>{a.entity_type}</td>
                  <td className="mono">{a.entity_id ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}