//! Public discovery documents and signing keys only; never caches bearer credentials.
use serde_json::Value;
use std::{
    collections::HashMap,
    time::{Duration, Instant},
};
use tokio::sync::Mutex;

#[derive(Default)]
pub struct Cache(Mutex<HashMap<String, (Instant, Value)>>);
impl Cache {
    #[cfg(test)]
    pub(crate) async fn seed(&self, url: &str, value: Value) {
        self.0
            .lock()
            .await
            .insert(url.into(), (Instant::now(), value));
    }

    pub async fn get(
        &self,
        http: &reqwest::Client,
        url: &str,
        refresh: bool,
    ) -> anyhow::Result<Value> {
        // Serialize cache misses, including unknown-key refreshes, to avoid request storms.
        let mut entries = self.0.lock().await;
        if let Some((at, value)) = entries.get(url) {
            let ttl = if refresh { 30 } else { 300 };
            if at.elapsed() < Duration::from_secs(ttl) {
                return Ok(value.clone());
            }
        }
        let value: Value = http
            .get(url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        entries.insert(url.to_owned(), (Instant::now(), value.clone()));
        Ok(value)
    }
}
