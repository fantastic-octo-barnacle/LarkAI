# Email Notifications

Task changes and important events can trigger email notifications. Delivery is best-effort: the website never blocks on SMTP, and every attempt (including dry-runs and failures) is recorded in the `notifications` table, visible under **Notifications** on the site.

## Triggers

| Trigger | Kind | When |
|---|---|---|
| Task created | `task_created` | After a successful `POST /tasks/new` |
| Task cancelled | `task_cancelled` | After successful cancel |
| Task completed | `task_completed` | After successful complete |
| Task deleted | `task_deleted` | After admin delete |
| Test | `task_updated` | Settings -> "Send test notification" |
| Important digest | `digest_important` | CLI `python -m scripts.collect --notify`, or automatically by the server auto-collect loop when `RM_AUTO_COLLECT_SECONDS` is set. Both share the same dedup: only important items newer than the last digest trigger an email (first run only records a baseline) |

The body includes task title, description, priority, due, status and actor, in both plain text and simple HTML.

## Configuration (`.env`)

```bash
NOTIFY_EMAIL_FROM=rmtasks@example.com
NOTIFY_EMAIL_TO=manager@example.com teammate@example.com   # space separated
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=rmtasks@example.com
SMTP_PASSWORD=...
SMTP_STARTTLS=1          # STARTTLS (port 587)
SMTP_SSL=0               # set 1 for implicit TLS (port 465)
NOTIFY_ON_TASK_CHANGE=1  # 0 to disable emails (audit trail still recorded)
```

If `SMTP_HOST` is empty the notifier runs in **dry-run** mode: no email leaves, but the record is still stored with status `dry_run`. Recipients can also be overridden per-deployment from **Settings** (stored in the `settings` table as `email_recipients`). Task-change emails additionally include the assignee's stored email (`users.email`) when it is known.

### Common SMTP providers

`SMTP_PASSWORD` is usually an **authorization code / app password** generated in the mailbox settings (never the login password).

| Provider | Host | Port | TLS |
|---|---|---|---|
| QQ 邮箱 | `smtp.qq.com` | 465 | `SMTP_SSL=1` |
| 163 邮箱 | `smtp.163.com` | 465 (994) | `SMTP_SSL=1` |
| 阿里云企业邮箱 | `smtp.aliyun.com` | 465 | `SMTP_SSL=1` |
| Gmail | `smtp.gmail.com` | 587 | `SMTP_STARTTLS=1` (app password) |

Example (QQ):

```bash
NOTIFY_EMAIL_FROM=your-name@qq.com
NOTIFY_EMAIL_TO=manager@qq.com
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your-name@qq.com
SMTP_PASSWORD=<authorization-code>
SMTP_SSL=1
SMTP_STARTTLS=0
```

Then send a test from **Settings → Send test notification** and check `/notifications` for status `sent`.

## Delivery status values

| Status | Meaning |
|---|---|
| `sent` | SMTP accepted the message |
| `dry_run` | No SMTP configured - recorded only |
| `skipped` | Notifications disabled or no recipients |
| `failed` | SMTP error - the exception text is stored in the `error` column |

## Implementation

- `rmtask/notify/emailer.py`: `Emailer.send()` uses stdlib `smtplib` + `email.message`; supports STARTTLS and implicit SSL; returns `dry_run` / `sent`.
- `rmtask/notify/service.py`: `notify_task_change()` / `notify_important_digest()` build the message, call the emailer inside a try/except, then always write the audit row - they never raise out of a request.
- Schedule the digest with cron, e.g. `0 8 * * * ... python -m scripts.collect --notify`.
