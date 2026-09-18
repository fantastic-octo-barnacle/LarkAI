import unittest
from deploy.merge_env import merge


class EnvironmentMergeTests(unittest.TestCase):
    def test_partial_secret_preserves_origin_verification_and_flask_secret(self):
        merged = merge('CF_ACCESS_AUD=aud\nFLASK_SECRET_KEY=stable\nFEISHU_APP_ID=old\n',
                       '# Updated connection\nFEISHU_APP_ID=cli_new\nFEISHU_APP_SECRET="secret=value"\n')
        self.assertIn('CF_ACCESS_AUD=aud\n', merged)
        self.assertIn('FLASK_SECRET_KEY=stable\n', merged)
        self.assertIn('FEISHU_APP_SECRET="secret=value"\n', merged)
        self.assertNotIn('FEISHU_APP_ID=old', merged)

    def test_explicit_empty_value_clears_setting(self):
        self.assertEqual(merge('FEISHU_WIKI_NODE_TOKEN=old\n', 'FEISHU_WIKI_NODE_TOKEN=\n'),
                         'FEISHU_WIKI_NODE_TOKEN=\n')

    def test_invalid_secret_fails_instead_of_silently_dropping_settings(self):
        with self.assertRaises(ValueError):
            merge('', 'FEISHU_APP_ID')
