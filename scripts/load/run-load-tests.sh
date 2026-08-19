#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BASE_URL=""
WEBHOOK_SECRET=""
WEBHOOK_SECRET_HEADER=""
TO_NUMBER="${TO_NUMBER:-}"
SEARCH_CPF="${SEARCH_CPF:-}"
SEARCH_ESPECIALIDADE="${SEARCH_ESPECIALIDADE:-}"
SEARCH_CIDADE="${SEARCH_CIDADE:-}"
SEARCH_BAIRRO="${SEARCH_BAIRRO:-}"
RANDOMIZE_SEARCH_ARGS="false"
MODE="tools"
AGGRESSIVE="false"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/load/run-load-tests.sh --base-url URL [--webhook-secret SECRET] [--webhook-secret-header HEADER] [--to-number DID] [--search-cpf CPF] [--search-especialidade TEXT] [--search-cidade TEXT] [--search-bairro LEGACY_IGNORED] [--randomize-search-args] [--mode health|tools|idempotency|all] [--aggressive]
EOF
}

dotenv_value() {
  local key="$1"
  local env_file="$SCRIPT_DIR/../../.env"

  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line// }" || "${line#"${line%%[![:space:]]*}"}" == \#* ]] && continue
    if [[ "$line" == "$key="* ]]; then
      local value="${line#*=}"
      value="${value%\"}"
      value="${value#\"}"
      value="${value%\'}"
      value="${value#\'}"
      printf '%s' "$value"
      return 0
    fi
  done < "$env_file"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --webhook-secret)
      WEBHOOK_SECRET="$2"
      shift 2
      ;;
    --webhook-secret-header)
      WEBHOOK_SECRET_HEADER="$2"
      shift 2
      ;;
    --to-number)
      TO_NUMBER="$2"
      shift 2
      ;;
    --search-cpf)
      SEARCH_CPF="$2"
      shift 2
      ;;
    --search-especialidade)
      SEARCH_ESPECIALIDADE="$2"
      shift 2
      ;;
    --search-cidade)
      SEARCH_CIDADE="$2"
      shift 2
      ;;
    --search-bairro)
      SEARCH_BAIRRO="$2"
      shift 2
      ;;
    --randomize-search-args)
      RANDOMIZE_SEARCH_ARGS="true"
      shift
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --aggressive)
      AGGRESSIVE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Argumento desconhecido: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$WEBHOOK_SECRET" ]]; then
  WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(dotenv_value WEBHOOK_SECRET)}"
fi

if [[ -z "$WEBHOOK_SECRET_HEADER" ]]; then
  WEBHOOK_SECRET_HEADER="$(dotenv_value WEBHOOK_SECRET_HEADER)"
fi

if [[ -z "$WEBHOOK_SECRET_HEADER" ]]; then
  WEBHOOK_SECRET_HEADER="x-webhook-secret"
fi

if [[ -z "$TO_NUMBER" ]]; then
  TO_NUMBER="$(dotenv_value TO_NUMBER)"
fi

if [[ -z "$BASE_URL" || ( "$MODE" != "health" && -z "$WEBHOOK_SECRET" ) ]]; then
  echo "O argumento --base-url e WEBHOOK_SECRET sao obrigatorios para tools/idempotency/all. Informe --webhook-secret ou configure WEBHOOK_SECRET no ambiente/.env." >&2
  usage
  exit 1
fi

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 nao encontrado." >&2
  echo "Instale usando o pacote da sua distribuicao ou consulte https://grafana.com/docs/k6/latest/set-up/install-k6/" >&2
  exit 1
fi

run_k6() {
  local script_path="$1"
  local args=(
    run
    -e "BASE_URL=$BASE_URL"
    -e "WEBHOOK_SECRET=$WEBHOOK_SECRET"
    -e "WEBHOOK_SECRET_HEADER=$WEBHOOK_SECRET_HEADER"
    -e "TO_NUMBER=$TO_NUMBER"
    -e "RANDOMIZE_SEARCH_ARGS=$RANDOMIZE_SEARCH_ARGS"
    -e "AGGRESSIVE_MODE=$AGGRESSIVE"
  )

  [[ -n "$SEARCH_CPF" ]] && args+=(-e "SEARCH_CPF=$SEARCH_CPF")
  [[ -n "$SEARCH_ESPECIALIDADE" ]] && args+=(-e "SEARCH_ESPECIALIDADE=$SEARCH_ESPECIALIDADE")
  [[ -n "$SEARCH_CIDADE" ]] && args+=(-e "SEARCH_CIDADE=$SEARCH_CIDADE")

  args+=("$script_path")
  k6 "${args[@]}"
}

case "$MODE" in
  health)
    run_k6 "$SCRIPT_DIR/load-health.js"
    ;;
  tools)
    run_k6 "$SCRIPT_DIR/load-tools.js"
    ;;
  idempotency)
    run_k6 "$SCRIPT_DIR/load-idempotency.js"
    ;;
  all)
    run_k6 "$SCRIPT_DIR/load-health.js"
    run_k6 "$SCRIPT_DIR/load-tools.js"
    run_k6 "$SCRIPT_DIR/load-idempotency.js"
    ;;
  *)
    echo "Modo invalido: $MODE" >&2
    usage
    exit 1
    ;;
esac
