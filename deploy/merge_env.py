"""Merge a partial dotenv secret without discarding server-owned settings."""
import re
import sys
from pathlib import Path


def merge(existing: str, incoming: str) -> str:
    values = {}
    for text in (existing, incoming):
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            key = key.strip()
            if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError('Expected one KEY=value setting per line')
            values[key] = value
    return ''.join(f'{key}={value}\n' for key, value in values.items())


if __name__ == '__main__':
    existing, incoming, output = map(Path, sys.argv[1:])
    output.write_text(merge(existing.read_text() if existing.exists() else '', incoming.read_text()))
    output.chmod(0o600)
