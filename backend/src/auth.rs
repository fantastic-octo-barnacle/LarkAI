use crate::{
    App, Error, Result,
    model::{Member, text},
    provider,
};
use axum::{
    Extension, Json,
    extract::{Query, Request, State},
    http::{StatusCode, header},
    middleware::Next,
    response::{IntoResponse, Redirect, Response},
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

#[derive(Clone, Default, Serialize, Deserialize)]
pub struct Session {
    #[serde(skip)]
    pub id: String,
    pub subject: String,
    pub name: String,
    pub role: String,
    pub csrf: String,
    pub access_token: String,
    pub token_expires: i64,
    pub oauth_state: String,
    pub nonce: String,
    pub verifier: String,
    pub flow: String,
    pub return_to: String,
    pub flow_expires: i64,
}
impl Session {
    pub fn admin(&self) -> bool {
        self.role == "admin"
    }
}
pub fn random() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}
pub fn safe_return(s: &str) -> String {
    if s.starts_with('/') && !s.starts_with("//") && !s.contains(['\\', '\r', '\n']) {
        s.to_owned()
    } else {
        "/".into()
    }
}
fn equal(a: &str, b: &str) -> bool {
    !a.is_empty() && bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}
pub async fn save(app: &App, s: &Session) -> anyhow::Result<()> {
    sqlx::query("INSERT INTO sessions(id,data,expires_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,expires_at=excluded.expires_at").bind(&s.id).bind(serde_json::to_string(s)?).bind(chrono::Utc::now().timestamp()+28800).execute(&app.db.0).await?;
    Ok(())
}
async fn rotate(app: &App, s: &mut Session) -> anyhow::Result<()> {
    sqlx::query("DELETE FROM sessions WHERE id=?")
        .bind(&s.id)
        .execute(&app.db.0)
        .await?;
    s.id = random();
    s.csrf = random();
    save(app, s).await
}
fn cookie(app: &App, id: &str) -> String {
    format!(
        "{}={id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800{}",
        app.cfg.cookie(),
        if app.cfg.secure() { "; Secure" } else { "" }
    )
}
fn with_cookie(app: &App, s: &Session, response: impl IntoResponse) -> Response {
    let mut r = response.into_response();
    r.headers_mut()
        .insert(header::SET_COOKIE, cookie(app, &s.id).parse().unwrap());
    r
}

async fn signed_claims(
    app: &App,
    token: &str,
    jwks_uri: &str,
    issuer: &str,
    audience: &str,
) -> anyhow::Result<Value> {
    let head = jsonwebtoken::decode_header(token)?;
    anyhow::ensure!(
        head.alg == jsonwebtoken::Algorithm::RS256,
        "Unsupported signing algorithm"
    );
    let jwks: jsonwebtoken::jwk::JwkSet = app
        .http
        .get(jwks_uri)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    let key = jwks
        .find(
            head.kid
                .as_deref()
                .ok_or_else(|| anyhow::anyhow!("Missing key ID"))?,
        )
        .ok_or_else(|| anyhow::anyhow!("Unknown signing key"))?;
    let mut validation = jsonwebtoken::Validation::new(jsonwebtoken::Algorithm::RS256);
    validation.set_audience(&[audience]);
    validation.set_issuer(&[issuer]);
    validation.set_required_spec_claims(&["exp", "iat", "sub", "iss", "aud"]);
    let claims = jsonwebtoken::decode::<Value>(
        token,
        &jsonwebtoken::DecodingKey::from_jwk(key)?,
        &validation,
    )?
    .claims;
    anyhow::ensure!(!text(&claims["sub"]).is_empty(), "Missing subject");
    Ok(claims)
}
async fn metadata(app: &App) -> anyhow::Result<Value> {
    let issuer = app.cfg.get("OIDC_ISSUER").trim_end_matches('/');
    let m: Value = app
        .http
        .get(format!("{issuer}/.well-known/openid-configuration"))
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    anyhow::ensure!(m["issuer"].as_str() == Some(issuer), "OIDC issuer mismatch");
    for key in [
        "authorization_endpoint",
        "token_endpoint",
        "userinfo_endpoint",
        "jwks_uri",
    ] {
        let u = url::Url::parse(m[key].as_str().unwrap_or(""))?;
        anyhow::ensure!(
            u.scheme() == "https" && u.host_str().is_some(),
            "Insecure OIDC endpoint"
        );
    }
    Ok(m)
}
async fn userinfo(app: &App, token: &str, subject: &str) -> anyhow::Result<Value> {
    let m = metadata(app).await?;
    let profile: Value = app
        .http
        .get(text(&m["userinfo_endpoint"]))
        .bearer_auth(token)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    anyhow::ensure!(
        profile["sub"].as_str() == Some(subject)
            && matches!(profile["role"].as_str(), Some("admin" | "member")),
        "Invalid identity"
    );
    Ok(profile)
}
pub async fn guard(State(app): State<App>, mut req: Request, next: Next) -> Response {
    match guard_inner(&app, &mut req).await {
        Ok(Some(r)) => r,
        Ok(None) => {
            let session = req.extensions().get::<Session>().cloned();
            let mut r = next.run(req).await;
            if !r.headers().contains_key(header::SET_COOKIE)
                && let Some(s) = session
            {
                r.headers_mut()
                    .insert(header::SET_COOKIE, cookie(&app, &s.id).parse().unwrap());
            }
            r.headers_mut()
                .insert(header::CACHE_CONTROL, "no-store".parse().unwrap());
            r.headers_mut()
                .insert("X-Content-Type-Options", "nosniff".parse().unwrap());
            r.headers_mut()
                .insert("Referrer-Policy", "same-origin".parse().unwrap());
            r.headers_mut().insert("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'".parse().unwrap());
            r
        }
        Err(e) => e.into_response(),
    }
}
async fn guard_inner(app: &App, req: &mut Request) -> Result<Option<Response>> {
    let path = req.uri().path().to_owned();
    if path == "/healthz" {
        return Ok(None);
    }
    let issuer = app.cfg.get("CF_ACCESS_ISSUER").trim_end_matches('/');
    if !issuer.is_empty() {
        let token = req
            .headers()
            .get("Cf-Access-Jwt-Assertion")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        let claims = signed_claims(
            app,
            token,
            &format!("{issuer}/cdn-cgi/access/certs"),
            issuer,
            app.cfg.get("CF_ACCESS_AUD"),
        )
        .await
        .map_err(|_| {
            Error(
                StatusCode::FORBIDDEN,
                "Cloudflare Access authentication required".into(),
            )
        })?;
        if text(&claims["email"]).is_empty() {
            return Err(Error(
                StatusCode::FORBIDDEN,
                "Cloudflare identity required".into(),
            ));
        }
    }
    let supplied = req
        .headers()
        .get(header::COOKIE)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .split(';')
        .find_map(|p| {
            let (k, v) = p.trim().split_once('=')?;
            (k == app.cfg.cookie()).then_some(v)
        })
        .unwrap_or("");
    let data =
        sqlx::query_scalar::<_, String>("SELECT data FROM sessions WHERE id=? AND expires_at>?")
            .bind(supplied)
            .bind(chrono::Utc::now().timestamp())
            .fetch_optional(&app.db.0)
            .await?;
    let mut s = if let Some(data) = data {
        let mut s: Session = serde_json::from_str(&data).map_err(anyhow::Error::from)?;
        s.id = supplied.to_owned();
        s
    } else {
        Session {
            id: random(),
            csrf: random(),
            ..Default::default()
        }
    };
    let public = matches!(
        path.as_str(),
        "/auth/login" | "/oidc/login" | "/oidc/callback"
    );
    if app.cfg.oidc() && !public {
        if s.subject.is_empty() || s.token_expires <= chrono::Utc::now().timestamp() {
            if path.starts_with("/api/") || req.method() != axum::http::Method::GET {
                return Err(Error(
                    StatusCode::UNAUTHORIZED,
                    "authentication_required".into(),
                ));
            }
            s.return_to = safe_return(&req.uri().to_string());
            save(app, &s).await?;
            return Ok(Some(with_cookie(app, &s, Redirect::to("/oidc/login"))));
        }
        let p = userinfo(app, &s.access_token, &s.subject)
            .await
            .map_err(|_| Error(StatusCode::UNAUTHORIZED, "authentication_required".into()))?;
        s.role = text(&p["role"]);
        s.name = text(&p["name"]);
        if s.name.is_empty() {
            s.name = text(&p["email"]);
        }
    }
    if !matches!(
        *req.method(),
        axum::http::Method::GET | axum::http::Method::HEAD | axum::http::Method::OPTIONS
    ) {
        let token = req
            .headers()
            .get("X-CSRF-Token")
            .and_then(|h| h.to_str().ok())
            .unwrap_or("");
        if !equal(&s.csrf, token) {
            return Err(Error(StatusCode::FORBIDDEN, "Invalid CSRF token".into()));
        }
        if let Some(origin) = req
            .headers()
            .get(header::ORIGIN)
            .and_then(|h| h.to_str().ok())
            && !app.cfg.origin().is_empty()
            && origin != app.cfg.origin()
        {
            return Err(Error(
                StatusCode::FORBIDDEN,
                "Invalid request origin".into(),
            ));
        }
    }
    save(app, &s).await?;
    req.extensions_mut().insert(s);
    Ok(None)
}
#[derive(Default, Deserialize)]
pub struct Params {
    #[serde(default)]
    next: String,
    #[serde(default)]
    code: String,
    #[serde(default)]
    state: String,
}
pub async fn oidc_login(
    State(app): State<App>,
    Extension(mut s): Extension<Session>,
    Query(p): Query<Params>,
) -> Result<Response> {
    if !app.cfg.oidc() {
        return Err(Error::bad("OIDC is not configured"));
    }
    let m = metadata(&app).await?;
    if !p.next.is_empty() {
        s.return_to = safe_return(&p.next);
    }
    s.subject.clear();
    s.access_token.clear();
    s.role.clear();
    s.oauth_state = random();
    s.nonce = random();
    s.verifier = random();
    s.flow = "oidc".into();
    s.flow_expires = chrono::Utc::now().timestamp() + 600;
    rotate(&app, &mut s).await?;
    let mut u =
        url::Url::parse(&text(&m["authorization_endpoint"])).map_err(anyhow::Error::from)?;
    u.query_pairs_mut().extend_pairs([
        ("client_id", app.cfg.get("OIDC_CLIENT_ID")),
        (
            "redirect_uri",
            &format!("{}/oidc/callback", app.cfg.origin()),
        ),
        ("response_type", "code"),
        ("scope", "openid email profile"),
        ("state", &s.oauth_state),
        ("nonce", &s.nonce),
        (
            "code_challenge",
            &URL_SAFE_NO_PAD.encode(Sha256::digest(s.verifier.as_bytes())),
        ),
        ("code_challenge_method", "S256"),
    ]);
    Ok(with_cookie(&app, &s, Redirect::to(u.as_str())))
}
async fn consume(app: &App, s: &mut Session, p: &Params, flow: &str) -> Result<()> {
    let valid = s.flow == flow
        && s.flow_expires > chrono::Utc::now().timestamp()
        && equal(&s.oauth_state, &p.state)
        && !p.code.is_empty();
    s.oauth_state.clear();
    s.flow.clear();
    save(app, s).await?;
    if !valid {
        return Err(Error::bad(
            "Authorization expired or was declined. Please try again.",
        ));
    }
    Ok(())
}
pub async fn oidc_callback(
    State(app): State<App>,
    Extension(mut s): Extension<Session>,
    Query(p): Query<Params>,
) -> Result<Response> {
    consume(&app, &mut s, &p, "oidc").await?;
    let outcome: anyhow::Result<Value> = async {
        let m = metadata(&app).await?;
        let token: Value = app
            .http
            .post(text(&m["token_endpoint"]))
            .basic_auth(
                app.cfg.get("OIDC_CLIENT_ID"),
                Some(app.cfg.get("OIDC_CLIENT_SECRET")),
            )
            .form(&[
                ("grant_type", "authorization_code"),
                ("code", p.code.as_str()),
                (
                    "redirect_uri",
                    &format!("{}/oidc/callback", app.cfg.origin()),
                ),
                ("code_verifier", &s.verifier),
            ])
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        let c = signed_claims(
            &app,
            &text(&token["id_token"]),
            &text(&m["jwks_uri"]),
            app.cfg.get("OIDC_ISSUER").trim_end_matches('/'),
            app.cfg.get("OIDC_CLIENT_ID"),
        )
        .await?;
        anyhow::ensure!(equal(&s.nonce, &text(&c["nonce"])), "Nonce mismatch");
        if c.get("azp").is_some() || c["aud"].as_array().is_some_and(|a| a.len() > 1) {
            anyhow::ensure!(
                c["azp"].as_str() == Some(app.cfg.get("OIDC_CLIENT_ID")),
                "Authorized party mismatch"
            );
        }
        if let Some(hash) = c["at_hash"].as_str() {
            let digest = Sha256::digest(text(&token["access_token"]).as_bytes());
            anyhow::ensure!(
                equal(hash, &URL_SAFE_NO_PAD.encode(&digest[..16])),
                "Access token hash mismatch"
            );
        }
        let profile = userinfo(&app, &text(&token["access_token"]), &text(&c["sub"])).await?;
        s.subject = text(&c["sub"]);
        s.name = text(&profile["name"]);
        s.role = text(&profile["role"]);
        s.access_token = text(&token["access_token"]);
        s.token_expires =
            chrono::Utc::now().timestamp() + token["expires_in"].as_i64().unwrap_or(900);
        Ok(profile)
    }
    .await;
    outcome.map_err(|_| Error::bad("Sign-in could not be verified. Please try again."))?;
    s.verifier.clear();
    s.nonce.clear();
    rotate(&app, &mut s).await?;
    Ok(with_cookie(
        &app,
        &s,
        Redirect::to(&safe_return(&s.return_to)),
    ))
}
pub async fn feishu_login(
    State(app): State<App>,
    Extension(mut s): Extension<Session>,
    Query(p): Query<Params>,
) -> Result<Response> {
    s.return_to = safe_return(&p.next);
    if !app.cfg.live() {
        if !app.cfg.oidc() {
            s.subject = "demo".into();
            s.name = "Demo Driver".into();
            s.role = "admin".into();
        }
        provider::save_connection(
            &app,
            &s.subject,
            "ou_demo_user",
            &json!({"access_token":"mock","expires_at":i64::MAX}),
        )
        .await?;
        app.db
            .put_member(&Member {
                id: "ou_demo_user".into(),
                name: s.name.clone(),
                email: String::new(),
            })
            .await?;
        rotate(&app, &mut s).await?;
        return Ok(with_cookie(&app, &s, Redirect::to(&s.return_to)));
    }
    for key in ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_REDIRECT_URI"] {
        if app.cfg.get(key).is_empty() {
            return Err(Error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Feishu connection is not configured".into(),
            ));
        }
    }
    s.oauth_state = random();
    s.flow = "feishu".into();
    s.flow_expires = chrono::Utc::now().timestamp() + 600;
    save(&app, &s).await?;
    let mut u = url::Url::parse(&format!(
        "{}/open-apis/authen/v1/authorize",
        app.cfg
            .value("FEISHU_ACCOUNTS_URL", "https://accounts.feishu.cn")
            .trim_end_matches('/')
    ))
    .map_err(anyhow::Error::from)?;
    u.query_pairs_mut().extend_pairs([
        ("client_id", app.cfg.get("FEISHU_APP_ID")),
        ("redirect_uri", app.cfg.get("FEISHU_REDIRECT_URI")),
        ("response_type", "code"),
        ("state", s.oauth_state.as_str()),
        (
            "scope",
            app.cfg.value(
                "FEISHU_SCOPES",
                "auth:user.id:read task:task:read offline_access",
            ),
        ),
    ]);
    Ok(with_cookie(&app, &s, Redirect::to(u.as_str())))
}
pub async fn feishu_callback(
    State(app): State<App>,
    Extension(mut s): Extension<Session>,
    Query(p): Query<Params>,
) -> Result<Response> {
    consume(&app, &mut s, &p, "feishu").await?;
    let token = provider::exchange(&app, "authorization_code", &p.code)
        .await
        .map_err(|_| Error::bad("Feishu authorization failed"))?;
    let profile = provider::call(
        &app,
        "GET",
        "/authen/v1/user_info",
        &text(&token["access_token"]),
        None,
    )
    .await
    .map_err(|_| Error::bad("Feishu identity could not be verified"))?;
    let oid = text(&profile["open_id"]);
    if oid.is_empty() {
        return Err(Error::bad("Missing Feishu identity"));
    }
    if !app.cfg.oidc() {
        s.subject = format!("feishu:{oid}");
        s.name = text(&profile["name"]);
        let admins = app.cfg.list("FEISHU_ADMIN_OPEN_IDS");
        if admins.is_empty() {
            sqlx::query("INSERT OR IGNORE INTO settings(key,value) VALUES('first_admin',?)")
                .bind(&oid)
                .execute(&app.db.0)
                .await?;
        }
        s.role = if admins.contains(&oid)
            || (admins.is_empty() && app.db.setting("first_admin").await? == oid)
        {
            "admin"
        } else {
            "member"
        }
        .into();
    }
    provider::save_connection(&app, &s.subject, &oid, &token)
        .await
        .map_err(|_| {
            Error(
                StatusCode::CONFLICT,
                "This Feishu account is already linked to another account".into(),
            )
        })?;
    app.db
        .put_member(&Member {
            id: oid,
            name: text(&profile["name"]),
            email: text(&profile["email"]),
        })
        .await?;
    rotate(&app, &mut s).await?;
    Ok(with_cookie(
        &app,
        &s,
        Redirect::to(&safe_return(&s.return_to)),
    ))
}
pub async fn logout(State(app): State<App>, Extension(s): Extension<Session>) -> Result<Response> {
    sqlx::query("DELETE FROM sessions WHERE id=?")
        .bind(&s.id)
        .execute(&app.db.0)
        .await?;
    let mut r = Json(json!({"ok":true})).into_response();
    r.headers_mut().insert(
        header::SET_COOKIE,
        format!(
            "{}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{}",
            app.cfg.cookie(),
            if app.cfg.secure() { "; Secure" } else { "" }
        )
        .parse()
        .unwrap(),
    );
    Ok(r)
}
pub fn require_admin(s: &Session) -> Result<()> {
    if s.admin() {
        Ok(())
    } else {
        Err(Error::forbidden())
    }
}
pub async fn require_connection(app: &App, s: &Session) -> Result<String> {
    if s.subject.is_empty() {
        return Err(Error(
            StatusCode::UNAUTHORIZED,
            "authentication_required".into(),
        ));
    }
    provider::user_token(app, &s.subject).await.map_err(|_| {
        Error(
            StatusCode::PRECONDITION_REQUIRED,
            "feishu_connection_required".into(),
        )
    })
}

pub async fn login(
    state: State<App>,
    session: Extension<Session>,
    params: Query<Params>,
) -> Result<Response> {
    if state.0.cfg.oidc() {
        oidc_login(state, session, params).await
    } else {
        feishu_login(state, session, params).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn signed_identity_checks_signature_issuer_audience_and_expiry() {
        let keys: Value =
            serde_json::from_str(include_str!("../tests/fixtures/jwks.json")).unwrap();
        let router = axum::Router::new().route(
            "/jwks",
            axum::routing::get(move || async move { Json(keys) }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let uri = format!("http://{}/jwks", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
        let app = App::new(crate::config::Config(
            [("DATABASE_PATH".into(), ":memory:".into())].into(),
        ))
        .await
        .unwrap();
        let key = jsonwebtoken::EncodingKey::from_rsa_pem(include_bytes!(
            "../tests/fixtures/test-only.pem"
        ))
        .unwrap();
        let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
        header.kid = Some("test-key".into());
        let now = chrono::Utc::now().timestamp();
        let claims = json!({"sub":"user","iss":"https://issuer.test","aud":"larkai","iat":now,"exp":now+300});
        let token = jsonwebtoken::encode(&header, &claims, &key).unwrap();
        assert!(
            signed_claims(&app, &token, &uri, "https://issuer.test", "larkai")
                .await
                .is_ok()
        );
        assert!(
            signed_claims(&app, &token, &uri, "https://other.test", "larkai")
                .await
                .is_err()
        );
        assert!(
            signed_claims(&app, &token, &uri, "https://issuer.test", "wrong-app")
                .await
                .is_err()
        );
        let mut expired = claims.clone();
        expired["exp"] = json!(now - 300);
        let expired = jsonwebtoken::encode(&header, &expired, &key).unwrap();
        assert!(
            signed_claims(&app, &expired, &uri, "https://issuer.test", "larkai")
                .await
                .is_err()
        );
        let mut parts: Vec<String> = token.split('.').map(str::to_owned).collect();
        parts[1] = URL_SAFE_NO_PAD.encode(b"{\"sub\":\"attacker\"}");
        assert!(
            signed_claims(
                &app,
                &parts.join("."),
                &uri,
                "https://issuer.test",
                "larkai"
            )
            .await
            .is_err()
        );
        let hs = jsonwebtoken::encode(
            &jsonwebtoken::Header::default(),
            &claims,
            &jsonwebtoken::EncodingKey::from_secret(b"fake"),
        )
        .unwrap();
        assert!(
            signed_claims(&app, &hs, &uri, "https://issuer.test", "larkai")
                .await
                .is_err()
        );
        server.abort();
    }
}
