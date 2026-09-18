//! Request-scoped wall-clock measurements. Submetrics overlap their parent phases.
use axum::{
    extract::{MatchedPath, Request},
    middleware::Next,
    response::Response,
};
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
    time::Instant,
};
tokio::task_local! { static METRICS: Arc<Mutex<BTreeMap<&'static str, f64>>>; }
pub struct Timer(&'static str, Instant);
impl Timer {
    pub fn start(name: &'static str) -> Self {
        Self(name, Instant::now())
    }
}
impl Drop for Timer {
    fn drop(&mut self) {
        let _ = METRICS.try_with(|m| {
            *m.lock().unwrap().entry(self.0).or_default() +=
                self.1.elapsed().as_secs_f64() * 1000.0;
        });
    }
}
pub async fn measure<T>(name: &'static str, future: impl std::future::Future<Output = T>) -> T {
    let _timer = Timer::start(name);
    future.await
}
pub async fn middleware(req: Request, next: Next) -> Response {
    let id = uuid::Uuid::new_v4().to_string();
    let route = req
        .extensions()
        .get::<MatchedPath>()
        .map(|p| p.as_str())
        .unwrap_or("static")
        .to_owned();
    let method = req.method().clone();
    let metrics = Arc::new(Mutex::new(BTreeMap::new()));
    let start = Instant::now();
    let mut response = METRICS.scope(metrics.clone(), next.run(req)).await;
    let total = start.elapsed().as_secs_f64() * 1000.0;
    let mut values = metrics.lock().unwrap();
    values.insert("total", total);
    let header = values
        .iter()
        .map(|(name, ms)| format!("{name};dur={ms:.2}"))
        .collect::<Vec<_>>()
        .join(", ");
    response
        .headers_mut()
        .insert("Server-Timing", header.parse().unwrap());
    response
        .headers_mut()
        .insert("X-Request-ID", id.parse().unwrap());
    tracing::info!(request_id=%id, %method, %route, status=response.status().as_u16(), timings=%header, "HTTP request completed");
    response
}
