import { usePreferences } from "../preferences";
import { useState } from "react";
import { Plus, Search, Clock3, Users, Check, X, Trash2 } from "lucide-react";
import type { Task, Member, PageProps } from "../types";
import { useData } from "../useData";
import { formatDate } from "../api";
import { Heading, Load, Empty, Badge, LinkOut } from "../components";
import { TaskGraph } from "./TaskGraph";
import { graphIndex, isBlocked } from "../taskGraph";
import { TaskForm } from "./TaskForm";

export function TasksPage({ session, revision, mutate, busy }: PageProps) {
  const { t: translate, locale } = usePreferences();
  const [view, setView] = useState("board");
  const [selected, setSelected] = useState<string>();
  const [division, setDivision] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [group, setGroup] = useState("status");
  const [creating, setCreating] = useState(false);
  const state = useData<Task[]>("/tasks?q=&status=", revision, true);
  const members = useData<Member[]>(
    creating ? "/members" : undefined,
    revision,
  );
  const options = useData<{ categories: string[]; divisions: string[] }>(
    creating ? "/task-options" : undefined,
    revision,
  );
  const [confirm, setConfirm] = useState<string>();
  return (
    <>
      <Heading
        title={translate("Task board")}
        description={translate("Turn team priorities into progress.")}
      >
        <button className="primary" onClick={() => setCreating(!creating)}>
          <Plus size={17} />
          {creating ? translate("Close form") : translate("New task")}
        </button>
      </Heading>
      <Load state={state}>
        {(allTasks) => {
          const tasks = allTasks.filter(
            (task) =>
              (!status || task.status === status) &&
              (!division || task.divisions.includes(division)) &&
              `${task.title} ${task.description}`
                .toLowerCase()
                .includes(q.toLowerCase()),
          );
          const index = graphIndex(allTasks);
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
              <div
                className="task-view-switch"
                aria-label={translate("Task view")}
              >
                <button
                  aria-pressed={view === "board"}
                  onClick={() => setView("board")}
                >
                  {translate("Board")}
                </button>
                <button
                  aria-pressed={view === "graph"}
                  onClick={() => setView("graph")}
                >
                  {translate("Graph")}
                </button>
              </div>
              <div className="toolbar">
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label={translate("Search tasks")}
                    placeholder={translate("Search tasks…")}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                </div>
                <select
                  aria-label={translate("Filter status")}
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option value="">{translate("All statuses")}</option>
                  {[
                    "pending",
                    "in_progress",
                    "completed",
                    "cancelled",
                    "paused",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {translate(s)}
                    </option>
                  ))}
                </select>
                <select
                  aria-label={translate("Filter team")}
                  value={division}
                  onChange={(e) => setDivision(e.target.value)}
                >
                  <option value="">{translate("All teams")}</option>
                  {[...new Set(allTasks.flatMap((task) => task.divisions))]
                    .sort()
                    .map((name) => (
                      <option key={name}>{name}</option>
                    ))}
                </select>
                {view === "board" && (
                  <select
                    aria-label={translate("Group tasks")}
                    value={group}
                    onChange={(e) => setGroup(e.target.value)}
                  >
                    {["status", "division", "source", "none"].map((s) => (
                      <option key={s} value={s}>
                        {translate("Group:")} {translate(s)}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              {!tasks.length && (
                <Empty>
                  {translate(
                    "No tasks match. Create a task or sync Feishu to get started.",
                  )}
                </Empty>
              )}
              {view === "graph" ? (
                <TaskGraph
                  tasks={allTasks}
                  visibleTasks={tasks}
                  selected={selected}
                  select={setSelected}
                  busy={busy}
                  mutate={mutate}
                />
              ) : (
                <div className="task-groups">
                  {Object.entries(groups).map(([label, items]) => (
                    <section className="task-group" key={label}>
                      <h2>
                        {translate(label) === label
                          ? label.replaceAll("_", " ")
                          : translate(label)}{" "}
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
                          {isBlocked(t, index.byId) && (
                            <span className="blocked-label">
                              {translate("Blocked")}
                            </span>
                          )}
                          <p>{t.description}</p>
                          <div className="task-info">
                            <span>
                              <Clock3 size={14} />
                              {formatDate(t.due, locale)}
                            </span>
                            <span>
                              <Users size={14} />
                              {t.owners.map((m) => m.name || m.id).join(", ") ||
                                translate("Unassigned")}
                            </span>
                            {!!t.divisions.length && (
                              <span>{t.divisions.join(" · ")}</span>
                            )}
                          </div>
                          <div className="card-actions">
                            <button
                              onClick={() => {
                                setSelected(t.id);
                                setView("graph");
                              }}
                            >
                              {translate("Explore graph")}
                            </button>
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
                                  {translate("Complete")}
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
                                  {translate("Cancel")}
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
                                    {translate("Confirm delete")}
                                  </button>
                                  <button onClick={() => setConfirm(undefined)}>
                                    {translate("Keep")}
                                  </button>
                                </>
                              ) : (
                                <button
                                  className="icon-button"
                                  aria-label={translate("Delete {title}", {
                                    title: t.title,
                                  })}
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
              )}
            </>
          );
        }}
      </Load>
    </>
  );
}
