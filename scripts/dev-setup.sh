#!/usr/bin/env bash
# Bootstrap canônico do ambiente local de testes.
#
# Uso (a partir de qualquer subdiretório do repo ou de um worktree):
#   ./scripts/dev-setup.sh
#
# O que faz (idempotente):
#   1. Cria .venv na raiz do repo com python3 se ainda não existir.
#   2. Instala/atualiza dependências de requirements.txt.
#   3. Roda `pip check` para detectar inconsistência de dependências.
#
# Por que existe: agentes e humanos usam o mesmo caminho, em vez de
# improvisar com `python`, `pip install --global` (bloqueado por PEP 668)
# ou `venv\Scripts\python.exe` (Windows). Para rodar testes, use
# ./scripts/test.sh ou .venv/bin/python.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "==> criando .venv em $ROOT/.venv"
  python3 -m venv .venv
else
  echo "==> .venv já existe, reutilizando"
fi

echo "==> instalando requirements.txt"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> verificando consistência"
.venv/bin/pip check

echo "==> OK. Rode os testes com: ./scripts/test.sh"
