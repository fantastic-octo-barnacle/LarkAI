"""Cloudflare origin checks use signed tokens, including invalid signatures/claims."""
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from rmtask.config import Settings
from rmtask.web.app import create_app

ISSUER = 'https://test.cloudflareaccess.com'


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CF_ACCESS_ISSUER': ISSUER, 'CF_ACCESS_AUD': 'dashboard'})
        self.env.start()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.app = create_app(Settings(db_path=self.tmp.name + '/test.db', mock_data_dir=self.tmp.name, secret_key='test'))
        self.client = self.app.test_client()
        self.jwks = patch.object(self.app.extensions['cloudflare_jwks'], 'get_signing_key_from_jwt',
                                 return_value=SimpleNamespace(key=self.key.public_key()))
        self.jwks.start()

    def tearDown(self):
        self.jwks.stop()
        self.env.stop()
        self.tmp.cleanup()

    def token(self, **overrides):
        claims = dict(iss=ISSUER, aud=['dashboard'], sub='user-1', email='member@example.com',
                      iat=int(time.time()), exp=int(time.time()) + 60)
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test'})

    def test_missing_or_forged_identity_cannot_read_pages_api_or_assets(self):
        for path in ['/', '/api/stats.json', '/static/style.css', '/login', '/oauth/callback']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers={
                    'Cf-Access-Authenticated-User-Email': 'fake@example.com'}).status_code, 403)
        self.assertEqual(self.client.post('/settings').status_code, 403)

    def test_signed_identity_is_shown_without_granting_feishu_admin(self):
        response = self.client.get('/', headers={'Cf-Access-Jwt-Assertion': self.token()})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'member@example.com', response.data)
        self.assertIn(b'Connect Feishu', response.data)
        self.assertNotIn(b'>Diagnostics<', response.data)

    def test_wrong_audience_issuer_expiry_and_missing_identity_are_rejected(self):
        for claims in [{'aud': 'other'}, {'iss': 'https://other.cloudflareaccess.com'},
                       {'exp': 1}, {'email': ''}, {'sub': ''}]:
            with self.subTest(claims=claims):
                self.assertEqual(self.client.get('/', headers={
                    'Cf-Access-Jwt-Assertion': self.token(**claims)}).status_code, 403)

    def test_invalid_signature_is_rejected(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode({'sub': 'fake'}, other, algorithm='RS256')
        self.assertEqual(self.client.get('/', headers={'Cf-Access-Jwt-Assertion': token}).status_code, 403)

    def test_partial_configuration_fails_startup(self):
        with patch.dict(os.environ, {'CF_ACCESS_AUD': ''}):
            with self.assertRaises(ValueError):
                create_app(Settings())
