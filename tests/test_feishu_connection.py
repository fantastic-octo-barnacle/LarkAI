"""The feature gate must not conflate site login with upstream authorization."""
import time
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from test_oidc import OIDCFixture, ORIGIN
from rmtask.storage.db import DB
from rmtask.storage.models import TokenRecord, UserRecord
from rmtask.web.feishu_connection import safe_return


class FeishuConnectionTests(OIDCFixture):
    def connect(self, expires=None, refresh=''):
        db = DB(self.tmp.name+'/db')
        db.upsert_user(UserRecord(open_id='ou_connected', name='Feishu Name'))
        db.save_token(TokenRecord(open_id='ou_connected', access_token='feishu-private',
                                 expires_at=expires or int(time.time()+3600), refresh_token=refresh))
        db.link_feishu(self.subject, 'ou_connected')
        return db

    def test_dashboard_shows_herkules_name_without_feishu_prompt(self):
        self.login()
        page = self.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="user-chip">Member</span>', page.data)
        self.assertNotIn(b'member@example.com', page.data)
        self.assertNotIn(b'Connect Feishu', page.data)
        self.connect()
        self.assertNotIn(b'Feishu Name', self.get('/').data)

    def test_tasks_requires_connection_without_calling_provider(self):
        self.login()
        with patch('rmtask.providers.LiveProvider.task_create_options') as options:
            response = self.get('/tasks?group=division')
        self.assertEqual(response.status_code, 403)
        self.assertIn(b'Connect Feishu to use this feature', response.data)
        options.assert_not_called()
        self.assertEqual(self.get('/').status_code, 200)

    def test_connected_tasks_and_expired_token_gate(self):
        self.login()
        self.connect()
        with patch('rmtask.providers.LiveProvider.task_create_options', return_value={}):
            self.assertEqual(self.get('/tasks').status_code, 200)
        self.connect(expires=1)
        self.assertEqual(self.get('/tasks').status_code, 403)

    def test_expired_token_refreshes_before_opening_tasks(self):
        self.login()
        self.connect(expires=1, refresh='refresh')
        with patch('rmtask.api.auth.AuthManager.refresh_user_token', return_value={
            'access_token':'refreshed', 'expires_in':7200}), \
             patch('rmtask.providers.LiveProvider.task_create_options', return_value={}):
            self.assertEqual(self.get('/tasks').status_code, 200)

    def test_failed_refresh_blocks_actions_without_tenant_fallback(self):
        self.login()
        self.connect(expires=1, refresh='refresh')
        with self.client.session_transaction(base_url=ORIGIN) as s:
            csrf = s['csrf_token']
        with patch('rmtask.api.auth.AuthManager.refresh_user_token', side_effect=RuntimeError('revoked')), \
             patch('rmtask.providers.LiveProvider.create_task') as create:
            response = self.client.post('/tasks/new', base_url=ORIGIN, data={'csrf_token':csrf,'title':'Do not create'})
        self.assertEqual(response.status_code, 403)
        create.assert_not_called()

    def test_feishu_callback_returns_to_tasks_and_preserves_herkules_session(self):
        self.login()
        cfg = self.app.config['SETTINGS']
        cfg.app_id = 'app'; cfg.app_secret = 'secret'; cfg.redirect_uri = ORIGIN+'/oauth/callback'
        start = self.get('/login?next=/tasks?group=division')
        state = parse_qs(urlparse(start.location).query)['state'][0]
        with patch('rmtask.api.auth.AuthManager.exchange_code', return_value={'access_token':'feishu-private','expires_in':7200}), \
             patch('rmtask.api.auth.AuthManager.user_info', return_value={'open_id':'ou_new','name':'Feishu Name'}):
            result = self.get('/oauth/callback?code=valid&state='+state)
        self.assertEqual(result.location, '/tasks?group=division')
        self.assertEqual(DB(cfg.db_path).linked_feishu_id(self.subject), 'ou_new')
        self.assertIn(b'class="user-chip">Member</span>', self.get('/').data)
        self.assertEqual(self.get('/oauth/callback?code=valid&state='+state).status_code, 400)

    def test_declining_feishu_keeps_dashboard_access(self):
        self.login()
        with self.client.session_transaction(base_url=ORIGIN) as s:
            s['oauth_state'] = 'declined'; s['feishu_return_to'] = '/tasks'
        result = self.get('/oauth/callback?error=access_denied&state=declined')
        self.assertEqual(result.status_code, 400)
        self.assertIn(b'Feishu access was not granted', result.data)
        self.assertEqual(self.get('/').status_code, 200)

    def test_return_urls_are_local_read_only_pages(self):
        for value in ['https://evil.example/', '//evil.example/', '/\\evil.example', '/oauth/callback?code=bad', '/tasks/new', '/tasks\n']:
            with self.subTest(value=value):
                self.assertEqual(safe_return(value), '/tasks')
        self.assertEqual(safe_return('/tasks?status=pending'), '/tasks?status=pending')

    def test_herkules_signin_preserves_tasks_destination(self):
        self.assertEqual(self.get('/tasks').location, '/oidc/login')
        self.assertEqual(self.login().location, '/tasks')
