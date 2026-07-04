import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/api/client";

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't sign in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", placeItems: "center", height: "100vh", background: "var(--canvas)" }}>
      <div className="card" style={{ width: 360 }}>
        <div className="bd stack">
          <div style={{ textAlign: "center", marginBottom: 4 }}>
            <div style={{ fontWeight: 750, fontSize: 24, color: "var(--teal)", letterSpacing: "-0.02em" }}>PlanTrack</div>
            <div className="muted" style={{ fontSize: 13 }}>APS Control Tower</div>
          </div>
          {error && <div className="banner err">{error}</div>}
          <div>
            <label>Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              autoFocus
            />
          </div>
          <div>
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
          </div>
          <button className="primary" onClick={submit} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {import.meta.env.DEV && (
            <p className="muted" style={{ fontSize: 12, margin: 0, textAlign: "center" }}>
              Dev only: admin / admin123 · planner / planner123 · viewer / viewer123
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

