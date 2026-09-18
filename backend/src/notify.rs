use crate::{
    App,
    model::{Task, now},
};
use lettre::{
    AsyncSmtpTransport, AsyncTransport, Message, Tokio1Executor,
    transport::smtp::{
        authentication::Credentials,
        client::{Tls, TlsParameters},
    },
};
use serde_json::json;

pub async fn deliver(
    app: &App,
    kind: &str,
    subject: &str,
    body: &str,
    owner_emails: Vec<String>,
) -> anyhow::Result<()> {
    let saved = app.db.setting("email_recipients").await?;
    let recipients = if saved.is_empty() {
        app.cfg.get("NOTIFY_EMAIL_TO")
    } else {
        &saved
    };
    let mut recipients: Vec<String> = recipients
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .chain(owner_emails.into_iter().filter(|s| !s.is_empty()))
        .collect();
    recipients.sort();
    recipients.dedup();
    let enabled = app.cfg.flag("NOTIFY_ON_TASK_CHANGE", true) && !recipients.is_empty();
    let status = if !enabled {
        "skipped"
    } else if app.cfg.get("SMTP_HOST").is_empty() {
        "dry_run"
    } else {
        "pending"
    };
    let id=sqlx::query("INSERT INTO notifications(created_at,kind,subject,body,recipients,status) VALUES(?,?,?,?,?,?)").bind(now()).bind(kind).bind(subject).bind(body).bind(recipients.join(" ")).bind(status).execute(&app.db.0).await?.last_insert_rowid();
    if status == "pending" {
        let a = app.clone();
        let subject = subject.to_owned();
        let body = body.to_owned();
        tokio::spawn(async move {
            let result = send(&a, &subject, &body, &recipients).await;
            let (status, error) = match result {
                Ok(()) => ("delivered", String::new()),
                Err(e) => {
                    tracing::warn!(error=%e,"Email delivery failed");
                    ("failed", "SMTP delivery failed; check server logs".into())
                }
            };
            if let Err(e) = sqlx::query("UPDATE notifications SET status=?,error=? WHERE id=?")
                .bind(status)
                .bind(error)
                .bind(id)
                .execute(&a.db.0)
                .await
            {
                tracing::error!(error=%e,"Unable to update notification audit");
            }
        });
    }
    Ok(())
}
async fn send(app: &App, subject: &str, body: &str, recipients: &[String]) -> anyhow::Result<()> {
    let mut message = Message::builder()
        .from(
            app.cfg
                .value("NOTIFY_EMAIL_FROM", "rmtasks@example.com")
                .parse()?,
        )
        .subject(subject);
    for recipient in recipients {
        message = message.to(recipient.parse()?);
    }
    let host = app.cfg.get("SMTP_HOST");
    let mut builder = AsyncSmtpTransport::<Tokio1Executor>::builder_dangerous(host)
        .port(app.cfg.number("SMTP_PORT", 587) as u16)
        .timeout(Some(std::time::Duration::from_secs(20)));
    if app.cfg.flag("SMTP_SSL", false) {
        builder = builder.tls(Tls::Wrapper(TlsParameters::new(host.into())?));
    } else if app.cfg.flag("SMTP_STARTTLS", true) {
        builder = builder.tls(Tls::Required(TlsParameters::new(host.into())?));
    }
    if !app.cfg.get("SMTP_USER").is_empty() {
        builder = builder.credentials(Credentials::new(
            app.cfg.get("SMTP_USER").into(),
            app.cfg.get("SMTP_PASSWORD").into(),
        ));
    }
    builder.build().send(message.body(body.to_owned())?).await?;
    Ok(())
}
pub async fn task(app: &App, kind: &str, t: &Task, actor: &str) {
    let subject = format!(
        "[{}] Task {kind}: {}",
        app.cfg
            .value("FEISHU_TENANT_NAME", "RoboMaster Research Team"),
        t.title
    );
    let body = format!(
        "Task: {}\nDescription: {}\nPriority: {}\nDue: {}\nStatus: {}\nActor: {actor}",
        t.title, t.description, t.priority, t.due, t.status
    );
    if let Err(e) = deliver(
        app,
        &format!("task_{kind}"),
        &subject,
        &body,
        t.owners.iter().map(|m| m.email.clone()).collect(),
    )
    .await
    {
        tracing::error!(error=%e,"Notification audit failed");
    }
}
pub async fn digest(app: &App) -> anyhow::Result<()> {
    if !app.cfg.live()
        || app.cfg.get("SMTP_HOST").is_empty()
        || !app.cfg.flag("NOTIFY_ON_TASK_CHANGE", true)
    {
        return Ok(());
    }
    // Compare content, not deadline timestamps: future deadlines must not be
    // mailed again on every collection tick.
    let previous = app.db.setting("digest_seen").await?;
    let seen: std::collections::HashSet<String> =
        serde_json::from_str(&previous).unwrap_or_default();
    let mut events = app.db.events().await?;
    events.extend(app.db.tasks().await?.iter().map(Task::event));
    let mut current = std::collections::HashSet::new();
    let mut fresh = Vec::new();
    for event in events.iter().filter(|e| e.importance >= 2) {
        let fingerprint = serde_json::to_string(event)?;
        if !previous.is_empty() && !seen.contains(&fingerprint) {
            fresh.push(event);
        }
        current.insert(fingerprint);
    }
    if !fresh.is_empty() {
        deliver(
            app,
            "digest",
            "Important team updates",
            &fresh
                .iter()
                .map(|e| format!("{} — {}", e.title, e.ts))
                .collect::<Vec<_>>()
                .join("\n"),
            vec![],
        )
        .await?;
    }
    app.db
        .set("digest_seen", &serde_json::to_string(&current)?)
        .await?;
    app.db.set("last_digest", &now()).await?;
    Ok(())
}
pub async fn settings(app: &App) -> anyhow::Result<serde_json::Value> {
    let saved = app.db.setting("email_recipients").await?;
    Ok(
        json!({"email_recipients":if saved.is_empty(){app.cfg.get("NOTIFY_EMAIL_TO")}else{&saved},"smtp_configured":!app.cfg.get("SMTP_HOST").is_empty(),"smtp_host":app.cfg.get("SMTP_HOST"),"mode":app.cfg.mode(),"auto_collect_seconds":app.cfg.number("RM_AUTO_COLLECT_SECONDS",0)}),
    )
}
