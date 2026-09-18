import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ListTodo,
  Clock3,
  Users,
  Bell,
  Settings2,
  Activity,
  RefreshCw,
  LogOut,
  Bot,
  Menu,
} from "lucide-react";
import { api, setCsrf, primeInitialData } from "./api";
import type { Session, Sync } from "./types";
import { ErrorBox, Empty } from "./components";
import { DashboardPage } from "./pages/DashboardPage";
import { TasksPage } from "./pages/TasksPage";
import { TimelinePage } from "./pages/TimelinePage";
import { WorkloadPage } from "./pages/WorkloadPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";

const nav = [
  ["/", "Overview", LayoutDashboard],
  ["/tasks", "Tasks", ListTodo],
  ["/timeline", "Timeline", Clock3],
  ["/workload", "Workload", Users],
  ["/notifications", "Notifications", Bell],
  ["/settings", "Settings", Settings2],
  ["/diagnostics", "Diagnostics", Activity],
] as const;
export default function App() {
  const [revision, setRevision] = useState(0);
  const [session, setSession] = useState<Session>();
  const [error, setError] = useState<Error>();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const loadSession = useCallback(() => {
    api<{ session: Session; data: Parameters<typeof primeInitialData>[0] }>(
      `/bootstrap?page=${encodeURIComponent(window.location.pathname)}`,
    )
      .then(({ session: s, data }) => {
        primeInitialData(data);
        setCsrf(s.csrf_token);
        setSession(s);
      })
      .catch(setError);
  }, []);
  useEffect(loadSession, [loadSession]);
  useEffect(() => {
    setMenu(false);
    setMessage("");
    setError(undefined);
  }, [location.pathname]);
  async function mutate(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError(undefined);
    setMessage("");
    try {
      const result = await api<Partial<Sync>>(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      setRevision((r) => r + 1);
      setMessage(
        result.warnings?.length ? result.warnings.join(" ") : "Changes saved.",
      );
      return true;
    } catch (e) {
      setError(e as Error);
      return false;
    } finally {
      setBusy(false);
    }
  }
  if (!session)
    return (
      <main className="startup">
        {error ? (
          <>
            <ErrorBox error={error} />
            <button onClick={loadSession}>Retry</button>
          </>
        ) : (
          <div className="loading">Opening your workspace…</div>
        )}
      </main>
    );
  const props = { session, revision, mutate, busy };
  const admin = session.user?.role === "admin";
  return (
    <div className="app">
      <aside className={menu ? "sidebar open" : "sidebar"}>
        <NavLink className="brand" to="/">
          <span className="brand-icon">
            <Bot size={24} />
          </span>
          <div>
            RM Hub<small>RESEARCH WORKSPACE</small>
          </div>
        </NavLink>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav
            .filter(
              ([p]) => admin || !["/settings", "/diagnostics"].includes(p),
            )
            .map(([path, label, Icon]) => (
              <NavLink end={path === "/"} to={path} key={path}>
                <Icon size={18} />
                {label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" />
          {session.mode === "mock"
            ? "Local workspace"
            : "Feishu connected workspace"}
          <small>{session.team_name}</small>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Toggle navigation"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={22} />
          </button>
          <span className="workspace-label">
            RoboMaster <span>/</span> Research
          </span>
          <div className="topbar-actions">
            {admin && (
              <>
                <button
                  disabled={busy}
                  onClick={() => void mutate("/members/refresh")}
                >
                  <Users size={15} />
                  Members
                </button>
                <button disabled={busy} onClick={() => void mutate("/sync")}>
                  <RefreshCw className={busy ? "spin" : ""} size={15} />
                  Sync
                </button>
              </>
            )}
            {!session.connected && (
              <a
                className="button primary"
                href={`/auth/feishu?next=${encodeURIComponent(location.pathname)}`}
              >
                {session.mode === "mock" ? "Demo login" : "Connect Feishu"}
              </a>
            )}
            {session.user && (
              <>
                <span className="user-name">{session.user.name}</span>
                <button
                  className="icon-button"
                  aria-label="Sign out"
                  onClick={async () => {
                    if (await mutate("/logout"))
                      window.location.href = session.oidc ? "/oidc/login" : "/";
                  }}
                >
                  <LogOut size={16} />
                </button>
              </>
            )}
          </div>
        </header>
        <main>
          {session.mode === "mock" && (
            <div className="demo-banner">
              Local demo · Task changes stay in this workspace.
            </div>
          )}
          {error && <ErrorBox error={error} />}{" "}
          {!!message && (
            <div className="notice" role="status">
              {message}
            </div>
          )}
          <Routes>
            <Route path="/" element={<DashboardPage revision={revision} />} />
            <Route path="/tasks" element={<TasksPage {...props} />} />
            <Route
              path="/timeline"
              element={<TimelinePage revision={revision} />}
            />
            <Route
              path="/workload"
              element={<WorkloadPage revision={revision} />}
            />
            <Route
              path="/notifications"
              element={<NotificationsPage revision={revision} />}
            />
            <Route path="/settings" element={<SettingsPage {...props} />} />
            <Route
              path="/diagnostics"
              element={<DiagnosticsPage revision={revision} />}
            />
            <Route
              path="*"
              element={
                <Empty>
                  Page not found. <NavLink to="/">Return to overview</NavLink>
                </Empty>
              }
            />
          </Routes>
          <footer>RM Hub · Built for the work behind the robot.</footer>
        </main>
      </div>
    </div>
  );
}
