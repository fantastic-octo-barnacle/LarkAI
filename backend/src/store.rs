use crate::model::{Event, Member, Task};
use serde::{Serialize, de::DeserializeOwned};
use sqlx::{
    SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions},
};
use std::{path::Path, str::FromStr};

#[derive(Clone)]
pub struct Store(pub SqlitePool);
impl Store {
    pub async fn open(path: &str) -> anyhow::Result<Self> {
        if path != ":memory:"
            && let Some(p) = Path::new(path).parent()
        {
            tokio::fs::create_dir_all(p).await?;
        }
        let opts = SqliteConnectOptions::from_str(path)?
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal)
            .busy_timeout(std::time::Duration::from_secs(5));
        let pool = SqlitePoolOptions::new()
            .max_connections(if path == ":memory:" { 1 } else { 5 })
            .connect_with(opts)
            .await?;
        sqlx::migrate!().run(&pool).await?;
        Ok(Self(pool))
    }
    pub async fn tasks(&self) -> anyhow::Result<Vec<Task>> {
        self.list("SELECT data FROM tasks ORDER BY id").await
    }
    pub async fn events(&self) -> anyhow::Result<Vec<Event>> {
        self.list("SELECT data FROM events ORDER BY id").await
    }
    pub async fn members(&self) -> anyhow::Result<Vec<Member>> {
        self.list("SELECT data FROM members ORDER BY id").await
    }
    async fn list<T: DeserializeOwned>(&self, query: &str) -> anyhow::Result<Vec<T>> {
        sqlx::query_scalar::<_, String>(query)
            .fetch_all(&self.0)
            .await?
            .iter()
            .map(|s| Ok(serde_json::from_str(s)?))
            .collect()
    }
    pub async fn task(&self, id: &str) -> anyhow::Result<Option<Task>> {
        sqlx::query_scalar::<_, String>("SELECT data FROM tasks WHERE id=?")
            .bind(id)
            .fetch_optional(&self.0)
            .await?
            .map(|s| Ok(serde_json::from_str(&s)?))
            .transpose()
    }
    pub async fn put_task(&self, t: &Task) -> anyhow::Result<()> {
        sqlx::query("INSERT INTO tasks(id,source,data) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,source=excluded.source").bind(&t.id).bind(&t.source).bind(serde_json::to_string(t)?).execute(&self.0).await?;
        Ok(())
    }
    pub async fn put_member(&self, m: &Member) -> anyhow::Result<()> {
        sqlx::query("INSERT INTO members(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data").bind(&m.id).bind(serde_json::to_string(m)?).execute(&self.0).await?;
        Ok(())
    }
    // Replace only a completely fetched source, atomically. Failed sources keep their cache.
    pub async fn replace<T: Serialize>(
        &self,
        table: &str,
        source: &str,
        items: &[(String, T)],
    ) -> anyhow::Result<()> {
        anyhow::ensure!(["tasks", "events"].contains(&table), "Invalid cache table");
        let mut tx = self.0.begin().await?;
        sqlx::query(&format!("DELETE FROM {table} WHERE source=?"))
            .bind(source)
            .execute(&mut *tx)
            .await?;
        for (id, item) in items {
            sqlx::query(&format!(
                "INSERT INTO {table}(id,source,data) VALUES(?,?,?)"
            ))
            .bind(id)
            .bind(source)
            .bind(serde_json::to_string(item)?)
            .execute(&mut *tx)
            .await?;
        }
        tx.commit().await?;
        Ok(())
    }
    pub async fn setting(&self, key: &str) -> anyhow::Result<String> {
        Ok(sqlx::query_scalar("SELECT value FROM settings WHERE key=?")
            .bind(key)
            .fetch_optional(&self.0)
            .await?
            .unwrap_or_default())
    }
    pub async fn set(&self, key: &str, value: &str) -> anyhow::Result<()> {
        sqlx::query("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(key).bind(value).execute(&self.0).await?;
        Ok(())
    }
}
