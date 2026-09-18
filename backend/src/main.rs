use larkai::{App, config::Config, provider, web};
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "larkai=info,tower_http=info".into()),
        )
        .init();
    let app = App::new(Config::load()?).await?;
    if std::env::args().any(|s| s == "check-auth") {
        println!("{}", larkai::auth::check_oidc(&app).await?);
        return Ok(());
    }
    let interval = app.cfg.number("RM_AUTO_COLLECT_SECONDS", 0);
    if std::env::args().any(|s| s == "collect") {
        let subject = sqlx::query_scalar::<_, String>(
            "SELECT subject FROM connections ORDER BY subject LIMIT 1",
        )
        .fetch_optional(&app.db.0)
        .await?
        .unwrap_or_default();
        println!("{}", provider::sync(&app, &subject).await?);
        return Ok(());
    }
    if interval > 0 {
        let a = app.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(interval)).await;
                let subject = sqlx::query_scalar::<_, String>(
                    "SELECT subject FROM connections ORDER BY subject LIMIT 1",
                )
                .fetch_optional(&a.db.0)
                .await
                .ok()
                .flatten();
                if let Some(s) = subject
                    && let Err(e) = provider::sync(&a, &s).await
                {
                    tracing::warn!(error=%e,"Auto collection failed");
                }
            }
        });
    }
    let address = format!(
        "{}:{}",
        app.cfg.value("HOST", "127.0.0.1"),
        app.cfg.value("PORT", "8000")
    );
    let listener = tokio::net::TcpListener::bind(&address).await?;
    tracing::info!(%address,"LarkAI listening");
    axum::serve(listener, web::router(app))
        .with_graceful_shutdown(async {
            tokio::signal::ctrl_c().await.ok();
        })
        .await?;
    Ok(())
}
