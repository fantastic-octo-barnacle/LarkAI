# Email notifications

Task changes write a notification audit record. If recipients and SMTP are configured, delivery runs asynchronously through lettre; task operations remain successful even when email delivery fails.

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (default true), `SMTP_SSL` (default false), `NOTIFY_EMAIL_FROM`, `NOTIFY_EMAIL_TO` and `NOTIFY_ON_TASK_CHANGE` (default true). Explicit SSL uses a TLS connection; otherwise STARTTLS is required unless explicitly disabled.

Admins can override recipients under **Settings** and send a test email. Cached assignee email addresses are included in task notifications. Clearing the override falls back to `NOTIFY_EMAIL_TO`. **Notifications** shows pending, delivered, dry_run, skipped or failed delivery status. Without SMTP, configured recipients produce dry-run records; without recipients or with notifications disabled, delivery is skipped.

Collection sends a digest of new or changed important updates compared with the previous collection snapshot. Unchanged future deadlines are not sent repeatedly. The first live collection establishes the baseline without sending historical updates. Digest delivery uses the same recipients/audit mechanism. Pending deliveries are process-local: a server shutdown during delivery can leave a pending audit record, and failed deliveries are not retried automatically.
