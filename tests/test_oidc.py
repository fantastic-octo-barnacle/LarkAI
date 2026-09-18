import base64
import hashlib
import json
import os
import tempfile
import time
import unittest
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from authlib.integrations.base_client.errors import OAuthError
from rmtask.config import Settings
from rmtask.web.app import create_app
from rmtask.storage.db import DB
from rmtask.storage.models import UserRecord

ISSUER = 'https://identity.example/auth'
ORIGIN = 'https://dashboard.example'


class OIDCTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'OIDC_ISSUER': ISSUER, 'OIDC_CLIENT_ID': 'larkai',
            'OIDC_CLIENT_SECRET': 's'*40, 'PUBLIC_ORIGIN': ORIGIN,
            'CF_ACCESS_ISSUER': '', 'CF_ACCESS_AUD': ''})
        self.env.start()
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.role = 'member'
        self.subject = 'herkules-user'
        self.expired = False
        self.bad_nonce = False
        self.bad_issuer = False
        self.bad_audience = False
        self.bad_signature = False
        self.token_calls = 0
        self.app = create_app(Settings(mode='live', db_path=self.tmp.name+'/db', secret_key='k'*40))
        self.client = self.app.test_client()
        self.http = patch('requests.sessions.Session.request', side_effect=self.transport)
        self.mock_http = self.http.start()

    def tearDown(self):
        self.http.stop()
        self.env.stop()
        self.tmp.cleanup()

    def transport(self, method, url, **kwargs):
        if url.endswith('/.well-known/openid-configuration'):
            payload = dict(issuer=ISSUER, authorization_endpoint=ISSUER+'/authorize',
                           token_endpoint=ISSUER+'/token', userinfo_endpoint=ISSUER+'/userinfo',
                           jwks_uri=ISSUER+'/jwks', id_token_signing_alg_values_supported=['ES256'])
        elif url.endswith('/jwks'):
            key = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
            key.update(kid='test', use='sig', alg='ES256')
            payload = {'keys': [key]}
        elif url.endswith('/token'):
            self.token_calls += 1
            now = int(time.time())
            claims = dict(iss=ISSUER if not self.bad_issuer else 'https://wrong.example',
                          sub=self.subject, aud='wrong' if self.bad_audience else 'larkai',
                          iat=now-120, exp=now-360 if self.expired else now+900,
                          nonce='wrong' if self.bad_nonce else self.nonce)
            signing = ec.generate_private_key(ec.SECP256R1()) if self.bad_signature else self.key
            payload = dict(access_token='private-access-token', token_type='Bearer', expires_in=900,
                           id_token=jwt.encode(claims, signing, algorithm='ES256', headers={'kid':'test'}))
        elif url.endswith('/userinfo'):
            payload = dict(sub=self.subject, role=self.role, name='Member', email='member@example.com')
        else:
            raise AssertionError('Unexpected request: '+url)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        response.headers['Content-Type'] = 'application/json'
        response.url = url
        return response

    def get(self, path, **kw):
        return self.client.get(path, base_url=ORIGIN, **kw)

    def start(self):
        result = self.get('/oidc/login')
        self.assertEqual(result.status_code, 302)
        args = parse_qs(urlparse(result.location).query)
        self.nonce = args['nonce'][0]
        self.state = args['state'][0]
        self.assertEqual(args['code_challenge_method'], ['S256'])
        self.assertEqual(args['redirect_uri'], [ORIGIN+'/oidc/callback'])
        return args

    def login(self):
        self.start()
        return self.get('/oidc/callback?code=valid&state='+self.state)

    def test_anonymous_pages_redirect_and_api_and_posts_are_denied(self):
        self.assertEqual(self.get('/').location, '/oidc/login')
        self.assertEqual(self.get('/api/stats.json').status_code, 401)
        self.assertEqual(self.client.post('/settings', base_url=ORIGIN).status_code, 401)
        self.assertEqual(self.get('/healthz').status_code, 200)

    def test_real_signed_callback_pkce_and_server_side_token(self):
        result = self.login()
        self.assertEqual(result.status_code, 302)
        cookie = result.headers['Set-Cookie']
        self.assertIn('Secure', cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertNotIn('private-access-token', cookie)
        self.assertEqual(self.get('/').status_code, 200)
        self.assertEqual(self.get('/settings').status_code, 403)

    def test_missing_or_wrong_state_and_replayed_callback(self):
        self.start()
        self.assertEqual(self.get('/oidc/callback?code=valid&state=wrong').status_code, 400)
        self.assertEqual(self.token_calls, 0)
        result = self.get('/oidc/callback?code=valid&state='+self.state)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.get('/oidc/callback?code=valid&state='+self.state).status_code, 400)

    def test_invalid_id_tokens_are_rejected(self):
        for field in ['bad_nonce','bad_issuer','bad_audience','bad_signature','expired']:
            with self.subTest(field=field):
                setattr(self, field, True)
                self.assertEqual(self.login().status_code, 400)
                setattr(self, field, False)

    def test_admin_role_is_live_and_ignores_feishu_admin_flag(self):
        self.role = 'admin'
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.get('/settings').status_code, 200)
        db = DB(self.tmp.name+'/db')
        db.upsert_user(UserRecord(open_id='ou_local_admin', is_admin=True))
        db.link_feishu(self.subject, 'ou_local_admin')
        self.role = 'member'
        self.assertEqual(self.get('/settings').status_code, 403)
        self.assertNotIn(b'>Diagnostics<', self.get('/').data)

    def test_subject_mismatch_and_missing_role_fail_closed(self):
        self.assertEqual(self.login().status_code, 302)
        self.subject = 'other-user'
        self.assertEqual(self.get('/').status_code, 403)
        self.subject = 'herkules-user'
        self.role = ''
        self.assertEqual(self.login().status_code, 403)

    def test_issuer_unavailable_does_not_keep_cached_admin(self):
        self.role = 'admin'
        self.login()
        self.mock_http.side_effect = requests.ConnectionError('unavailable')
        self.assertEqual(self.get('/settings').status_code, 503)

    def test_csrf_required_and_logout_clears_session(self):
        self.login()
        self.assertEqual(self.client.post('/oidc/logout', base_url=ORIGIN).status_code, 400)
        # Server-side session cookie is Secure, so use HTTPS for the transaction.
        with self.client.session_transaction(base_url=ORIGIN) as session:
            csrf = session['csrf_token']
        self.assertEqual(self.client.post('/oidc/logout', base_url=ORIGIN,
                                         data={'csrf_token':csrf}).status_code, 302)
        self.assertEqual(self.get('/').location, '/oidc/login')

    def test_link_cannot_be_taken_by_another_subject(self):
        db = DB(self.tmp.name+'/db'); db.init()
        db.link_feishu('one', 'ou_feishu')
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            db.link_feishu('two', 'ou_feishu')

    def test_disabled_account_response_clears_login(self):
        self.login()
        response = requests.Response(); response.status_code = 401
        self.mock_http.side_effect = requests.HTTPError(response=response)
        self.assertEqual(self.get('/').location, '/oidc/login')

    def test_expired_session_requires_new_authorization(self):
        self.login()
        with self.client.session_transaction(base_url=ORIGIN) as session:
            saved = session['herkules']
            saved['token']['expires_at'] = 1
            session['herkules'] = saved
        self.assertEqual(self.get('/').location, '/oidc/login')

    def test_admin_forms_have_csrf_fields(self):
        self.role = 'admin'; self.login()
        page = self.get('/settings')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="csrf_token"', page.data)
