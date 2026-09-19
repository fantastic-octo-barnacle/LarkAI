import { usePreferences } from "../preferences";
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { Dashboard } from "../types";
import { useData } from "../useData";
import { formatDate } from "../api";
import {
  Heading,
  Load,
  StatsGrid,
  Empty,
  TaskSummary,
  Badge,
  LinkOut,
} from "../components";

export function DashboardPage({ revision }: { revision: number }) {
  const { t, locale } = usePreferences();
  const state = useData<Dashboard>("/dashboard", revision);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <>
      <Heading
        title={t("Team overview")}
        description={t("The work ahead, and the updates that matter.")}
      />
      <Load state={state}>
        {(d) => (
          <>
            <StatsGrid stats={d.stats} />
            <div className="columns">
              <section className="panel">
                <div className="panel-title">
                  <h2>{t("Upcoming deadlines")}</h2>
                  <NavLink to="/tasks">
                    {t("View tasks")}
                    <ArrowUpRight size={14} />
                  </NavLink>
                </div>
                {d.stats.next_deadlines.length ? (
                  d.stats.next_deadlines.map((t) => (
                    <TaskSummary key={t.id} task={t} />
                  ))
                ) : (
                  <Empty>
                    {t("No upcoming deadlines. New tasks will appear here.")}
                  </Empty>
                )}
              </section>
              <section className="panel">
                <div className="panel-title">
                  <h2>{t("Important updates")}</h2>
                  <NavLink to="/timeline">
                    {t("Timeline")}
                    <ArrowUpRight size={14} />
                  </NavLink>
                </div>
                {d.important.length ? (
                  d.important.map((e) => (
                    <div className="row" key={e.id}>
                      <div>
                        <Badge value={e.source} />
                        <strong>{e.title}</strong>
                        <small>{formatDate(e.ts, locale)}</small>
                      </div>
                      <LinkOut url={e.url} />
                    </div>
                  ))
                ) : (
                  <Empty>
                    {t("Sync Feishu to bring your team’s updates together.")}
                  </Empty>
                )}
              </section>
            </div>
            <section className="panel">
              <div className="panel-title">
                <h2>
                  {t("Team directory")}{" "}
                  <span className="count">{d.members.length}</span>
                </h2>
                <input
                  aria-label={t("Search members")}
                  placeholder={t("Find a teammate…")}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <div className="member-grid">
                {d.members
                  .filter((m) => m.name.toLowerCase().includes(q.toLowerCase()))
                  .map((m) => (
                    <label key={m.id} className="member">
                      <input
                        type="checkbox"
                        checked={selected.includes(m.id)}
                        onChange={() =>
                          setSelected((s) =>
                            s.includes(m.id)
                              ? s.filter((id) => id !== m.id)
                              : [...s, m.id],
                          )
                        }
                      />
                      <span className="avatar">
                        {(m.name || "?").slice(0, 1)}
                      </span>
                      <span>
                        {m.name || m.id}
                        <small>{m.email}</small>
                      </span>
                    </label>
                  ))}
              </div>
              {!d.members.length && (
                <Empty>{t("Refresh members to populate the directory.")}</Empty>
              )}
              {!!selected.length && (
                <textarea
                  aria-label={t("Selected members")}
                  readOnly
                  value={d.members
                    .filter((m) => selected.includes(m.id))
                    .map((m) => `${m.name} ${m.email || m.id}`)
                    .join("\n")}
                />
              )}
            </section>
            {d.sync && (
              <p className="muted">
                {t("Last synced")} {formatDate(d.sync.last_sync, locale)}
                {d.sync.warnings.map((w) => (
                  <span className="notice" key={w}>
                    {w}
                  </span>
                ))}
              </p>
            )}
          </>
        )}
      </Load>
    </>
  );
}
