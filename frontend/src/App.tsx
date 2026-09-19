import { PreferenceControls, usePreferences } from "./preferences";
import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ListTodo,
  Users,
  Settings2,
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
  ["/", "My Tasks", ListTodo],
  ["/tasks", "Team tasks", Users],
  ["/overview", "Team overview", LayoutDashboard],
  ["/settings", "Administration", Settings2],
] as const;
export default function App() {
  const { t } = usePreferences();
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
        result.warnings?.length
          ? result.warnings.join(" ")
          : path === "/tasks"
            ? "Task created. Find it in Team tasks or the assignee’s My Tasks."
            : "Changes saved.",
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
        <PreferenceControls />
        {error ? (
          <>
            <ErrorBox error={error} />
            <button onClick={loadSession}>{t("Retry")}</button>
          </>
        ) : (
          <div className="loading">{t("Opening your workspace…")}</div>
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
            RM Hub<small>{t("RESEARCH WORKSPACE")}</small>
          </div>
        </NavLink>
        <div className="nav-label">{t("WORKSPACE")}</div>
        <nav>
          {nav
            .filter(
              ([p]) => admin || !["/settings", "/diagnostics"].includes(p),
            )
            .map(([path, label, Icon]) => (
              <NavLink end={path === "/"} to={path} key={path}>
                <Icon size={18} />
                {t(label)}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" />
          {session.mode === "mock"
            ? t("Local workspace")
            : t("Feishu connected workspace")}
          <small>{session.team_name}</small>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label={t("Toggle navigation")}
            onClick={() => setMenu(!menu)}
          >
            <Menu size={22} />
          </button>
          <span className="workspace-label">
            RoboMaster <span>/</span> {t("Research")}
          </span>
          <div className="topbar-actions">
            <PreferenceControls />
            {!session.connected && (
              <a
                className="button primary"
                href={`/auth/feishu?next=${encodeURIComponent(location.pathname)}`}
              >
                {session.mode === "mock"
                  ? t("Demo login")
                  : t("Connect Feishu")}
              </a>
            )}
            {session.user && (
              <>
                <span className="user-name">{session.user.name}</span>
                <button
                  className="icon-button"
                  aria-label={t("Sign out")}
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
              {t("Local demo · Task changes stay in this workspace.")}
            </div>
          )}
          {error && <ErrorBox error={error} />}{" "}
          {!!message && (
            <div className="notice" role="status">
              {t(message)}
            </div>
          )}
          <Routes>
            <Route
              path="/"
              element={<TasksPage key="mine" {...props} personal />}
            />
            <Route
              path="/overview"
              element={<DashboardPage revision={revision} />}
            />
            <Route
              path="/tasks"
              element={<TasksPage key="team" {...props} />}
            />
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
                  {t("Page not found.")}{" "}
                  <NavLink to="/">{t("Return to overview")}</NavLink>
                </Empty>
              }
            />
          </Routes>
          <footer>{t("RM Hub · Built for the work behind the robot.")}</footer>
        </main>
      </div>
    </div>
  );
}
