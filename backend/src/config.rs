use std::{collections::HashMap, env};

#[derive(Clone)]
pub struct Config(pub HashMap<String, String>);
impl Config {
    pub fn load() -> anyhow::Result<Self> {
        dotenvy::dotenv().ok();
        let cfg = Self(env::vars().collect());
        anyhow::ensure!(
            ["mock", "live"].contains(&cfg.mode()),
            "FEISHU_MODE must be mock or live"
        );
        if cfg.oidc() {
            for key in [
                "OIDC_ISSUER",
                "OIDC_CLIENT_ID",
                "OIDC_CLIENT_SECRET",
                "PUBLIC_ORIGIN",
            ] {
                anyhow::ensure!(!cfg.get(key).is_empty(), "{key} is required for OIDC");
            }
            for key in ["OIDC_ISSUER", "PUBLIC_ORIGIN"] {
                let u = url::Url::parse(cfg.get(key))?;
                anyhow::ensure!(
                    u.scheme() == "https"
                        && u.host_str().is_some()
                        && u.username().is_empty()
                        && u.password().is_none()
                        && u.query().is_none()
                        && u.fragment().is_none(),
                    "{key} must be an HTTPS URL"
                );
                if key == "PUBLIC_ORIGIN" {
                    anyhow::ensure!(u.path() == "/", "PUBLIC_ORIGIN must have no path");
                }
            }
        }
        if !cfg.get("CF_ACCESS_ISSUER").is_empty() || !cfg.get("CF_ACCESS_AUD").is_empty() {
            let u = url::Url::parse(cfg.get("CF_ACCESS_ISSUER"))?;
            anyhow::ensure!(
                u.scheme() == "https"
                    && u.host_str()
                        .is_some_and(|h| h.ends_with(".cloudflareaccess.com"))
                    && u.path() == "/"
                    && u.query().is_none()
                    && u.fragment().is_none()
                    && u.username().is_empty()
                    && u.password().is_none()
                    && !cfg.get("CF_ACCESS_AUD").is_empty(),
                "Invalid Cloudflare Access configuration"
            );
        }
        Ok(cfg)
    }
    pub fn get(&self, key: &str) -> &str {
        self.0.get(key).map(String::as_str).unwrap_or("")
    }
    pub fn value<'a>(&'a self, key: &str, default: &'a str) -> &'a str {
        let v = self.get(key);
        if v.is_empty() { default } else { v }
    }
    pub fn flag(&self, key: &str, default: bool) -> bool {
        match self.get(key) {
            "" => default,
            "1" | "true" | "yes" | "on" => true,
            _ => false,
        }
    }
    pub fn number(&self, key: &str, default: u64) -> u64 {
        self.get(key).parse().unwrap_or(default)
    }
    pub fn list(&self, key: &str) -> Vec<String> {
        self.get(key)
            .split(|c: char| c == ',' || c.is_whitespace())
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .collect()
    }
    pub fn mode(&self) -> &str {
        self.value("FEISHU_MODE", "mock")
    }
    pub fn live(&self) -> bool {
        self.mode() == "live"
    }
    pub fn oidc(&self) -> bool {
        ["OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]
            .iter()
            .any(|k| !self.get(k).is_empty())
    }
    pub fn origin(&self) -> &str {
        self.get("PUBLIC_ORIGIN").trim_end_matches('/')
    }
    pub fn secure(&self) -> bool {
        self.origin().starts_with("https://") || !self.get("CF_ACCESS_ISSUER").is_empty()
    }
    pub fn cookie(&self) -> &str {
        if self.secure() {
            "__Host-larkai"
        } else {
            "larkai"
        }
    }
}
