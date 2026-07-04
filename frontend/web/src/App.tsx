import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { useLiveUpdates } from "./hooks/useLiveUpdates";
import { useAuth } from "./hooks/useAuth";
import { api, ApiError } from "./api/client";
import { Modal } from "./components/ui";
import { Login } from "./screens/Login";
import { Dashboard } from "./screens/Dashboard";
import { Orders } from "./screens/Orders";
import { Schedule } from "./screens/Schedule";
import { Capacity } from "./screens/Capacity";
import { Materials } from "./screens/Materials";
import { Reschedule } from "./screens/Reschedule";
import { Analytics } from "./screens/Analytics";
import { Configuration } from "./screens/Configuration";
import { Admin } from "./screens/Admin";
import { Alerts } from "./screens/Alerts";
import { ImportData } from "./screens/ImportData";
import { Sandbox } from "./screens/Sandbox";

const NAV: Array<{ to: string; label: string }> = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts", label: "Alerts" },
  { to: "/orders", label: "Orders" },
  { to: "/schedule", label: "Schedule" },
  { to: "/capacity", label: "Capacity" },
  { to: "/materials", label: "Materials & BOM" },
  { to: "/reschedule", label: "Reschedule" },
  { to: "/analytics", label: "Analytics" },
  { to: "/sandbox", label: "What-if sandbox" },
  { to: "/import", label: "Import data" },
  { to: "/configuration", label: "Configuration" },
];

function LiveBadge() {
  const { status } = useLiveUpdates();
  const tone = status === "live" ? "ok" : status === "connecting" ? "warn" : "muted";
  const label = status === "live" ? "Live" : status === "connecting" ? "Connecting…" : "Offline";
  return <span className={`pill ${tone}`} title="Live update connection">{label}</span>;
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [showPw, setShowPw] = useState(false);
  if (!user) return null;
  return (
    <div className="row" style={{ gap: 10 }}>
      <span className="pill info" title="Your role">{user.role}</span>
      <span className="muted" style={{ fontSize: 13 }}>{user.username}</span>
      <button className="ghost" onClick={() => setShowPw(true)}>Change password</button>
      <button className="ghost" onClick={logout}>Sign out</button>
      {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}
    </div>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr(null);
    if (next.length < 6) { setErr("New password must be at least 6 characters."); return; }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setDone(true);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't change password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Change password" onClose={onClose} footer={
      done ? <button className="primary" onClick={onClose}>Done</button> : (
        <>
          <button onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={busy}>{busy ? "Saving…" : "Update password"}</button>
        </>
      )
    }>
      {done ? (
        <div className="banner ok">Password updated. Other sessions have been signed out.</div>
      ) : (
        <>
          {err && <div className="banner err">{err}</div>}
          <div><label>Current password</label><input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
          <div><label>New password</label><input type="password" value={next} onChange={(e) => setNext(e.target.value)} /></div>
        </>
      )}
    </Modal>
  );
}

export function App() {
  const { user, loading, hasRole } = useAuth();

  if (loading) {
    return <div className="state" style={{ height: "100vh", display: "grid", placeItems: "center" }}><span className="spinner" /></div>;
  }
  if (!user) return <Login />;

  const isAdmin = hasRole("admin");

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          PlanTrack
          <small>APS Control Tower</small>
        </div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            {n.label}
          </NavLink>
        ))}
        {isAdmin && (
          <NavLink to="/admin" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            Administration
          </NavLink>
        )}
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>Production Control Tower</h1>
          <div className="row" style={{ gap: 14 }}>
            <LiveBadge />
            <UserMenu />
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/capacity" element={<Capacity />} />
            <Route path="/materials" element={<Materials />} />
            <Route path="/reschedule" element={<Reschedule />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/configuration" element={<Configuration />} />
            <Route path="/sandbox" element={<Sandbox />} />
            <Route path="/import" element={<ImportData />} />
            {isAdmin && <Route path="/admin" element={<Admin />} />}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}