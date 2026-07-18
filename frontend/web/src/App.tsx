import { useState, useEffect } from "react";
import { NavLink, Route, Routes, Navigate, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLiveUpdates } from "./hooks/useLiveUpdates";
import { qk } from "./hooks/queries";
import { useAuth } from "./hooks/useAuth";
import { api, ApiError } from "./api/client";
import { Modal, Pill } from "./components/ui";
import { Login } from "./screens/Login";
import { Dashboard } from "./screens/Dashboard";
import { Orders } from "./screens/Orders";
import { Timeline } from "./screens/Timeline";
import { Capacity } from "./screens/Capacity";
import { Materials } from "./screens/Materials";
import { Reschedule } from "./screens/Reschedule";
import { Events } from "./screens/Events";
import { DelayedOrders } from "./screens/DelayedOrders";
import { Admin } from "./screens/Admin";
import { Alerts } from "./screens/Alerts";
import { ImportExport } from "./screens/ImportExport";
import { SetupReference } from "./screens/SetupReference";
import { Sandbox } from "./screens/Sandbox";

const NAV: Array<{ to: string; label: string }> = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts", label: "Alerts" },
  { to: "/orders", label: "Orders" },
  { to: "/timeline", label: "Timeline" },
  { to: "/capacity", label: "Capacity" },
  { to: "/materials", label: "Materials & BOM" },
  { to: "/reschedule", label: "Reschedule" },
  { to: "/events", label: "Execution events" },
  { to: "/sandbox", label: "What-if sandbox" },
  { to: "/import-export", label: "Import & export" },
  { to: "/setup", label: "Setup & reference" },
];

function LiveBadge() {
  const { status } = useLiveUpdates();
  const tone = status === "live" ? "ok" : status === "connecting" ? "warn" : "muted";
  const label = status === "live" ? "Live" : status === "connecting" ? "Connecting..." : "Offline";
  return <span className={`pill ${tone}`} title="Live update connection">{label}</span>;
}

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="clock" title="Current time">
      <span className="clock-time">
        {now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </span>
      <span className="clock-date">
        {now.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
      </span>
    </div>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem("plantrack_theme") === "dark"; } catch { return false; }
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    try { localStorage.setItem("plantrack_theme", dark ? "dark" : "light"); } catch (e) { void e; }
  }, [dark]);
  return (
    <button className="ghost icon-btn" title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={() => setDark((d) => !d)}>
      {dark ? <span aria-hidden="true">&#9789;</span> : <span aria-hidden="true">&#9728;</span>}
    </button>
  );
}

function NotificationBell() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const alerts = useQuery({ queryKey: qk.openAlerts, queryFn: () => api.alerts(false, "open") });
  const rows = (alerts.data ?? []).slice(0, 8);
  const count = alerts.data?.length ?? 0;

  const openAlert = async (dedupKey: string) => {
    try {
      await api.ackAlert(dedupKey);
    } catch (e) {
      void e; // if ack fails, still let the planner navigate to see it
    }
    qc.invalidateQueries({ queryKey: qk.openAlerts });
    setOpen(false);
    nav("/alerts");
  };

  const toneFor = (t: string) => (t === "crit" ? "risk" : t === "warn" ? "warn" : "info") as
    "risk" | "warn" | "info";

  return (
    <div className="profile-wrap">
      <button className="ghost icon-btn" style={{ position: "relative" }}
        onClick={() => setOpen((o) => !o)} title="Alerts" aria-label="Alerts">
        <span aria-hidden="true">&#128276;</span>
        {count > 0 && (
          <span style={{
            position: "absolute", top: -2, right: -2, background: "var(--risk)", color: "#fff",
            borderRadius: 999, fontSize: 10, fontWeight: 700, minWidth: 16, height: 16,
            display: "flex", alignItems: "center", justifyContent: "center", padding: "0 3px",
          }}>{count > 99 ? "99+" : count}</span>
        )}
      </button>
      {open && (
        <>
          <div className="menu-backdrop" onClick={() => setOpen(false)} />
          <div className="profile-menu" style={{ minWidth: 320, maxWidth: 360 }}>
            <div className="profile-head" style={{ paddingBottom: 6 }}>
              <div className="profile-name">Alerts</div>
              <span className="muted" style={{ fontSize: 12 }}>{count} not viewed</span>
            </div>
            <div className="menu-sep" />
            {rows.length === 0 && (
              <div className="muted" style={{ padding: "10px 10px", fontSize: 13 }}>No open alerts.</div>
            )}
            {rows.map((a) => (
              <button key={a.dedup_key} className="menu-item" style={{ display: "block" }}
                onClick={() => openAlert(a.dedup_key)}>
                <div className="row" style={{ gap: 6, alignItems: "center" }}>
                  <Pill tone={toneFor(a.alert_type)}>{a.alert_type}</Pill>
                  <span style={{ fontSize: 13, flex: 1 }}>{a.title}</span>
                </div>
              </button>
            ))}
            <div className="menu-sep" />
            <button className="menu-item" onClick={() => { setOpen(false); nav("/alerts"); }}>
              View all alerts
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ProfileMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  if (!user) return null;
  const initials = user.username.slice(0, 2).toUpperCase();
  return (
    <div className="profile-wrap">
      <button className="avatar-btn" onClick={() => setOpen((o) => !o)} title="Account">
        <span className="avatar">{initials}</span>
        <span className="avatar-name">{user.username}</span>
        <span className="avatar-caret"></span>
      </button>
      {open && (
        <>
          <div className="menu-backdrop" onClick={() => setOpen(false)} />
          <div className="profile-menu">
            <div className="profile-head">
              <span className="avatar lg">{initials}</span>
              <div>
                <div className="profile-name">{user.username}</div>
                <div className="profile-role"><span className="pill info">{user.role}</span></div>
              </div>
            </div>
            <button className="menu-item" onClick={() => { setShowProfile(true); setOpen(false); }}>Profile & details</button>
            <button className="menu-item" onClick={() => { setShowPw(true); setOpen(false); }}>Change password</button>
            <div className="menu-sep" />
            <button className="menu-item danger" onClick={logout}>Sign out</button>
          </div>
        </>
      )}
      {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}
      {showProfile && <ProfileModal onClose={() => setShowProfile(false)} />}
    </div>
  );
}

function ProfileModal({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  if (!user) return null;
  const initials = user.username.slice(0, 2).toUpperCase();
  return (
    <Modal title="Profile & details" onClose={onClose} footer={<button className="primary" onClick={onClose}>Close</button>}>
      <div className="stack">
        <div className="profile-head">
          <span className="avatar xl">{initials}</span>
          <div>
            <div className="profile-name" style={{ fontSize: 18 }}>{user.username}</div>
            <div className="profile-role"><span className="pill info">{user.role}</span></div>
          </div>
        </div>
        <table>
          <tbody>
            <tr><td className="muted">Username</td><td>{user.username}</td></tr>
            <tr><td className="muted">Role</td><td>{user.role}</td></tr>
            {"full_name" in user && (user as { full_name?: string }).full_name &&
              <tr><td className="muted">Full name</td><td>{(user as { full_name?: string }).full_name}</td></tr>}
          </tbody>
        </table>
        <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
          Profile photo upload is coming soon. For now your initials are shown as your avatar.
        </p>
      </div>
    </Modal>
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
          <button className="primary" onClick={submit} disabled={busy}>{busy ? "Saving..." : "Update password"}</button>
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
            <Clock />
            <LiveBadge />
            <NotificationBell />
            <ThemeToggle />
            <ProfileMenu />
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/capacity" element={<Capacity />} />
            <Route path="/materials" element={<Materials />} />
            <Route path="/reschedule" element={<Reschedule />} />
            <Route path="/delayed" element={<DelayedOrders />} />
            <Route path="/events" element={<Events />} />
            <Route path="/sandbox" element={<Sandbox />} />
            <Route path="/import-export" element={<ImportExport />} />
            <Route path="/setup" element={<SetupReference />} />
            {isAdmin && <Route path="/admin" element={<Admin />} />}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
