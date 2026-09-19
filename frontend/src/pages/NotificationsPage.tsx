import { usePreferences } from "../preferences";
import type { Notification } from "../types";
import { useData } from "../useData";
import { formatDate } from "../api";
import { Heading, Load, Empty, Badge } from "../components";

export function NotificationsPage({ revision }: { revision: number }) {
  const { t, locale } = usePreferences();
  const state = useData<Notification[]>("/notifications", revision);
  return (
    <>
      <Heading
        title={t("Notifications")}
        description={t("A delivery log for task changes and team updates.")}
      />
      <Load state={state}>
        {(rows) => (
          <section className="panel">
            {rows.length ? (
              rows.map((n) => (
                <details className="notification" key={n.id}>
                  <summary>
                    <div>
                      <strong>{n.subject}</strong>
                      <small>
                        {formatDate(n.created_at, locale)} ·{" "}
                        {n.recipients || t("No recipients")}
                      </small>
                    </div>
                    <Badge value={n.status} />
                  </summary>
                  <p>{n.body}</p>
                  {n.error && <p className="notice error">{n.error}</p>}
                </details>
              ))
            ) : (
              <Empty>{t("No notifications yet.")}</Empty>
            )}
          </section>
        )}
      </Load>
    </>
  );
}
