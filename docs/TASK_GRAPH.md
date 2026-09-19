# Task hierarchy and dependency graph

Open **Tasks → Graph**, or **Explore graph** on a task card. The left sidebar is the parent/subtask hierarchy. Solid arrows in the centre point from a prerequisite to its dependant. Dashed arrows show parent-to-subtask relationships; the Show hierarchy toggle is enabled by default. With hierarchy shown, the focus graph includes the selected task’s descendants and the ancestors of visible nodes. The right panel shows task details and links in both directions. Selecting a task focuses its immediate prerequisites and dependants; expand upstream/downstream for transitive relationships, or select Entire graph. Zoom, fit and scroll controls support larger graphs. Search, status and team filters narrow the task tree without hiding linked context from the graph. Board remains available.

`父记录` defines containment, while `前置/依赖` defines execution order. Both are same-table Bitable link fields. Dependencies allow multiple targets. Dependants are computed by reversing the stored links. Parent links never imply dependencies, inherited blockers or automatic completion. Missing/unnamed records remain visible; unnamed records use a local display label without renaming the Feishu record. Cancelled or unavailable prerequisites are unresolved; all prerequisites must be completed for an active task to stop showing Blocked.

Select **Edit relationships** to change the parent and prerequisites. The server enforces one parent, prevents self-links and cycles, and restricts links to the same source table. It reads the live source table before validating a save and rejects stale relationship edits. Only changed link fields are sent to Feishu; titles, status, owners and other cells are untouched. Existing permissions, CSRF checks and the shared mutation/sync lock apply. Mock mode supports the same editor locally; task-v2 records have no relationship writeback.

Feishu edits bypass the app's validation. Sync reports imported cycles, and the graph highlights their members instead of failing or silently dropping edges. Missing referenced records are shown as unavailable. Cycles must be resolved by editing their links. Feishu does not provide an atomic graph-wide transaction here: a direct Feishu edit racing between the app's validation read and write can still create a cycle, which the next sync detects.

Configure field names with `FEISHU_BITABLE_PARENT_FIELD` (default `父记录`) and `FEISHU_BITABLE_DEPENDENCY_FIELD` (default `前置/依赖`). Create the dependency field as a one-way same-table link; no reverse field is required. Old cached tasks deserialize with empty relationships until the next sync; no SQLite schema migration is needed. Restart the updated backend and sync once to load existing relationships.

## Live test records added on 2026-09-19

Base `WRJLbv47PaitdjsvUZZcQKyon1e`, table `tblSy6tBtCNhQuuv`. Dependency field: `fldHHnaUAd`.

| Record | ID |
| --- | --- |
| Test DAG · 关系图演示 | recvvDD70vDMp5 |
| Test DAG · 设计完成 | recvvDDaeBo3rO |
| Test DAG · 零件到货 | recvvDDaeBXkms |
| Test DAG · 组装与走线 | recvvDDdfsIxTM |
| Test DAG · 整车测试 | recvvDDltMBsZZ |
| Test DAG · 走线检查（子任务） | recvvDDltMfTdc |

Assembly depends on Design and Parts; Verification depends on Assembly. Wiring is a child of Assembly. Other test tasks are children of the test project. All links are between these new records. The original 74 records' names, parent links and dependency cells were compared before/after and were unchanged. No update or delete operations were sent for original records. Tests remain in Feishu for review.
