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

if [ "$#" -eq 0 ]; then
  exec .venv/bin/python -m unittest discover -s tests
fi

# -p "..." / -v / -s ... vão direto para discover; resto vai para unittest puro.
case "$1" in
  -p|-v|-s|-t|-k)
    exec .venv/bin/python -m unittest discover -s tests "$@"
    ;;
  *)
    exec .venv/bin/python -m unittest "$@"
    ;;
esac
