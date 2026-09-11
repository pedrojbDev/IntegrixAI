#!/usr/bin/env bash
# Runner canônico dos testes backend (unittest).
#
# Uso:
#   ./scripts/test.sh                          # suite ampla (igual ao CI)
#   ./scripts/test.sh -p "test_dashboard_route.py"
#   ./scripts/test.sh -p "test_tool_dispatcher.py" -v
#   ./scripts/test.sh tests.test_tenant -v     # repassa args p/ unittest
#
# Se .venv não existir, roda ./scripts/dev-setup.sh primeiro.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "==> .venv ausente, rodando bootstrap primeiro"
  ./scripts/dev-setup.sh
fi

# Testes locais nunca devem herdar credenciais, banco ou integrações da máquina
# do agente. Os testes que precisam de um cenário externo usam Settings/mocks
# explícitos. O PostgreSQL descartável da CI só fica disponível quando alguém
# opta por isso conscientemente com ALLOW_EXTERNAL_TESTS=1.
export ENVIRONMENT="dev"
export DATA_MODE="mock"
export DB_ENABLED="false"
export DATABASE_URL="sqlite://"
export AUDIT_WRITE_MODE="sync"
export OPS_COST_SYNC_ENABLED="false"
export DAILY_REPORT_ENABLED="false"
export PROMETHEUS_MULTIPROC_DIR=""
if [ "${ALLOW_EXTERNAL_TESTS:-0}" != "1" ]; then
  unset VAPI_TEST_DATABASE_URL
fi

echo "==> ambiente de teste local: DATA_MODE=$DATA_MODE DB_ENABLED=$DB_ENABLED"

if [ "$#" -eq 0 ]; then
  exec .venv/bin/python scripts/test_runner.py discover -s tests
fi

# -p "..." / -v / -s ... vão direto para discover; resto vai para unittest puro.
case "$1" in
  -p|-v|-s|-t|-k)
    exec .venv/bin/python scripts/test_runner.py discover -s tests "$@"
    ;;
  *)
    exec .venv/bin/python scripts/test_runner.py "$@"
    ;;
esac
