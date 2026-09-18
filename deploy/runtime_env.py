"""Build a private dotenv overlay from GitHub's combined or individual secrets."""
import os
from pathlib import Path

KEYS = (
    'FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_REDIRECT_URI',
    'FEISHU_WIKI_NODE_TOKEN', 'FEISHU_BITABLE_APP_TOKEN',
    'FEISHU_BITABLE_SUBMIT_TABLE_ID', 'FEISHU_BITABLE_TASKS_TABLE_ID',
    'FEISHU_ADMIN_OPEN_IDS', 'FEISHU_SCOPES',
    'OIDC_ISSUER', 'OIDC_CLIENT_ID', 'OIDC_CLIENT_SECRET', 'PUBLIC_ORIGIN',
)


def render(environ):
    lines = [environ.get('LARKAI_ENV', '').rstrip()]
    for key in KEYS:
        value = environ.get(key, '').strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
            value = value[1:-1].strip()
        if value:
            if any(c in value for c in "\r\n'"):
                raise ValueError(f'{key} must be a single-line value without single quotes')
            lines.append(f"{key}='{value}'")
    return '\n'.join(lines).strip() + '\n' if any(lines) else ''


if __name__ == '__main__':
    target = Path('runtime.env')
    target.write_text(render(os.environ))
    target.chmod(0o600)
