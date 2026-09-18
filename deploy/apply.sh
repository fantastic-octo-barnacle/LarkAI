#!/usr/bin/env bash
# Run on the VPS from ~/larkai, after staging incoming/{compose.yml,image.env}.
set -eu
cd "$(dirname "$0")"
umask 077
exec 9>.deploy.lock
flock -w 300 9
mkdir -p backups
rm -f backups/env.previous
env_changed=false
had_env=false
if [ -f .env ]; then
  had_env=true
  cp .env backups/env.previous
fi
previous=false
activated=false
finish() {
  status=$?
  trap - EXIT
  rm -f incoming/runtime.env
  if [ "$status" -ne 0 ]; then
    if [ "$env_changed" = true ]; then
      if [ "$had_env" = true ]; then cp backups/env.previous .env; else rm -f .env; fi
    fi
    if [ "$activated" = true ]; then
      if [ "$previous" = true ]; then
        cp backups/compose.previous.yml compose.yml
        cp backups/image.previous.env image.env
        compose image.env compose.yml up -d --wait --wait-timeout 120 || true
      else
        compose image.env compose.yml down || true
      fi
    fi
  fi
  exit "$status"
}
trap finish EXIT
if [ -s incoming/runtime.env ]; then
  cp incoming/runtime.env .env.new
  chmod 600 .env.new
  mv .env.new .env
  env_changed=true
fi
[ -s .env ] || { echo 'Provision .env or the production LARKAI_ENV secret first' >&2; exit 1; }
# Only digest references are accepted; tags are build outputs, never deployment inputs.
grep -Eq '^LARKAI_IMAGE=ghcr.io/fantastic-octo-barnacle/larkai@sha256:[a-f0-9]{64}$' incoming/image.env
compose() { docker compose --project-directory "$PWD" --env-file .env --env-file "$1" -f "$2" "${@:3}"; }

compose incoming/image.env incoming/compose.yml config --quiet
compose incoming/image.env incoming/compose.yml pull
previous=false
if [ -f compose.yml ] && [ -f image.env ]; then
  previous=true
  cp compose.yml backups/compose.previous.yml
  cp image.env backups/image.previous.env
  # SQLite's backup API gives a consistent snapshot even with WAL enabled.
  compose image.env compose.yml exec -T web python -c 'import sqlite3; s=sqlite3.connect("/app/data/rmtask.db"); d=sqlite3.connect("/app/data/pre-deploy.db"); s.backup(d); d.close(); s.close()'
  cid=$(compose image.env compose.yml ps -q web)
  docker cp "$cid:/app/data/pre-deploy.db" "backups/rmtask-$(date -u +%Y%m%dT%H%M%SZ).db"
fi
cp incoming/compose.yml compose.yml
cp incoming/image.env image.env
activated=true
if ! compose image.env compose.yml up -d --wait --wait-timeout 120; then
  echo 'LarkAI startup failed; restoring the previous image and configuration' >&2
  exit 1
fi
compose image.env compose.yml ps
