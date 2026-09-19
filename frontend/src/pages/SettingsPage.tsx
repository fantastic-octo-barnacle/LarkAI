import { usePreferences } from "../preferences";
import type { Settings, PageProps } from "../types";
import { useData } from "../useData";
import { Heading, Load, Badge } from "../components";

export function SettingsPage({ revision, mutate, busy }: PageProps) {
  const { t } = usePreferences();
  const state = useData<Settings>("/settings", revision);
  return (
    <>
      <Heading
        title={t("Settings")}
        description={t("Manage notification delivery for your team.")}
      />
      <section className="panel settings">
        <h2>{t("Feishu connection")}</h2>
        <p>
          {t(
            "After enabling the app’s user permissions in Feishu, reconnect to approve access to the organization directory and table fields.",
          )}
        </p>
        <a className="button primary" href="/auth/feishu?next=/settings">
          {t("Reconnect Feishu")}
        </a>
      </section>
      <Load state={state}>
        {(s) => (
          <section className="panel settings">
            <h2>{t("Email notifications")}</h2>
            <p className="muted">
              {s.smtp_configured
                ? t("SMTP connected to {host}", { host: s.smtp_host })
                : t("Dry run · configure SMTP to deliver email.")}
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void mutate(
                  "/settings",
                  {
                    email_recipients: new FormData(e.currentTarget).get(
                      "recipients",
                    ),
                  },
                  "PUT",
                );
              }}
            >
              <label>
                {t("Recipients")}
                <textarea
                  name="recipients"
                  defaultValue={s.email_recipients}
                  rows={4}
                />
              </label>
              <p className="muted">
                {t("Separate addresses with spaces or commas.")}
              </p>
              <div className="actions">
                <button disabled={busy} className="primary">
                  {t("Save settings")}
                </button>
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => void mutate("/settings/test")}
                >
                  {t("Send test email")}
                </button>
              </div>
            </form>
            <hr />
            <p>
              {t("Mode:")} <Badge value={s.mode} />
            </p>
            <p>
              {t("Auto sync:")}{" "}
              {s.auto_collect_seconds
                ? t("every {seconds} seconds", {
                    seconds: s.auto_collect_seconds,
                  })
                : t("disabled")}
            </p>
          </section>
        )}
      </Load>
    </>
  );
}
