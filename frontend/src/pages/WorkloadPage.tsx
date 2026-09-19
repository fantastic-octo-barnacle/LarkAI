import { usePreferences } from "../preferences";
import type { Workload } from "../types";
import { useData } from "../useData";
import { Heading, Load, Empty, Badge, TaskSummary } from "../components";

export function WorkloadPage({ revision }: { revision: number }) {
  const { t } = usePreferences();
  const state = useData<Workload>("/workload", revision);
  return (
    <>
      <Heading
        title={t("Team workload")}
        description={t("See who’s working on what, and where help is needed.")}
      />
      <Load state={state}>
        {(d) => (
          <>
            <p className="muted">
              {t("{count} team members · {unassigned} unassigned tasks", {
                count: d.members.length,
                unassigned: d.unassigned,
              })}
            </p>
            <div className="workload-grid">
              {d.members.map((m) => (
                <section className="panel" key={m.id}>
                  <div className="panel-title">
                    <h2>{m.name}</h2>
                    <Badge value={t("{count} active", { count: m.active })} />
                  </div>
                  <div className="workload-stats">
                    <span>
                      {t("{count} pending", { count: m.stats.pending })}
                    </span>
                    <span>
                      {t("{count} done", { count: m.stats.completed })}
                    </span>
                    <span>
                      {t("{count} overdue", { count: m.stats.overdue })}
                    </span>
                  </div>
                  <details>
                    <summary>
                      {t("View {count} tasks", { count: m.tasks.length })}
                    </summary>
                    {m.tasks.map((t) => (
                      <TaskSummary key={t.id} task={t} />
                    ))}
                  </details>
                </section>
              ))}
            </div>
            {!d.members.length && (
              <Empty>
                {t("Assigned tasks will appear here after a sync.")}
              </Empty>
            )}
          </>
        )}
      </Load>
    </>
  );
}
