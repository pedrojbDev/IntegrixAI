#!/usr/bin/env bash
# Inicia o backend com uma configuracao segura para desenvolvimento local.
#
# Uso:
#   ./scripts/run-local.sh
#   ./scripts/run-local.sh --reload
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "==> .venv ausente, rodando bootstrap primeiro"
  ./scripts/dev-setup.sh
fi

# Nao herdar configuracao de producao do .env da maquina do agente.
export ENVIRONMENT="dev"
export DATA_MODE="mock"
export DB_ENABLED="false"
export DATABASE_URL="sqlite://"
export AUDIT_WRITE_MODE="sync"
export OPS_COST_SYNC_ENABLED="false"
export DAILY_REPORT_ENABLED="false"
export PROMETHEUS_MULTIPROC_DIR=""
unset VAPI_TEST_DATABASE_URL

host="${HOST:-127.0.0.1}"
port="${PORT:-8000}"
echo "==> backend local em ${host}:${port} por padrao (DATA_MODE=$DATA_MODE DB_ENABLED=$DB_ENABLED)"

exec .venv/bin/python -m uvicorn app.main:app --host "$host" --port "$port" "$@"
