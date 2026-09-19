use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn now() -> String {
    Utc::now().to_rfc3339()
}
pub fn timestamp(v: &str) -> Option<i64> {
    DateTime::parse_from_rfc3339(v)
        .ok()
        .map(|d| d.timestamp_millis())
}
pub fn iso(v: &Value, milliseconds: bool) -> String {
    let n = v.as_i64().or_else(|| v.as_str()?.parse().ok());
    n.and_then(|n| DateTime::from_timestamp_millis(if milliseconds { n } else { n * 1000 }))
        .map(|d| d.to_rfc3339())
        .unwrap_or_default()
}
pub fn text(v: &Value) -> String {
    match v {
        Value::Null => String::new(),
        Value::String(s) => s.clone(),
        Value::Array(a) => a
            .iter()
            .map(text)
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" "),
        Value::Object(_) => ["text", "name", "value"]
            .iter()
            .find_map(|k| v.get(k).map(text))
            .unwrap_or_default(),
        _ => v.to_string(),
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Member {
    pub id: String,
    pub name: String,
    pub email: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    #[serde(default)]
    pub parent_ids: Vec<String>,
    #[serde(default)]
    pub dependency_ids: Vec<String>,
    pub remote_id: String,
    pub source: String,
    pub table_id: String,
    pub title: String,
    pub description: String,
    pub due: String,
    pub priority: String,
    pub status: String,
    pub owners: Vec<Member>,
    pub divisions: Vec<String>,
    pub category: String,
    pub url: String,
    pub updated_at: String,
}
impl Task {
    pub fn active(&self) -> bool {
        matches!(self.status.as_str(), "pending" | "in_progress")
    }
    pub fn overdue(&self) -> bool {
        self.active() && timestamp(&self.due).is_some_and(|t| t < Utc::now().timestamp_millis())
    }
    pub fn event(&self) -> Event {
        Event {
            id: format!("task:{}", self.id),
            source: self.source.clone(),
            title: self.title.clone(),
            description: self.description.clone(),
            ts: self.due.clone(),
            author: self
                .owners
                .iter()
                .map(|m| m.name.clone())
                .collect::<Vec<_>>()
                .join(", "),
            url: self.url.clone(),
            importance: if self.active() {
                if ["HIGH", "URGENT"].contains(&self.priority.as_str()) {
                    3
                } else {
                    2
                }
            } else {
                1
            },
            tags: vec![self.status.clone(), self.priority.clone()],
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub source: String,
    pub title: String,
    pub description: String,
    pub ts: String,
    pub author: String,
    pub url: String,
    pub importance: u8,
    pub tags: Vec<String>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct TaskInput {
    pub title: String,
    pub description: String,
    pub due: String,
    pub priority: String,
    pub owner_ids: Vec<String>,
    pub divisions: Vec<String>,
    pub category: String,
    pub remark: String,
}
impl TaskInput {
    pub fn validate(&mut self) -> Result<(), &'static str> {
        self.title = self.title.trim().to_owned();
        if self.title.is_empty() || self.title.chars().count() > 500 {
            return Err("Title must contain 1–500 characters");
        }
        if !self.due.is_empty() && timestamp(&self.due).is_none() {
            return Err("Due date must include a timezone");
        }
        if self.priority.is_empty() {
            self.priority = "NORMAL".into();
        }
        if !["LOW", "NORMAL", "MEDIUM", "HIGH", "URGENT"].contains(&self.priority.as_str()) {
            return Err("Invalid priority");
        }
        if self.description.len() + self.remark.len() > 20000 || self.owner_ids.len() > 100 {
            return Err("Task payload is too large");
        }
        self.owner_ids.sort();
        self.owner_ids.dedup();
        Ok(())
    }
}
pub fn stats(tasks: &[Task]) -> Value {
    let mut next: Vec<_> = tasks
        .iter()
        .filter(|t| {
            t.active() && timestamp(&t.due).is_some_and(|d| d >= Utc::now().timestamp_millis())
        })
        .collect();
    next.sort_by_key(|t| timestamp(&t.due));
    next.truncate(5);
    json!({"total":tasks.len(), "pending":tasks.iter().filter(|t|t.status=="pending").count(), "in_progress":tasks.iter().filter(|t|t.status=="in_progress").count(), "completed":tasks.iter().filter(|t|t.status=="completed").count(), "cancelled":tasks.iter().filter(|t|t.status=="cancelled").count(), "overdue":tasks.iter().filter(|t|t.overdue()).count(), "next_deadlines":next})
}
