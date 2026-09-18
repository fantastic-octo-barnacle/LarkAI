import unittest
from deploy.merge_env import merge


class EnvironmentMergeTests(unittest.TestCase):
    def test_partial_secret_preserves_origin_verification_and_database_path(self):
        merged = merge('CF_ACCESS_AUD=aud\nDATABASE_PATH=/app/data/larkai.sqlite3\nFEISHU_APP_ID=old\n',
                       '# Updated connection\nFEISHU_APP_ID=cli_new\nFEISHU_APP_SECRET="secret=value"\n')
        self.assertIn('CF_ACCESS_AUD=aud\n', merged)
        self.assertIn('DATABASE_PATH=/app/data/larkai.sqlite3\n', merged)
        self.assertIn('FEISHU_APP_SECRET="secret=value"\n', merged)
        self.assertNotIn('FEISHU_APP_ID=old', merged)

    def test_explicit_empty_value_clears_setting(self):
        self.assertEqual(merge('FEISHU_WIKI_NODE_TOKEN=old\n', 'FEISHU_WIKI_NODE_TOKEN=\n'),
                         'FEISHU_WIKI_NODE_TOKEN=\n')

    def test_invalid_secret_fails_instead_of_silently_dropping_settings(self):
        with self.assertRaises(ValueError):
            merge('', 'FEISHU_APP_ID')


class IndividualSecretTests(unittest.TestCase):
    def test_individual_secrets_override_combined_and_preserve_literals(self):
        from deploy.runtime_env import render
        result = render({'LARKAI_ENV': 'FEISHU_APP_ID=old', 'FEISHU_APP_ID': 'cli_new',
                         'FEISHU_APP_SECRET': 'dollar$hash#equals='})
        merged = merge('', result)
        self.assertIn("FEISHU_APP_ID='cli_new'", merged)
        self.assertIn("FEISHU_APP_SECRET='dollar$hash#equals='", merged)
        self.assertNotIn('FEISHU_ADMIN_OPEN_IDS', merged)

    def test_empty_secrets_preserve_server_configuration(self):
        from deploy.runtime_env import render
        self.assertEqual(render({'FEISHU_APP_ID': ''}), '')

    def test_newlines_cannot_inject_other_settings(self):
        from deploy.runtime_env import render
        with self.assertRaises(ValueError):
            render({'FEISHU_APP_SECRET': 'value\nCF_ACCESS_AUD='})

    def test_pasted_values_can_have_surrounding_quotes_and_newlines(self):
        from deploy.runtime_env import render
        self.assertEqual(render({'FEISHU_APP_ID': ' \n"cli_test"\n'}), "FEISHU_APP_ID='cli_test'\n")
