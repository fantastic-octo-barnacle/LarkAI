use crate::{
    App,
    model::{Event, Member, Task, TaskInput, iso, now, text, timestamp},
    notify,
};
use serde_json::{Value, json};
use std::collections::HashSet;

#[derive(Debug)]
pub struct FeishuError(pub String);
impl std::fmt::Display for FeishuError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for FeishuError {}

pub async fn call(
    app: &App,
    method: &str,
    path: &str,
    token: &str,
    body: Option<Value>,
) -> anyhow::Result<Value> {
    let url = format!(
        "{}/open-apis{}",
        app.cfg
            .value("FEISHU_BASE_URL", "https://open.feishu.cn")
            .trim_end_matches('/'),
        path
    );
    let mut req = app.http.request(method.parse()?, url).bearer_auth(token);
    if let Some(body) = body {
        req = req.json(&body);
    }
    let _timer = crate::timing::Timer::start("upstream");
    let response = req.send().await?;
    let status = response.status();
    let v: Value = response.json().await?;
    if !status.is_success() || v["code"].as_i64() != Some(0) {
        let code = v["code"].as_i64().unwrap_or(0);
        let scopes: Vec<&str> = v["error"]["permission_violations"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|p| p["subject"].as_str())
            .collect();
        let message = if code == 99991679 {
            format!(
                "Feishu permission missing (code {code}). Enable one of [{}] under user permissions, then reconnect Feishu in Settings.",
                scopes.join(", ")
            )
        } else {
            format!("Feishu request failed (HTTP {status}, code {code}). Check server logs.")
        };
        tracing::warn!(%status, code, path, "Feishu API rejected request");
        return Err(FeishuError(message).into());
    }
    Ok(v.get("data").cloned().unwrap_or(v))
}
pub async fn pages(
    app: &App,
    path: &str,
    key: &str,
    token: &str,
    post: bool,
) -> anyhow::Result<Vec<Value>> {
    let mut all = Vec::new();
    let mut cursor = String::new();
    let mut seen = HashSet::new();
    loop {
        let separator = if path.contains('?') { '&' } else { '?' };
        let query = {
            let mut query = url::form_urlencoded::Serializer::new(String::new());
            query.append_pair("page_size", "50");
            if !cursor.is_empty() {
                query.append_pair("page_token", &cursor);
            }
            query.finish()
        };
        let v = call(
            app,
            if post { "POST" } else { "GET" },
            &format!("{path}{separator}{query}"),
            token,
            post.then(|| json!({})),
        )
        .await?;
        if let Some(a) = v[key].as_array() {
            all.extend(a.iter().cloned());
        }
        if !v["has_more"].as_bool().unwrap_or(false) {
            break;
        }
        cursor = text(&v["page_token"]);
        anyhow::ensure!(
            !cursor.is_empty() && seen.insert(cursor.clone()),
            "Invalid pagination cursor"
        );
    }
    Ok(all)
}
pub async fn exchange(app: &App, grant: &str, code: &str) -> anyhow::Result<Value> {
    let _timer = crate::timing::Timer::start("upstream");
    let mut data = vec![
        ("grant_type", grant),
        ("client_id", app.cfg.get("FEISHU_APP_ID")),
        ("client_secret", app.cfg.get("FEISHU_APP_SECRET")),
    ];
    data.push((
        if grant == "refresh_token" {
            "refresh_token"
        } else {
            "code"
        },
        code,
    ));
    if grant == "authorization_code" {
        data.push(("redirect_uri", app.cfg.get("FEISHU_REDIRECT_URI")));
    }
    let mut v: Value = app
        .http
        .post(format!(
            "{}/oauth/v3/token",
            app.cfg
                .value("FEISHU_ACCOUNTS_URL", "https://accounts.feishu.cn")
                .trim_end_matches('/')
        ))
        .form(&data)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    anyhow::ensure!(
        v["code"].as_i64() == Some(0) && !text(&v["access_token"]).is_empty(),
        "Feishu token exchange failed"
    );
    v["expires_at"] =
        json!(chrono::Utc::now().timestamp() + v["expires_in"].as_i64().unwrap_or(7200));
    Ok(v)
}
pub async fn save_connection(
    app: &App,
    subject: &str,
    oid: &str,
    token: &Value,
) -> anyhow::Result<()> {
    anyhow::ensure!(
        !subject.is_empty() && !oid.is_empty(),
        "Missing connection identity"
    );
    sqlx::query("INSERT INTO connections(subject,open_id,data) VALUES(?,?,?) ON CONFLICT(subject) DO UPDATE SET open_id=excluded.open_id,data=excluded.data").bind(subject).bind(oid).bind(token.to_string()).execute(&app.db.0).await?;
    Ok(())
}
pub async fn open_id(app: &App, subject: &str) -> anyhow::Result<String> {
    Ok(
        sqlx::query_scalar("SELECT open_id FROM connections WHERE subject=?")
            .bind(subject)
            .fetch_optional(&app.db.0)
            .await?
            .unwrap_or_default(),
    )
}
pub async fn user_token(app: &App, subject: &str) -> anyhow::Result<String> {
    let _lock = app.token_lock.lock().await;
    let db_timer = crate::timing::Timer::start("db");
    let raw: String = sqlx::query_scalar("SELECT data FROM connections WHERE subject=?")
        .bind(subject)
        .fetch_one(&app.db.0)
        .await?;
    let mut v: Value = serde_json::from_str(&raw)?;
    drop(db_timer);
    if v["expires_at"].as_i64().unwrap_or(0) < chrono::Utc::now().timestamp() + 60 {
        let refresh = text(&v["refresh_token"]);
        anyhow::ensure!(!refresh.is_empty(), "Reconnect Feishu");
        let mut updated = exchange(app, "refresh_token", &refresh).await?;
        if text(&updated["refresh_token"]).is_empty() {
            updated["refresh_token"] = json!(refresh);
        }
        save_connection(app, subject, &open_id(app, subject).await?, &updated).await?;
        v = updated;
    }
    let token = text(&v["access_token"]);
    anyhow::ensure!(!token.is_empty(), "Reconnect Feishu");
    Ok(token)
}
fn member(v: &Value) -> Member {
    Member {
        id: text(&v["id"]),
        name: text(&v["name"]),
        email: text(&v["email"]),
    }
}
pub fn normalize_task(v: &Value) -> Task {
    let remote_id = text(&v["guid"]);
    Task {
        id: format!("feishu:{remote_id}"),
        remote_id,
        source: "feishu".into(),
        table_id: String::new(),
        title: text(&v["summary"]),
        description: text(&v["description"]),
        due: iso(&v["due"]["timestamp"], true),
        priority: "NORMAL".into(),
        status: if ["", "0"].contains(&text(&v["completed_at"]).as_str()) {
            "pending"
        } else {
            "completed"
        }
        .into(),
        owners: v["members"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|m| m["role"] == "assignee")
            .map(member)
            .collect(),
        divisions: vec![],
        category: String::new(),
        url: text(&v["url"]),
        updated_at: now(),
    }
}
fn field<'a>(app: &'a App, key: &str, fallback: &'a str) -> &'a str {
    app.cfg.value(key, fallback)
}
pub fn normalize_record(app: &App, table: &str, v: &Value) -> Option<Task> {
    let f = &v["fields"];
    let title = text(&f[field(app, "FEISHU_BITABLE_NAME_FIELD", "任务名称")]);
    if title.is_empty() {
        return None;
    }
    let remote_id = text(&v["record_id"]);
    if remote_id.is_empty() {
        return None;
    }
    let status = text(
        &f[field(
            app,
            "FEISHU_BITABLE_STATUS_FIELD",
            "任务状态（由技术组长验收）",
        )],
    );
    let priority = text(&f[field(app, "FEISHU_BITABLE_PRIORITY_FIELD", "优先级")]);
    let owners = f[field(app, "FEISHU_BITABLE_OWNER_FIELD", "负责人")]
        .as_array()
        .into_iter()
        .flatten()
        .map(member)
        .collect();
    let div = &f[field(app, "FEISHU_BITABLE_DIVISION_FIELD", "研发组别")];
    let divisions = if let Some(a) = div.as_array() {
        a.iter().map(text).collect()
    } else {
        let s = text(div);
        if s.is_empty() { vec![] } else { vec![s] }
    };
    Some(Task {
        id: format!("bitable:{table}:{remote_id}"),
        remote_id,
        source: "bitable".into(),
        table_id: table.into(),
        title,
        description: [
            text(
                &f[field(
                    app,
                    "FEISHU_BITABLE_REQUIREMENT_FIELD",
                    "任务需求（兵种组长填写）（务必详细！）",
                )],
            ),
            text(&f[field(app, "FEISHU_BITABLE_DESC_FIELD", "备注")]),
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("\n"),
        due: iso(&f[field(app, "FEISHU_BITABLE_DDL_FIELD", "ddl")], true),
        priority: match priority.as_str() {
            "高" | "高优先级" => "HIGH",
            "紧急" | "特急" => "URGENT",
            "中" => "MEDIUM",
            "低" => "LOW",
            _ => "NORMAL",
        }
        .into(),
        status: match status.as_str() {
            "执行中" => "in_progress",
            "已完成" => "completed",
            "已取消" | "已放弃" | "取消" | "终止" => "cancelled",
            "暂停" => "paused",
            _ => "pending",
        }
        .into(),
        owners,
        divisions,
        category: text(&f[field(app, "FEISHU_BITABLE_TYPE_FIELD", "兵种类型")]),
        url: String::new(),
        updated_at: now(),
    })
}
pub async fn base(app: &App, token: &str) -> anyhow::Result<String> {
    if !app.cfg.get("FEISHU_BITABLE_APP_TOKEN").is_empty() {
        return Ok(app.cfg.get("FEISHU_BITABLE_APP_TOKEN").into());
    }
    anyhow::ensure!(
        !app.cfg.get("FEISHU_WIKI_NODE_TOKEN").is_empty(),
        "Configure a Bitable app token or wiki node"
    );
    let q = url::form_urlencoded::Serializer::new(String::new())
        .append_pair("token", app.cfg.get("FEISHU_WIKI_NODE_TOKEN"))
        .finish();
    let v = call(
        app,
        "GET",
        &format!("/wiki/v2/spaces/get_node?{q}"),
        token,
        None,
    )
    .await?;
    anyhow::ensure!(
        v["node"]["obj_type"] == "bitable",
        "Wiki node is not a Bitable"
    );
    Ok(text(&v["node"]["obj_token"]))
}
pub fn task_body(input: &TaskInput) -> Value {
    let mut body = json!({"summary":input.title,"description":input.description,"client_token":uuid::Uuid::new_v4().to_string(),"members":input.owner_ids.iter().map(|id|json!({"id":id,"type":"user","role":"assignee"})).collect::<Vec<_>>()});
    if let Some(ms) = timestamp(&input.due) {
        body["due"] = json!({"timestamp":ms.to_string(),"is_all_day":false});
    }
    body
}
pub fn record_fields(app: &App, input: &TaskInput) -> Value {
    let mut f = json!({});
    for (key, default, value) in [
        ("FEISHU_BITABLE_NAME_FIELD", "任务名称", &input.title),
        (
            "FEISHU_BITABLE_REQUIREMENT_FIELD",
            "任务需求（兵种组长填写）（务必详细！）",
            &input.description,
        ),
        ("FEISHU_BITABLE_DESC_FIELD", "备注", &input.remark),
        ("FEISHU_BITABLE_TYPE_FIELD", "兵种类型", &input.category),
    ] {
        if !value.is_empty() {
            f[field(app, key, default)] = json!(value);
        }
    }
    if !input.divisions.is_empty() {
        f[field(app, "FEISHU_BITABLE_DIVISION_FIELD", "研发组别")] = json!(input.divisions);
    }
    if let Some(ms) = timestamp(&input.due) {
        f[field(app, "FEISHU_BITABLE_DDL_FIELD", "ddl")] = json!(ms);
    }
    f[field(app, "FEISHU_BITABLE_PRIORITY_FIELD", "优先级")] =
        json!(match input.priority.as_str() {
            "HIGH" | "URGENT" => "高",
            "LOW" => "低",
            _ => "中",
        });
    f[field(app, "FEISHU_BITABLE_OWNER_FIELD", "负责人")] = json!(
        input
            .owner_ids
            .iter()
            .map(|id| json!({"id":id}))
            .collect::<Vec<_>>()
    );
    f[field(
        app,
        "FEISHU_BITABLE_STATUS_FIELD",
        "任务状态（由技术组长验收）",
    )] = json!(app.cfg.value("FEISHU_BITABLE_DEFAULT_STATUS", "待执行"));
    f
}
pub async fn create(app: &App, subject: &str, mut input: TaskInput) -> anyhow::Result<Task> {
    let oid = open_id(app, subject).await?;
    if input.owner_ids.is_empty() {
        input.owner_ids.push(oid);
    }
    let members = app.db.members().await?;
    let mut t = Task {
        id: format!("mock:{}", uuid::Uuid::new_v4()),
        remote_id: String::new(),
        source: "mock".into(),
        table_id: String::new(),
        title: input.title.clone(),
        description: input.description.clone(),
        due: input.due.clone(),
        priority: input.priority.clone(),
        status: "pending".into(),
        owners: input
            .owner_ids
            .iter()
            .map(|id| {
                members
                    .iter()
                    .find(|m| &m.id == id)
                    .cloned()
                    .unwrap_or(Member {
                        id: id.clone(),
                        name: id.clone(),
                        email: String::new(),
                    })
            })
            .collect(),
        divisions: input.divisions.clone(),
        category: input.category.clone(),
        url: String::new(),
        updated_at: now(),
    };
    if !input.remark.is_empty() {
        t.description.push_str(&format!("\n{}", input.remark));
    }
    if app.cfg.live() {
        let token = user_token(app, subject).await?;
        let table = app.cfg.get("FEISHU_BITABLE_SUBMIT_TABLE_ID");
        if !table.is_empty() {
            let b = base(app, &token).await?;
            let v = call(
                app,
                "POST",
                &format!("/bitable/v1/apps/{b}/tables/{table}/records"),
                &token,
                Some(json!({"fields":record_fields(app,&input)})),
            )
            .await?;
            t.remote_id = text(&v["record"]["record_id"]);
            t.source = "bitable".into();
            t.table_id = table.into();
            t.id = format!("bitable:{table}:{}", t.remote_id);
        } else {
            let mut body = task_body(&input);
            body["description"] = json!(format!(
                "{}{}{}",
                t.description,
                if input.divisions.is_empty() {
                    String::new()
                } else {
                    format!("\n研发组别: {}", input.divisions.join("、"))
                },
                if input.category.is_empty() {
                    String::new()
                } else {
                    format!("\n兵种类型: {}", input.category)
                }
            ));
            let v = call(app, "POST", "/task/v2/tasks", &token, Some(body)).await?;
            t.remote_id = text(&v["task"]["guid"]);
            t.id = format!("feishu:{}", t.remote_id);
            t.source = "feishu".into();
            t.url = text(&v["task"]["url"]);
        }
        anyhow::ensure!(!t.remote_id.is_empty(), "Feishu returned no task ID");
    }
    app.db.put_task(&t).await?;
    Ok(t)
}
pub async fn action(app: &App, subject: &str, t: &mut Task, action: &str) -> anyhow::Result<()> {
    if app.cfg.live() {
        anyhow::ensure!(
            t.source != "mock",
            "Mock tasks cannot be modified in live mode"
        );
        let token = user_token(app, subject).await?;
        let path = if t.source == "bitable" {
            let b = base(app, &token).await?;
            anyhow::ensure!(!t.table_id.is_empty(), "Missing source table");
            format!(
                "/bitable/v1/apps/{b}/tables/{}/records/{}",
                t.table_id, t.remote_id
            )
        } else {
            format!("/task/v2/tasks/{}", t.remote_id)
        };
        let (method, body) = if action == "delete" {
            ("DELETE", None)
        } else if t.source == "bitable" {
            let mut f = json!({});
            f[field(
                app,
                "FEISHU_BITABLE_STATUS_FIELD",
                "任务状态（由技术组长验收）",
            )] = json!(if action == "complete" {
                "已完成"
            } else {
                "已放弃"
            });
            ("PUT", Some(json!({"fields":f})))
        } else {
            (
                "PATCH",
                Some(
                    json!({"task":{"completed_at":chrono::Utc::now().timestamp_millis().to_string()},"update_fields":["completed_at"]}),
                ),
            )
        };
        call(app, method, &path, &token, body).await?;
    }
    if action == "delete" {
        sqlx::query("DELETE FROM tasks WHERE id=?")
            .bind(&t.id)
            .execute(&app.db.0)
            .await?;
    } else {
        t.status = if action == "complete" {
            "completed"
        } else {
            "cancelled"
        }
        .into();
        t.updated_at = now();
        app.db.put_task(t).await?;
    }
    Ok(())
}
async fn collect_tasks(app: &App, token: &str) -> anyhow::Result<usize> {
    let items = pages(app, "/task/v2/tasks?type=my_tasks", "items", token, false).await?;
    let old = app.db.tasks().await?;
    let members = app.db.members().await?;
    let mut tasks = Vec::new();
    for v in items {
        let mut t = normalize_task(&v);
        anyhow::ensure!(!t.remote_id.is_empty(), "Missing task ID");
        if let Some(o) = old.iter().find(|o| o.id == t.id) {
            t.priority = o.priority.clone();
            t.divisions = o.divisions.clone();
            t.category = o.category.clone();
            if o.status == "cancelled" && t.status == "completed" {
                t.status = "cancelled".into();
            }
        }
        for m in &mut t.owners {
            if let Some(known) = members.iter().find(|k| k.id == m.id) {
                *m = known.clone();
            }
        }
        tasks.push((t.id.clone(), t));
    }
    let n = tasks.len();
    for (_, task) in tasks {
        app.db.put_task(&task).await?;
    }
    Ok(n)
}
async fn collect_bitable(app: &App, token: &str) -> anyhow::Result<usize> {
    if app.cfg.get("FEISHU_BITABLE_APP_TOKEN").is_empty()
        && app.cfg.get("FEISHU_WIKI_NODE_TOKEN").is_empty()
    {
        return Ok(0);
    }
    let b = base(app, token).await?;
    let tables = pages(
        app,
        &format!("/bitable/v1/apps/{b}/tables"),
        "items",
        token,
        false,
    )
    .await?;
    let mut tasks = Vec::new();
    for table in tables {
        let id = text(&table["table_id"]);
        let records = pages(
            app,
            &format!("/bitable/v1/apps/{b}/tables/{id}/records/search"),
            "items",
            token,
            true,
        )
        .await?;
        for r in records {
            if let Some(t) = normalize_record(app, &id, &r) {
                tasks.push((t.id.clone(), t));
            }
        }
    }
    let n = tasks.len();
    app.db.replace("tasks", "bitable", &tasks).await?;
    Ok(n)
}
async fn chats(app: &App, token: &str) -> anyhow::Result<Vec<Value>> {
    let ids = app.cfg.list("FEISHU_CHAT_IDS");
    if ids.is_empty() {
        pages(app, "/im/v1/chats", "items", token, false).await
    } else {
        Ok(ids
            .iter()
            .map(|id| json!({"chat_id":id,"name":id}))
            .collect())
    }
}
fn important(s: &str) -> u8 {
    if [
        "重要",
        "紧急",
        "截止",
        "比赛",
        "deadline",
        "urgent",
        "important",
    ]
    .iter()
    .any(|w| s.to_lowercase().contains(w))
    {
        2
    } else {
        1
    }
}
async fn collect_calendar(app: &App, token: &str) -> anyhow::Result<usize> {
    let mut id = app.cfg.get("FEISHU_CALENDAR_ID").to_owned();
    if id.is_empty() {
        id = pages(app, "/calendar/v4/calendars", "calendar_list", token, false)
            .await?
            .first()
            .map(|c| text(&c["calendar_id"]))
            .unwrap_or_default();
    }
    if id.is_empty() {
        return Ok(0);
    }
    let mut events = Vec::new();
    for v in pages(
        app,
        &format!("/calendar/v4/calendars/{id}/events"),
        "items",
        token,
        false,
    )
    .await?
    {
        if v["status"] == "cancelled" {
            continue;
        }
        let title = text(&v["summary"]);
        let description = text(&v["description"]);
        let mut ts = iso(&v["start_time"]["timestamp"], false);
        if ts.is_empty() {
            let date = text(&v["start_time"]["date"]);
            if !date.is_empty() {
                ts = format!("{date}T00:00:00Z");
            }
        }
        let e = Event {
            id: format!("meeting:{}", text(&v["event_id"])),
            source: "meeting".into(),
            importance: important(&format!("{title} {description}")),
            title,
            description,
            ts,
            author: String::new(),
            url: text(&v["url"]),
            tags: vec![],
        };
        events.push((e.id.clone(), e));
    }
    let n = events.len();
    app.db.replace("events", "meeting", &events).await?;
    Ok(n)
}
pub async fn sync(app: &App, subject: &str) -> anyhow::Result<Value> {
    let _lock = app.sync_lock.lock().await;
    let mut warnings = Vec::new();
    let mut sources = json!({});
    if app.cfg.live() {
        let token = user_token(app, subject).await?;
        for (name, result) in [
            ("tasks", collect_tasks(app, &token).await),
            ("bitable", collect_bitable(app, &token).await),
            ("calendar", collect_calendar(app, &token).await),
        ] {
            match result {
                Ok(n) => {
                    sources[name] = json!(n);
                }
                Err(e) => {
                    tracing::warn!(source=name,error=%e,"Collection source failed");
                    warnings.push(format!("{name}: {e} Previous data retained."));
                }
            }
        }
    }
    let result = json!({"last_sync":now(),"sources":sources,"warnings":warnings});
    app.db.set("sync", &result.to_string()).await?;
    notify::digest(app).await?;
    Ok(result)
}
pub async fn refresh_members(app: &App, subject: &str) -> anyhow::Result<Value> {
    if !app.cfg.live() {
        return Ok(json!({"count":app.db.members().await?.len(),"warnings":[]}));
    }
    let token = user_token(app, subject).await?;
    let mut warnings = vec![];
    let mut records = Vec::new();
    match pages(app,"/contact/v3/users/find_by_department?department_id=0&department_id_type=open_department_id&user_id_type=open_id","items",&token,false).await{Ok(v)=>records.extend(v),Err(e)=>{tracing::warn!(error=%e,"Directory collection failed");warnings.push(format!("Organization directory: {e}"));}}
    // Traverse department hierarchy so directory members outside the root are included.
    match pages(
        app,
        "/contact/v3/departments/0/children?fetch_child=true&department_id_type=open_department_id",
        "items",
        &token,
        false,
    )
    .await
    {
        Ok(depts) => {
            for dept in depts {
                let id = text(&dept["open_department_id"]);
                let q = url::form_urlencoded::Serializer::new(String::new())
                    .append_pair("department_id", &id)
                    .finish();
                match pages(app,&format!("/contact/v3/users/find_by_department?{q}&department_id_type=open_department_id&user_id_type=open_id"),"items",&token,false).await{Ok(v)=>records.extend(v),Err(_)=>warnings.push(format!("Department {id} unavailable"))}
            }
        }
        Err(e) => warnings.push(format!("Department listing: {e}")),
    }
    match chats(app, &token).await {
        Ok(chats) => {
            for c in chats {
                let id = text(&c["chat_id"]);
                match pages(
                    app,
                    &format!("/im/v1/chats/{id}/members?member_id_type=open_id"),
                    "items",
                    &token,
                    false,
                )
                .await
                {
                    Ok(v) => records.extend(v),
                    Err(_) => warnings.push(format!("Members of {id} unavailable")),
                }
            }
        }
        Err(_) => warnings.push("Group directory unavailable".into()),
    }
    let mut count = HashSet::new();
    for v in records {
        let id = if v["open_id"].is_string() {
            text(&v["open_id"])
        } else {
            text(&v["member_id"])
        };
        if id.is_empty() {
            continue;
        }
        let mut name = text(&v["name"]);
        if name.is_empty() {
            name = id.clone();
        }
        let mut email = text(&v["email"]);
        if email.is_empty() {
            email = text(&v["enterprise_email"]);
        }
        let m = Member {
            id: id.clone(),
            name,
            email,
        };
        if count.insert(id) {
            app.db.put_member(&m).await?;
        }
    }
    Ok(json!({"count":count.len(),"warnings":warnings}))
}
pub async fn options(app: &App, subject: &str) -> anyhow::Result<Value> {
    let mut result = json!({"categories":["步兵（HKU）","哨兵（HKU）","无人机","飞镖","总车组","场地设施","步兵（CUHKSZ）","重装","哨兵（CUHKSZ）"],"divisions":["机械","硬件","算法","电控","管理","宣营"]});
    if app.cfg.live() && !app.cfg.get("FEISHU_BITABLE_SUBMIT_TABLE_ID").is_empty() {
        let token = user_token(app, subject).await?;
        let b = base(app, &token).await?;
        let table = app.cfg.get("FEISHU_BITABLE_SUBMIT_TABLE_ID");
        for f in pages(
            app,
            &format!("/bitable/v1/apps/{b}/tables/{table}/fields"),
            "items",
            &token,
            false,
        )
        .await?
        {
            for (key, name) in [
                (
                    "categories",
                    field(app, "FEISHU_BITABLE_TYPE_FIELD", "兵种类型"),
                ),
                (
                    "divisions",
                    field(app, "FEISHU_BITABLE_DIVISION_FIELD", "研发组别"),
                ),
            ] {
                if f["field_name"] == name {
                    let values: Vec<_> = f["property"]["options"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .map(|o| text(&o["name"]))
                        .collect();
                    if !values.is_empty() {
                        result[key] = json!(values);
                    }
                }
            }
        }
    }
    Ok(result)
}
