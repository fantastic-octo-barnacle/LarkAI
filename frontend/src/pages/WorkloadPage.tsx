import type { Workload } from "../types";
import { useData } from "../useData";
import { Heading, Load, Empty, Badge, TaskSummary } from "../components";

export function WorkloadPage({ revision }: { revision: number }) {
  const state = useData<Workload>("/workload", revision);
  return (
    <>
      <Heading
        title="Team workload"
        description="See who’s working on what, and where help is needed."
      />
      <Load state={state}>
        {(d) => (
          <>
            <p className="muted">
              {d.members.length} team members · {d.unassigned} unassigned tasks
            </p>
            <div className="workload-grid">
              {d.members.map((m) => (
                <section className="panel" key={m.id}>
                  <div className="panel-title">
                    <h2>{m.name}</h2>
                    <Badge value={`${m.active} active`} />
                  </div>
                  <div className="workload-stats">
                    <span>{m.stats.pending} pending</span>
                    <span>{m.stats.completed} done</span>
                    <span>{m.stats.overdue} overdue</span>
                  </div>
                  <details>
                    <summary>View {m.tasks.length} tasks</summary>
                    {m.tasks.map((t) => (
                      <TaskSummary key={t.id} task={t} />
                    ))}
                  </details>
                </section>
              ))}
            </div>
            {!d.members.length && (
              <Empty>Assigned tasks will appear here after a sync.</Empty>
            )}
          </>
        )}
      </Load>
    </>
  );
}
