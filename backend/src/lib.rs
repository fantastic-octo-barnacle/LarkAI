pub mod auth;
pub mod auth_cache;
pub mod config;
pub mod graph;
pub mod model;
pub mod notify;
pub mod provider;
pub mod store;
pub mod timing;
pub mod web;
use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use config::Config;
use serde_json::json;
use std::sync::Arc;
use store::Store;

#[derive(Clone)]
pub struct App {
    pub cfg: Config,
    pub db: Store,
    pub http: reqwest::Client,
    pub sync_lock: Arc<tokio::sync::Mutex<()>>,
    pub token_lock: Arc<tokio::sync::Mutex<()>>,
    pub auth_cache: Arc<auth_cache::Cache>,
}
impl App {
    pub async fn new(cfg: Config) -> anyhow::Result<Self> {
        let db = Store::open(cfg.value("DATABASE_PATH", "data/larkai.sqlite3")).await?;
        let http = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(20))
            .redirect(reqwest::redirect::Policy::none())
            .build()?;
        Ok(Self {
            cfg,
            db,
            http,
            sync_lock: Arc::new(tokio::sync::Mutex::new(())),
            token_lock: Arc::new(tokio::sync::Mutex::new(())),
            auth_cache: Arc::new(auth_cache::Cache::default()),
        })
    }
}
pub struct Error(pub StatusCode, pub String);
impl Error {
    pub fn bad(message: impl Into<String>) -> Self {
        Self(StatusCode::BAD_REQUEST, message.into())
    }
    pub fn forbidden() -> Self {
        Self(
            StatusCode::FORBIDDEN,
            "Administrator access required".into(),
        )
    }
}
impl From<anyhow::Error> for Error {
    fn from(e: anyhow::Error) -> Self {
        if let Some(error) = e.downcast_ref::<provider::FeishuError>() {
            return Self(StatusCode::BAD_GATEWAY, error.to_string());
        }
        tracing::error!(error=%e, "Request failed");
        Self(
            StatusCode::INTERNAL_SERVER_ERROR,
            "The operation failed. Check the server logs and try again.".into(),
        )
    }
}
impl From<sqlx::Error> for Error {
    fn from(e: sqlx::Error) -> Self {
        anyhow::Error::from(e).into()
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error":self.1}))).into_response()
    }
}
pub type Result<T> = std::result::Result<T, Error>;
