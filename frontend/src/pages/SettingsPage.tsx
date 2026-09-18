import type { Settings, PageProps } from "../types";
import { useData } from "../useData";
import { Heading, Load, Badge } from "../components";

export function SettingsPage({ revision, mutate, busy }: PageProps) {
  const state = useData<Settings>("/settings", revision);
  return (
    <>
      <Heading
        title="Settings"
        description="Manage notification delivery for your team."
      />
      <section className="panel settings">
        <h2>Feishu connection</h2>
        <p>After enabling the app’s user permissions in Feishu, reconnect to approve access to the organization directory and table fields.</p>
        <a className="button primary" href="/auth/feishu?next=/settings">Reconnect Feishu</a>
      </section>
      <Load state={state}>
        {(s) => (
          <section className="panel settings">
            <h2>Email notifications</h2>
            <p className="muted">
              {s.smtp_configured
                ? `SMTP connected to ${s.smtp_host}`
                : "Dry run · configure SMTP to deliver email."}
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
                Recipients
                <textarea
                  name="recipients"
                  defaultValue={s.email_recipients}
                  rows={4}
                />
              </label>
              <p className="muted">Separate addresses with spaces or commas.</p>
              <div className="actions">
                <button disabled={busy} className="primary">
                  Save settings
                </button>
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => void mutate("/settings/test")}
                >
                  Send test email
                </button>
              </div>
            </form>
            <hr />
            <p>
              Mode: <Badge value={s.mode} />
            </p>
            <p>
              Auto sync:{" "}
              {s.auto_collect_seconds
                ? `every ${s.auto_collect_seconds} seconds`
                : "disabled"}
            </p>
          </section>
        )}
      </Load>
    </>
  );
}
