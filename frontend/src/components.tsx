import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Bot, ArrowUpRight, ListTodo } from "lucide-react";
import { ApiError, safeUrl, formatDate } from "./api";
import type { Stats, Task } from "./types";

export function ErrorBox({ error }: { error: Error }) {
  const location = useLocation();
  if (error instanceof ApiError && [401, 428].includes(error.status))
    return (
      <div className="empty">
        <Bot size={34} />
        <h2>
          {error.status === 428
            ? "Connect your Feishu account"
            : "Sign in to continue"}
        </h2>
        <p>
          Your dashboard stays available. Connect Feishu to manage tasks and
          sync your team.
        </p>
        <a
          className="button primary"
          href={`${error.status === 401 ? "/auth/login" : "/auth/feishu"}?next=${encodeURIComponent(location.pathname)}`}
        >
          Continue <ArrowUpRight size={16} />
        </a>
      </div>
    );
  return (
    <div role="alert" className="notice error">
      {error.message}
    </div>
  );
}
export function Load<T>({
  state,
  children,
}: {
  state: { data?: T; error?: Error };
  children: (data: T) => ReactNode;
}) {
  return state.error ? (
    <ErrorBox error={state.error} />
  ) : state.data === undefined ? (
    <div className="loading" role="status">
      Loading…
    </div>
  ) : (
    children(state.data)
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <ListTodo size={28} />
      <p>{children}</p>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.toLowerCase()}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function LinkOut({ url }: { url: string }) {
  const href = safeUrl(url);
  return href ? (
    <a href={href} target="_blank" rel="noreferrer" aria-label="Open in Feishu">
      <ArrowUpRight size={16} />
    </a>
  ) : null;
}
export function Heading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="heading">
      <div>
        <div className="eyebrow">TEAM WORKSPACE</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function StatsGrid({ stats }: { stats: Stats }) {
  return (
    <div className="stats">
      {[
        ["Pending", stats.pending],
        ["In progress", stats.in_progress],
        ["Completed", stats.completed],
        ["Overdue", stats.overdue],
      ].map(([label, value], i) => (
        <div className={`stat stat-${i}`} key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <div className="stat-line" />
        </div>
      ))}
    </div>
  );
}
export function TaskSummary({ task }: { task: Task }) {
  return (
    <div className="row">
      <div>
        <strong>{task.title}</strong>
        <small>
          {task.owners.map((m) => m.name || m.id).join(", ") || "Unassigned"} ·{" "}
          {formatDate(task.due)}
        </small>
      </div>
      <Badge value={task.priority} />
      <LinkOut url={task.url} />
    </div>
  );
}
