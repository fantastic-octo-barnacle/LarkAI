import { usePreferences } from "../preferences";
import { useData } from "../useData";
import { Heading, Load, Badge } from "../components";

export function DiagnosticsPage({ revision }: { revision: number }) {
  const { t } = usePreferences();
  const state = useData<{
    checks: { name: string; ok: boolean; detail: string }[];
  }>("/diagnostics", revision);
  return (
    <>
      <Heading
        title={t("Diagnostics")}
        description={t("Check the services behind your workspace.")}
      />
      <Load state={state}>
        {(d) => (
          <section className="panel">
            {d.checks.map((c) => (
              <div className="row" key={c.name}>
                <div>
                  <strong>{c.name}</strong>
                  <small>{c.detail}</small>
                </div>
                <Badge value={c.ok ? "healthy" : "unavailable"} />
              </div>
            ))}
          </section>
        )}
      </Load>
    </>
  );
}
