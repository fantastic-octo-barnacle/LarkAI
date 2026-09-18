"""Validate Cloudflare Access at the origin; never trust identity headers alone."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import jwt
from flask import Flask, g, request


def configure_access(app: Flask) -> None:
    issuer = os.environ.get("CF_ACCESS_ISSUER", "").rstrip("/")
    audience = os.environ.get("CF_ACCESS_AUD", "")
    if not issuer and not audience:
        return  # Local development / deployments using native Feishu login.
    parsed = urlparse(issuer)
    if (not audience or parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".cloudflareaccess.com")
            or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port):
        raise ValueError("Set CF_ACCESS_ISSUER to the HTTPS team domain and CF_ACCESS_AUD to the application audience")
    client = jwt.PyJWKClient(issuer + "/cdn-cgi/access/certs", timeout=10)
    app.extensions["cloudflare_jwks"] = client
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax")

    @app.before_request
    def authenticate_access():
        if request.path == "/healthz":
            return None
        token = request.headers.get("Cf-Access-Jwt-Assertion", "")
        if not token:
            return "Cloudflare Access authentication required", 403
        try:
            key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=audience,
                                issuer=issuer, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
            if not claims.get("sub") or not claims.get("email"):
                return "Cloudflare Access user identity required", 403
        except jwt.PyJWTError:
            return "Invalid Cloudflare Access authentication", 403
        g.access_identity = claims

    @app.context_processor
    def access_identity():
        return {"access_identity": g.get("access_identity")}
