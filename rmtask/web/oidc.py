"""Herkules OIDC login; provider-owned roles and server-side browser sessions."""
from __future__ import annotations

import os
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from cachelib.file import FileSystemCache
from flask import Blueprint, abort, g, jsonify, redirect, request, session
from flask_session import Session
from joserfc.errors import JoseError

from rmtask.storage.db import DB
from rmtask.web.feishu_connection import safe_return


def configure_oidc(app, cfg):
    issuer = os.getenv('OIDC_ISSUER', '').rstrip('/')
    client_id = os.getenv('OIDC_CLIENT_ID', '')
    client_secret = os.getenv('OIDC_CLIENT_SECRET', '')
    origin = os.getenv('PUBLIC_ORIGIN', '').rstrip('/')
    if not any((issuer, client_id, client_secret)):
        return
    if not all((issuer, client_id, client_secret, origin)):
        raise ValueError('OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET and PUBLIC_ORIGIN are required')
    for value in (issuer, origin):
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('OIDC issuer and public origin must be HTTPS URLs')
    if urlparse(origin).path:
        raise ValueError('PUBLIC_ORIGIN must have no path')
    if len(cfg.secret_key) < 32:
        raise ValueError('OIDC requires a stable FLASK_SECRET_KEY of at least 32 characters')
    directory = Path(cfg.db_path).parent / 'sessions'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    app.config.update(OIDC_ENABLED=True, PUBLIC_ORIGIN=origin,
                      SESSION_TYPE='cachelib', SESSION_CACHELIB=FileSystemCache(str(directory), mode=0o600),
                      SESSION_COOKIE_NAME='__Host-larkai', SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_PATH='/', PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    Session(app)
    oauth = OAuth(app)
    client = oauth.register('herkules', client_id=client_id, client_secret=client_secret,
                           server_metadata_url=issuer+'/.well-known/openid-configuration',
                           client_kwargs={'scope': 'openid email profile',
                                          'code_challenge_method': 'S256',
                                          'token_endpoint_auth_method': 'client_secret_basic',
                                          'default_timeout': 10})
    app.extensions['herkules_oidc'] = client
    bp = Blueprint('oidc', __name__)

    def start_login():
        if request.path.startswith('/api/') or request.method not in ('GET', 'HEAD'):
            return jsonify(error='authentication_required'), 401
        session['oidc_return_to'] = safe_return(request.full_path.rstrip('?'), '/')
        return redirect('/oidc/login')

    @app.before_request
    def authenticate():
        if request.endpoint in ('oidc.login', 'oidc.callback', 'healthz'):
            return None
        saved = session.get('herkules')
        if not saved or saved['token'].get('expires_at', 0) <= time.time():
            session.pop('herkules', None)
            session.pop('open_id', None)
            return start_login()
        try:
            # A live response reflects admin demotions and disabled accounts immediately.
            profile = dict(client.userinfo(token=saved['token'], timeout=10))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (400, 401, 403):
                session.clear()
                return start_login()
            return 'Identity service unavailable', 503
        except (requests.RequestException, OAuthError, ValueError):
            return 'Identity service unavailable', 503
        if profile.get('sub') != saved['sub'] or profile.get('role') not in ('admin', 'member'):
            session.clear()
            return 'Invalid Herkules identity', 403
        g.identity = profile
        db = DB(cfg.db_path)
        db.init()
        linked = db.linked_feishu_id(profile['sub'])
        if linked:
            session['open_id'] = linked
        else:
            session.pop('open_id', None)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            supplied = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
            expected = session.get('csrf_token', '')
            if not expected or not secrets.compare_digest(supplied, expected):
                abort(400, 'Invalid CSRF token')
        if request.endpoint == 'main.settings_page' and profile['role'] != 'admin':
            abort(403)

    @bp.get('/oidc/login')
    def login():
        target = safe_return(session.get('oidc_return_to'), '/')
        session.clear()
        session['oidc_return_to'] = target
        app.session_interface.regenerate(session)
        try:
            return client.authorize_redirect(origin+'/oidc/callback')
        except (requests.RequestException, OAuthError, ValueError):
            return 'Identity service unavailable', 503

    @bp.get('/oidc/callback')
    def callback():
        try:
            token = client.authorize_access_token(timeout=10)
            identity = token.get('userinfo', {})  # Authlib validates signed ID token, nonce and state.
            if not identity.get('sub') or identity.get('iss') != issuer:
                abort(400, 'Invalid ID token')
            profile = dict(client.userinfo(token=token, timeout=10))
            if profile.get('sub') != identity['sub'] or profile.get('role') not in ('admin', 'member'):
                abort(403, 'Invalid Herkules identity')
        except (OAuthError, JoseError, requests.RequestException, ValueError):
            return 'Sign-in could not be verified. Please try again.', 400
        target = safe_return(session.get('oidc_return_to'), '/')
        session.clear()
        session['herkules'] = {'sub': identity['sub'], 'token': {
            'access_token': token['access_token'], 'token_type': token.get('token_type', 'Bearer'),
            'expires_at': token.get('expires_at', time.time()+int(token.get('expires_in', 900)))}}
        session['csrf_token'] = secrets.token_urlsafe(32)
        app.session_interface.regenerate(session)
        return redirect(target)

    @bp.post('/oidc/logout')
    def logout():
        session.clear()
        return redirect('/oidc/login')

    @app.context_processor
    def context():
        return {'identity': g.get('identity'), 'oidc_enabled': True,
                'csrf_token': session.get('csrf_token', '')}

    app.register_blueprint(bp)
