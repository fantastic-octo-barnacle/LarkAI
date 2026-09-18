import { useState } from "react";
import { Plus, Search, Clock3, Users, Check, X, Trash2 } from "lucide-react";
import type { Task, Member, PageProps } from "../types";
import { useData } from "../useData";
import { formatDate } from "../api";
import { Heading, Load, Empty, Badge, LinkOut } from "../components";
import { TaskForm } from "./TaskForm";

export function TasksPage({ session, revision, mutate, busy }: PageProps) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [group, setGroup] = useState("status");
  const [creating, setCreating] = useState(false);
  const state = useData<Task[]>(
    `/tasks?${new URLSearchParams({ q, status })}`,
    revision,
  );
  const members = useData<Member[]>("/members", revision);
  const options = useData<{ categories: string[]; divisions: string[] }>(
    "/task-options",
    revision,
  );
  const [confirm, setConfirm] = useState<string>();
  return (
    <>
      <Heading
        title="Task board"
        description="Turn team priorities into progress."
      >
        <button className="primary" onClick={() => setCreating(!creating)}>
          <Plus size={17} />
          {creating ? "Close form" : "New task"}
        </button>
      </Heading>
      <Load state={state}>
        {(tasks) => {
          const groups: Record<string, Task[]> = {};
          tasks.forEach((t) => {
            const key =
              group === "division"
                ? t.divisions.join(" · ") || "Unassigned division"
                : group === "source"
                  ? t.source
                  : group === "none"
                    ? "All tasks"
                    : t.status;
            (groups[key] ??= []).push(t);
          });
          return (
            <>
              {creating && (
                <section className="panel">
                  <Load state={members}>
                    {(m) => (
                      <Load state={options}>
                        {(o) => (
                          <TaskForm
                            members={m}
                            options={o}
                            busy={busy}
                            submit={(body) => mutate("/tasks", body)}
                          />
                        )}
                      </Load>
                    )}
                  </Load>
                </section>
              )}
              <div className="toolbar">
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label="Search tasks"
                    placeholder="Search tasks…"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                </div>
                <select
                  aria-label="Filter status"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option value="">All statuses</option>
                  {[
                    "pending",
                    "in_progress",
                    "completed",
                    "cancelled",
                    "paused",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
                <select
                  aria-label="Group tasks"
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                >
                  {["status", "division", "source", "none"].map((s) => (
                    <option key={s} value={s}>
                      Group: {s}
                    </option>
                  ))}
                </select>
              </div>
              {!tasks.length && (
                <Empty>
                  No tasks match. Create a task or sync Feishu to get started.
                </Empty>
              )}
              <div className="task-groups">
                {Object.entries(groups).map(([label, items]) => (
                  <section className="task-group" key={label}>
                    <h2>
                      {label.replaceAll("_", " ")}{" "}
                      <span className="count">{items.length}</span>
                    </h2>
                    {items.map((t) => (
                      <article className="task-card" key={t.id}>
                        <div className="card-meta">
                          <Badge value={t.source} />
                          <Badge value={t.priority} />
                          <LinkOut url={t.url} />
                        </div>
                        <h3>{t.title}</h3>
                        <p>{t.description}</p>
                        <div className="task-info">
                          <span>
                            <Clock3 size={14} />
                            {formatDate(t.due)}
                          </span>
                          <span>
                            <Users size={14} />
                            {t.owners.map((m) => m.name || m.id).join(", ") ||
                              "Unassigned"}
                          </span>
                          {!!t.divisions.length && (
                            <span>{t.divisions.join(" · ")}</span>
                          )}
                        </div>
                        <div className="card-actions">
                          {["pending", "in_progress", "paused"].includes(
                            t.status,
                          ) && (
                            <>
                              <button
                                disabled={busy}
                                onClick={() =>
                                  void mutate(
                                    `/tasks/${encodeURIComponent(t.id)}/complete`,
                                  )
                                }
                              >
                                <Check size={14} />
                                Complete
                              </button>
                              <button
                                disabled={busy}
                                onClick={() =>
                                  void mutate(
                                    `/tasks/${encodeURIComponent(t.id)}/cancel`,
                                  )
                                }
                              >
                                <X size={14} />
                                Cancel
                              </button>
                            </>
                          )}
                          {session.user?.role === "admin" &&
                            (confirm === t.id ? (
                              <>
                                <button
                                  className="danger"
                                  disabled={busy}
                                  onClick={async () => {
                                    if (
                                      await mutate(
                                        `/tasks/${encodeURIComponent(t.id)}/delete`,
                                      )
                                    )
                                      setConfirm(undefined);
                                  }}
                                >
                                  Confirm delete
                                </button>
                                <button onClick={() => setConfirm(undefined)}>
                                  Keep
                                </button>
                              </>
                            ) : (
                              <button
                                className="icon-button"
                                aria-label={`Delete ${t.title}`}
                                onClick={() => setConfirm(t.id)}
                              >
                                <Trash2 size={14} />
                              </button>
                            ))}
                        </div>
                      </article>
                    ))}
                  </section>
                ))}
              </div>
            </>
          );
        }}
      </Load>
    </>
  );
}
