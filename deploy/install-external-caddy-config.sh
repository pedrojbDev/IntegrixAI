#!/usr/bin/env bash
set -euo pipefail

# Copies the currently active source configuration out of the Git worktree.
# Do not reload Caddy here: another site can share the same proxy process.

readonly target_path="${1:-/opt/integrix-ops/gateway/integrix.Caddyfile}"
readonly repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly source_path="${repo_root}/deploy/Caddyfile"

if [[ ! -f "${source_path}" ]]; then
  printf 'Missing source Caddyfile: %s\n' "${source_path}" >&2
  exit 1
fi

if [[ -e "${target_path}" ]]; then
  printf 'Refusing to overwrite existing external Caddy configuration: %s\n' "${target_path}" >&2
  exit 1
fi

install -d -m 700 "$(dirname "${target_path}")"
install -m 600 "${source_path}" "${target_path}"
sha256sum "${target_path}"
printf 'External Caddy configuration created. Set CADDY_CONFIG_PATH=%s in the private production environment before the next intentional Caddy restart.\n' "${target_path}"
