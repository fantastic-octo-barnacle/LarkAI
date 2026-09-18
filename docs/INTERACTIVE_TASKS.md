# Interactive tasks

The React task board creates, completes, cancels and deletes tasks through JSON APIs. Task forms support a title, description, timezone-aware deadline, priority, multiple assignees, divisions, category and remark. Search/filter/grouping is available by status, source and division.

## Source mapping

When `FEISHU_BITABLE_SUBMIT_TABLE_ID` is configured, creation uses `POST /bitable/v1/apps/{base}/tables/{table}/records`. Column names come from `FEISHU_BITABLE_*_FIELD`. Categories and divisions come from the table's field options when available. Failed Bitable creation is reported; it never silently creates a task in a different system.

Without a submit table, creation uses `POST /task/v2/tasks`. Deadlines use milliseconds in a string-valued `due.timestamp`; members carry `role=assignee`. Priority is local because task-v2 has no priority field. Completion uses PATCH with `task.completed_at` and `update_fields=["completed_at"]`. Cancellation also completes the upstream task and retains a local cancelled marker.

Bitable completion/cancellation uses PUT to the original record's table, with status `已完成`/`已放弃`. Deletion uses the source-specific DELETE endpoint and requires admin access. Bitable records must use the configured task name field to be mirrored; customize the field mapping for your base rather than relying on heuristic title detection.

All actions require a connected Feishu account and CSRF token; admin actions also check role. Authorization failures never replay task submissions after reconnecting. Local state changes only after an upstream operation succeeds. Every successful lifecycle action records a notification audit entry. Mock mode implements the same API locally with no remote calls.
