# Integrix AI

Backend FastAPI para tool-calls de voz com roteamento multi-tenant por DID, auditoria operacional, sync de custos da Vapi e console ops React servida em `/dashboard`.

## Resumo

O sistema recebe webhooks de ferramentas em `/tools`, resolve o tenant a partir do numero discado, escolhe a implementacao do tenant, executa a tool, registra metricas, persiste auditoria mascarada e devolve a resposta no envelope esperado pelo orquestrador de voz.

Hoje o repositorio contem cinco blocos principais:

- backend FastAPI em `app/`
- console ops React/Vite em `frontend/`
- migrations Alembic em `alembic/`
- testes backend em `tests/`
- artefatos de deploy Docker/Caddy em `deploy/` e arquivos raiz

## O que o sistema faz hoje

### Fluxo principal

1. A plataforma de voz envia um POST para `/tools`.
2. O dispatcher extrai `call.id`, `call.to` e a lista `toolCallList`.
3. O tenant e resolvido por `TENANT_MAP`; em producao, fallback para tenant default pode ser rejeitado.
4. O webhook e validado pelo segredo configurado em `WEBHOOK_SECRET`.
5. A implementacao do tenant e resolvida por `DEFAULT_TENANT_IMPLEMENTATION` ou `TENANT_IMPLEMENTATION_MAP`.
6. A tool e executada via registry tenant-aware.
7. O resultado e salvo em cache de idempotencia quando DB esta habilitado.
8. Metricas em memoria e trilha de auditoria sao atualizadas.
9. O retorno sai sempre no envelope `{"results":[...]}`.

### Console ops

A aplicacao tambem expoe uma console operacional em `/dashboard` com:

- login por token ops
- sessao HttpOnly em cookie
- visoes de overview, custo, auditoria, diagnostico e resiliencia
- sync manual de custos da Vapi
- filtros por `tenant_id` e `assistant_id`

## Arquitetura

```text
app/
  api/routes/
    tools.py            # entrada principal /tools
    ops.py              # endpoints operacionais protegidos
    ops_session.py      # login/logout/status da sessao ops
    dashboard.py        # serving da SPA /dashboard
    health.py           # /health
  core/
    tools/              # dispatcher, registry, contratos, idempotencia
    tenant/             # resolucao de tenant e regras de fallback
    audit/              # persistencia sync/async de auditoria
    ops/                # dashboard analytics, retention, cost sync
    security/           # webhook e sessao ops
    metrics/            # metricas em memoria
  platform/
    services/           # roteamento por implementacao de tenant
  tenants/pbsaude/
    workflows/          # logica das tools do tenant
    integration/        # cliente HTTP, auth, mock, tradutor
    policies.py         # tools habilitadas para o tenant
  models/               # tabelas SQLAlchemy
  static/dashboard/     # shell legada usada fora de producao
frontend/
  src/                  # SPA React/Vite
tests/                  # suite backend com unittest
deploy/
  Caddyfile
  README.md
```

## Tools disponiveis

### Tools implementadas no codigo

- `authenticate_member`
- `get_authorization_status`
- `search_providers`
- `handoff_human`

### Tools realmente habilitadas hoje para `pbsaude`

De acordo com `app/tenants/pbsaude/policies.py`, apenas estas tools sao registradas:

- `search_providers`
- `handoff_human`

Isso e importante: o codigo das outras tools existe, mas a politica atual do tenant nao as expone no registry ativo.

## Stack tecnica

### Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Gunicorn
- SQLAlchemy 2
- Alembic
- Pydantic 2 / Pydantic Settings
- Psycopg 3
- HTTPX
- Structlog

### Frontend

- React 19
- Vite 6
- TypeScript
- Tailwind CSS
- TanStack Query
- React Hook Form
- Zod
- Recharts

## Estrutura de dados e persistencia

Quando `DB_ENABLED=true`, o sistema usa estas tabelas:

- `call_events`: trilha de auditoria operacional por chamada/tool/evento
- `vapi_call_costs`: custos sincronizados da Vapi
- `ops_sync_state`: cursor da ultima sincronizacao de custos
- `tool_invocation_results`: cache de idempotencia por `tenant_id + call_id + tool_call_id`
- `tool_business_error_attempts`: contagem de repeticao de erros de negocio por escopo

As migrations atuais vao ate:

- `0001_create_call_events`
- `0002_add_vapi_cost_tables`
- `0003_add_high_volume_indexes`
- `0004_add_tool_idempotency`

## Variaveis de ambiente

As configuracoes sao carregadas de `.env`.

### Aplicacao e ambiente

| Variavel | Default | Uso |
|---|---:|---|
| `APP_NAME` | `Integrix AI Call Center Pilot` | titulo da aplicacao |
| `ENVIRONMENT` | `dev` | `dev`, `staging`, `production`, etc. |
| `LOG_LEVEL` | `INFO` | nivel de log |
| `DATA_MODE` | `mock` | `mock`, `external_api` ou `protheus` |

### Banco e pool

| Variavel | Default | Uso |
|---|---:|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/integrix` | conexao principal |
| `DB_ENABLED` | `false` | habilita auditoria persistida e analytics SQL |
| `DB_CONNECT_TIMEOUT_SECONDS` | `2.0` | timeout de conexao |
| `DB_POOL_SIZE` | `5` | tamanho do pool |
| `DB_MAX_OVERFLOW` | `10` | overflow do pool |
| `DB_POOL_TIMEOUT_SECONDS` | `5.0` | espera maxima por conexao |
| `DB_POOL_RECYCLE_SECONDS` | `1800` | reciclagem de conexoes |

### Tenant e implementacao

| Variavel | Default | Uso |
|---|---:|---|
| `DEFAULT_TENANT` | `demo` | tenant fallback |
| `TENANT_MAP` | `{}` | JSON DID -> tenant |
| `DEFAULT_TENANT_IMPLEMENTATION` | `pbsaude` | implementacao padrao |
| `TENANT_IMPLEMENTATION_MAP` | `{}` | override tenant -> implementacao |

### Seguranca e operacao

| Variavel | Default | Uso |
|---|---:|---|
| `WEBHOOK_SECRET` | vazio | segredo do webhook `/tools` |
| `WEBHOOK_SECRET_HEADER` | `x-webhook-secret` | header do segredo |
| `OPS_DASHBOARD_TOKEN` | vazio | token de acesso ops |
| `OPS_TOKEN_HEADER` | `x-ops-token` | header do token ops |
| `OPS_ALLOW_GLOBAL_QUERIES` | `false` | em producao, permite consultas ops sem `tenant_id` |

### Auditoria e retention

| Variavel | Default | Uso |
|---|---:|---|
| `AUDIT_WRITE_MODE` | `sync` | `sync` ou `async` |
| `AUDIT_QUEUE_MAX_SIZE` | `10000` | fila da auditoria async |
| `AUDIT_BATCH_SIZE` | `100` | batch da auditoria async |
| `AUDIT_FLUSH_INTERVAL_SECONDS` | `1.0` | flush da fila |
| `CALL_EVENTS_RETENTION_DAYS` | `90` | retention de `call_events` |
| `VAPI_COST_RETENTION_DAYS` | `365` | retention de `vapi_call_costs` |

### Integracao externa

| Variavel | Default | Uso |
|---|---:|---|
| `EXTERNAL_API_BASE_URL` | vazio | base da API externa |
| `EXTERNAL_API_AUTH_TYPE` | `none` | `none`, `bearer`, `basic` |
| `EXTERNAL_API_TOKEN` | vazio | bearer token |
| `EXTERNAL_API_USERNAME` | vazio | usuario basic auth |
| `EXTERNAL_API_PASSWORD` | vazio | senha basic auth |
| `EXTERNAL_API_PROVIDER_SEARCH_PATH` | `/rest02/TNSCallCenter/busca-rede` | path de busca |
| `EXTERNAL_API_TIMEOUT_SECONDS` | `3.0` | timeout da API externa |
| `EXTERNAL_API_MAX_RETRIES` | `1` | retries HTTP |
| `EXTERNAL_API_RETRY_BACKOFF_SECONDS` | `0.2` | backoff base |
| `EXTERNAL_API_MAX_CONNECTIONS` | `50` | limite do pool HTTP |
| `EXTERNAL_API_MAX_KEEPALIVE_CONNECTIONS` | `20` | keepalive HTTP |
| `EXTERNAL_API_TENANT_CONFIGS` | `{}` | JSON com override por tenant |
| `PROVIDER_MAX_RESULTS` | `3` | maximo de prestadores na resposta |

### Timeouts de tool

| Variavel | Default | Uso |
|---|---:|---|
| `AUTH_TIMEOUT_SECONDS` | `2.0` | timeout da tool de autenticacao |
| `STATUS_TIMEOUT_SECONDS` | `2.0` | timeout da tool de status |
| `PROVIDER_TIMEOUT_SECONDS` | `2.0` | timeout da busca de prestadores |

### Catalogo e caos controlado

| Variavel | Default | Uso |
|---|---:|---|
| `SPECIALTIES_CSV_PATH` | vazio | caminho do catalogo CSV |
| `CHAOS_ERROR_RATE` | `0.0` | injecao de erro para simulacao |
| `CHAOS_LATENCY_MS` | `0` | injecao de latencia |

### Vapi

| Variavel | Default | Uso |
|---|---:|---|
| `VAPI_API_KEY` | vazio | autentica sync de custos |
| `VAPI_BASE_URL` | `https://api.vapi.ai` | base da Vapi |
| `VAPI_CALLS_PATH` | `/call` | endpoint de chamadas |
| `OPS_COST_SYNC_PAGE_SIZE` | `100` | pagina do sync |
| `OPS_COST_SYNC_LOOKBACK_MINUTES` | `60` | lookback inicial |

## Regras de producao

`app/config.py` valida o ambiente de producao e falha no boot se estes requisitos nao forem atendidos:

- `WEBHOOK_SECRET` obrigatorio
- `DATA_MODE=external_api`
- `DB_ENABLED=true`
- `AUDIT_WRITE_MODE=async`
- `TENANT_MAP` preenchido
- `OPS_DASHBOARD_TOKEN` definido
- base de API externa configurada
- credenciais de auth externa coerentes com `EXTERNAL_API_AUTH_TYPE`
- `CHAOS_ERROR_RATE=0`
- `CHAOS_LATENCY_MS=0`
- `DATABASE_URL` nao pode apontar para `localhost`

## Setup local

### Backend

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Frontend

```powershell
cd frontend
npm install
```

### Configuracao minima para desenvolvimento

```env
APP_NAME=Integrix AI Call Center Pilot
ENVIRONMENT=dev
DATA_MODE=mock
DB_ENABLED=false
DEFAULT_TENANT=demo
TENANT_MAP={"+5511999999999":"tenant_demo"}
DEFAULT_TENANT_IMPLEMENTATION=pbsaude
OPS_DASHBOARD_TOKEN=troque-este-token
LOG_LEVEL=INFO
```

## Rodando localmente

### Backend

```powershell
.\venv\Scripts\activate
uvicorn app.main:app --reload
```

ou:

```powershell
python -m app.main
```

### Frontend em desenvolvimento

```powershell
cd frontend
npm run dev
```

O Vite sobe em `http://localhost:5173` com proxy para:

- `/ops`
- `/health`
- `/tools`

`frontend/vite.config.ts` usa:

- `VITE_APP_BASENAME=/` em dev
- `VITE_APP_BASENAME=/dashboard` por default em producao

`VITE_API_BASE_URL` e opcional e so precisa ser definido se frontend e backend forem servidos em origens diferentes.

## Build do frontend

```powershell
cd frontend
npm run build
```

No ambiente atual, esse build concluiu com sucesso.

O output fica em `frontend/dist`.

## Banco de dados e migrations

Para usar auditoria persistida, dashboard SQL e idempotencia:

```powershell
.\venv\Scripts\activate
alembic upgrade head
```

## Endpoints principais

### Publicos

- `POST /tools`
- `GET /health`

### Ops protegidos

- `POST /ops/session`
- `GET /ops/session`
- `DELETE /ops/session`
- `GET /ops/baseline`
- `GET /ops/audit/recent`
- `GET /ops/audit/summary`
- `POST /ops/costs/sync`
- `GET /ops/dashboard/overview`
- `GET /ops/dashboard/costs`
- `GET /ops/dashboard/tools`
- `GET /ops/dashboard/health`
- `GET /ops/dashboard/resilience`

### SPA e assets

- `GET /dashboard`
- `GET /dashboard/assets/*`
- fallback SPA em `GET /dashboard/{client_path:path}`

## Comportamento do endpoint `/tools`

### Envelope aceito

Aceita payload com `message.toolCallList` e suporte legado para leitura equivalente dentro do parser.

Exemplo:

```json
{
  "message": {
    "call": {
      "id": "call_123",
      "to": "+5511999999999"
    },
    "toolCallList": [
      {
        "id": "tc_001",
        "name": "search_providers",
        "arguments": {
          "cpf": "03457351538",
          "cidade": "feira de santana",
          "bairro": "Centro",
          "especialidade": "cardiologia"
        }
      }
    ]
  }
}
```

### Envelope de resposta

```json
{
  "results": [
    {
      "toolCallId": "tc_001",
      "result": {
        "ok": true,
        "tool_name": "search_providers",
        "data": {
          "providers": []
        },
        "error": null,
        "final_state": "RESOLVIDA_AUTOMATICO"
      }
    }
  ]
}
```

### Codigos de erro funcionais

- `VALIDATION`
- `TIMEOUT`
- `UPSTREAM_503`

## Multi-tenant

### Resolucao

`call.to` e comparado com `TENANT_MAP`.

Se o DID existir:

- usa o tenant mapeado

Se o DID nao existir:

- em dev/staging: pode cair em `DEFAULT_TENANT`
- em producao: o fallback e rejeitado quando `should_reject_tenant_resolution` detectar resolucao por fallback

### Implementacao do tenant

Depois de resolver o `tenant_id`, o sistema define a implementacao por:

- `TENANT_IMPLEMENTATION_MAP[tenant_id]`, se existir
- senao `DEFAULT_TENANT_IMPLEMENTATION`

Hoje a implementacao registrada no codigo e `pbsaude`.

## Idempotencia e tolerancia a repeticao

Quando `DB_ENABLED=true`, o dispatcher salva o resultado da tool em `tool_invocation_results` usando:

- `tenant_id`
- `call_id`
- `tool_call_id`

Se a mesma tool chegar novamente com o mesmo escopo, o sistema:

- nao reexecuta o handler
- devolve o resultado salvo
- registra evento `idempotency_hit`

Erros de negocio repetidos tambem sao contados em `tool_business_error_attempts`.

## Auditoria

### Modos

- `AUDIT_WRITE_MODE=sync`: grava no banco imediatamente
- `AUDIT_WRITE_MODE=async`: enfileira eventos e grava em lote por worker em background

### Mascaramento

Campos sensiveis sao mascarados antes da persistencia:

- `cpf`
- `token`
- `secret`
- `authorization`
- `password`

### Eventos relevantes

- `tool_completed`
- `tool_argument_validation`
- `tool_not_found`
- `tool_validation`
- `tool_timeout`
- `tool_upstream_503`
- `business_error`
- `idempotency_hit`
- `tenant_resolution_rejected`
- `webhook_unauthorized`

## Dashboard e analytics

### `GET /ops/dashboard/overview`

Retorna:

- KPIs de total, sucesso, falha, handoff e duracao media
- serie temporal por janela

### `GET /ops/dashboard/costs`

Retorna:

- custo total USD
- media por chamada
- serie temporal de custo

### `GET /ops/dashboard/tools`

Retorna:

- volume por tool
- taxa de falha
- handoff por tool
- custo total e medio por tool

### `GET /ops/dashboard/health`

Calcula saude operacional a partir de:

- freshness do sync da Vapi
- failure rate
- handoff rate
- coverage de custos
- repeticao de business errors
- idempotency hits

Estados possiveis:

- `no_data`
- `stable`
- `warning`
- `critical`

### `GET /ops/dashboard/resilience`

Expoe:

- serie de falhas
- serie de idempotency hits
- serie de business errors repetidos
- top tools degradantes
- top tools com handoff

## Sessao ops e seguranca

### Login

`POST /ops/session` recebe:

```json
{ "token": "..." }
```

Se o token bater com `OPS_DASHBOARD_TOKEN`, o backend define o cookie:

- `integrix_ops_session`
- `HttpOnly`
- `SameSite=lax`
- `Secure` em producao

### Rate limit

O endpoint de sessao aplica limitador simples em memoria por IP:

- janela de 60 segundos
- maximo de 10 tentativas

### Dashboard bootstrap

`/dashboard?token=...` so e aceito fora de producao.

Em producao:

- query token e rejeitado com `401`
- use login da SPA ou header ops

## Search providers

O tenant `pbsaude` tem workflow especifico para `search_providers`.

Capacidades observadas no codigo:

- suporta catalogo de especialidades por CSV
- normaliza acentos, texto e aliases
- aceita modo `mock` e `external_api`
- aplica validacao de negocio com retry controlado

## Deploy

O repositorio inclui:

- `Dockerfile`
- `docker-compose.production.yml`
- `deploy/Caddyfile`
- `deploy/README.md`
- `.env.production.example`

### Stack de deploy prevista

- `app`: Gunicorn + Uvicorn worker
- `postgres`: Postgres 16
- `caddy`: reverse proxy com HTTPS automatico

### Comando principal

```powershell
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

### Migrations no container

```powershell
docker compose -f docker-compose.production.yml --env-file .env.production exec app alembic upgrade head
```

## Testes e validacao

### Suite backend

Ha cobertura de testes em `tests/` para:

- config
- db
- tenant resolver
- dispatcher
- rotas tools
- rotas dashboard
- sync da Vapi
- retention
- providers externos

### Comando

```powershell
python -m unittest discover -s tests
```

### Resultado da verificacao feita agora

No ambiente atual, a suite backend nao rodou completamente porque o Python usado fora do `venv` nao tem dependencias instaladas, em especial:

- `structlog`
- `psycopg`

Ou seja: a suite existe, mas exige que o ambiente esteja preparado com `pip install -r requirements.txt`.

### Smoke script

Existe um smoke script operacional:

```powershell
python scripts\smoke_local.py --base-url http://127.0.0.1:8000
```

Ele valida:

- `/health`
- `handoff_human`
- `search_providers`
- `/ops/dashboard/overview`
- carga leve concorrente

## Limitacoes e pontos de atencao

### 1. Tools expostas vs implementadas

O codigo de `authenticate_member` e `get_authorization_status` existe, mas a politica ativa do tenant `pbsaude` registra somente:

- `search_providers`
- `handoff_human`

### 2. Console React em producao no container

O backend so serve a SPA React em producao se `frontend/dist` existir. Porem o `Dockerfile` atual copia:

- `requirements.txt`
- `alembic/`
- `app/`
- `scripts/`

Ele nao copia `frontend/` nem `frontend/dist`.

Na pratica, isso significa:

- em producao, o endpoint `/dashboard` pode retornar `503` dentro da imagem atual
- para servir a console no container, a imagem precisa ser ajustada para incluir o build do frontend, ou esse diretio precisa ser montado

### 3. Modo externo

O sistema esta claramente orientado para `search_providers` no modo `external_api`. O `README` e a operacao devem assumir isso como fluxo principal atual.

## Comandos uteis

### Backend

```powershell
.\venv\Scripts\activate
uvicorn app.main:app --reload
```

### Frontend

```powershell
cd frontend
npm run dev
npm run build
```

### Testes backend

```powershell
python -m unittest discover -s tests
```

### Migrations

```powershell
alembic upgrade head
```

### Smoke local

```powershell
python scripts\smoke_local.py --base-url http://127.0.0.1:8000
```

## Fluxo recomendado para subir o projeto corretamente

1. Criar e ativar o `venv`.
2. Instalar dependencias Python com `pip install -r requirements.txt`.
3. Copiar `.env.example` para `.env` e ajustar valores.
4. Se usar DB, executar `alembic upgrade head`.
5. Instalar dependencias do frontend em `frontend/`.
6. Rodar `npm run build` para gerar `frontend/dist` se quiser servir a console pelo backend.
7. Subir o backend com `uvicorn`.
8. Validar `GET /health`.
9. Rodar `python -m unittest discover -s tests`.
10. Rodar `python scripts\smoke_local.py`.
11. Acessar `/dashboard` e autenticar via token ops.
