#!/usr/bin/env bash
set -euo pipefail

# Updates only the Integrix API. It never starts, stops, recreates, or reloads
# Caddy, PostgreSQL, Alloy, or another Compose project.

readonly repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ops_root="${INTEGRIX_OPS_ROOT:-/opt/integrix-ops}"
readonly env_file="${INTEGRIX_ENV_FILE:-.env.production}"
readonly app_image="${APP_IMAGE:-integrixai-app}"
readonly health_attempts="${INTEGRIX_HEALTH_ATTEMPTS:-20}"

usage() {
  printf 'Usage: %s --release-ref <verified-git-ref> [--allow-caddy-drift]\n' "$0" >&2
}

release_ref=""
allow_caddy_drift=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-ref)
      release_ref="${2:-}"
      shift 2
      ;;
    --allow-caddy-drift)
      allow_caddy_drift=true
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${release_ref}" ]]; then
  usage
  exit 2
fi

cd "${repo_root}"
if [[ ! -f "${env_file}" ]]; then
  printf 'Missing environment file: %s\n' "${env_file}" >&2
  exit 1
fi

git rev-parse --verify --quiet "${release_ref}^{commit}" >/dev/null || {
  printf 'Unknown release ref: %s\n' "${release_ref}" >&2
  exit 1
}
git merge-base --is-ancestor HEAD "${release_ref}" || {
  printf 'Release is not a fast-forward from the deployed commit.\n' >&2
  exit 1
}

if ! git diff --quiet HEAD.."${release_ref}" -- deploy/Caddyfile; then
  printf 'Release changes deploy/Caddyfile; use a dedicated Caddy rollout instead.\n' >&2
  exit 1
fi

if ! git diff --quiet -- deploy/Caddyfile || [[ -e deploy/Caddyfile.bak ]]; then
  if [[ "${allow_caddy_drift}" != true ]]; then
    printf 'Local Caddy configuration drift detected; rerun only after confirming --allow-caddy-drift.\n' >&2
    exit 1
  fi
fi

unexpected_changes="$({ git status --porcelain; } | awk '
  $0 ~ /^.. deploy\/Caddyfile$/ { next }
  $0 ~ /^\?\? deploy\/Caddyfile\.bak-/ { next }
  { print }
')"
if [[ -n "${unexpected_changes}" ]]; then
  printf 'Refusing rollout with unexpected worktree changes:\n%s\n' "${unexpected_changes}" >&2
  exit 1
fi

install -d -m 700 "${ops_root}/backups" "${ops_root}/locks"
exec 9>"${ops_root}/locks/integrix-app-rollout.lock"
flock -n 9 || {
  printf 'Another Integrix rollout is already running.\n' >&2
  exit 1
}

compose=(docker compose -f docker-compose.production.yml --env-file "${env_file}")
release_commit="$(git rev-parse --short "${release_ref}")"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="${ops_root}/backups/pre-rollout-${timestamp}-${release_commit}.dump"
rollback_tag="${app_image}:rollback-$(git rev-parse --short HEAD)"

"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"${backup_path}"
"${compose[@]}" exec -T postgres pg_restore --list <"${backup_path}" >/dev/null
sha256sum "${backup_path}" >"${backup_path}.sha256"

if docker image inspect "${app_image}:latest" >/dev/null 2>&1; then
  docker image tag "${app_image}:latest" "${rollback_tag}"
fi

git merge --ff-only "${release_ref}"
"${compose[@]}" build app
"${compose[@]}" run --rm app alembic upgrade head
"${compose[@]}" run --rm app alembic check
"${compose[@]}" up -d --no-deps app

for ((attempt = 1; attempt <= health_attempts; attempt++)); do
  if "${compose[@]}" exec -T app curl -fsS http://localhost:8000/health >/dev/null; then
    "${compose[@]}" exec -T app alembic current
    printf 'Integrix app rollout completed at %s. Rollback image: %s\n' "${release_commit}" "${rollback_tag}"
    exit 0
  fi
  sleep 1
done

printf 'Health check failed. Rollback image is available as %s.\n' "${rollback_tag}" >&2
exit 1
