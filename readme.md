# Integrix AI Call Center Pilot

Backend em `FastAPI` para orquestracao de tool-calls de voz, com suporte a multi-tenant por DID, modo mock para piloto, integracao externa para busca de rede credenciada, trilha de auditoria em banco, metricas operacionais e dashboard protegido por token.

## Visao geral

O projeto expoe uma API principal em `/tools` para receber chamadas de ferramentas disparadas por uma plataforma de voz como a Vapi. A aplicacao interpreta o payload recebido, resolve o tenant a partir do numero discado, executa a tool correspondente, registra metricas, mascara dados sensiveis antes de persistir auditoria e retorna a resposta no formato esperado pelo orquestrador.

Alem do fluxo principal, o backend possui:

- metricas em memoria para baseline operacional;
- auditoria opcional em Postgres;
- sincronizacao de custos de chamadas na Vapi;
- endpoints de dashboard para visao consolidada de volume, handoff e custo por tool;
- UI HTML embutida em `/dashboard`.

## Principais capacidades

- Autenticacao de beneficiario via tool `authenticate_member`
- Consulta de status de autorizacao via tool `get_authorization_status`
- Busca de prestadores via tool `search_providers`
- Transferencia para atendimento humano via tool `handoff_human`
- Resolucao de tenant por `TENANT_MAP` e `DEFAULT_TENANT`
- Modo `mock` para demonstracao sem dependencias externas
- Modo `external_api` para busca real de rede credenciada
- Catalogo opcional de especialidades a partir de CSV
- Logs estruturados em JSON com `structlog`
- Auditoria mascarada em `call_events`
- Dashboard operacional e de custo protegido por token

## Stack tecnica

- Python 3.12+ recomendado
- FastAPI
- Uvicorn
- SQLAlchemy 2
- Alembic
- Pydantic Settings
- Psycopg 3
- HTTPX
- Structlog

## Estrutura do projeto

```text
app/
  api/
    dashboard.py        # pagina HTML do dashboard
    ops.py              # endpoints operacionais protegidos
    routes.py           # endpoint principal /tools
    security.py         # validacao de token do dashboard/ops
  models/
    call_event.py       # auditoria de tool-calls
    ops_sync_state.py   # cursor de sync operacional
    vapi_call_cost.py   # custos de chamadas sincronizadas
  schemas/
    tools.py            # contratos de entrada/saida das tools
  services/
    audit_store.py      # persistencia de auditoria com masking
    dashboard_metrics.py
    data_provider.py
    external_api_provider.py
    mock_provider.py
    specialty_catalog.py
    tenant.py
    vapi_cost_sync.py
  config.py             # variaveis de ambiente
  db.py                 # engine/session SQLAlchemy
  logging.py            # logs estruturados JSON
  main.py               # bootstrap FastAPI
alembic/
  versions/             # migrations
requirements.txt
.env.example
```

## Como a aplicacao funciona

### Fluxo principal de tool-call

1. A plataforma de voz envia um POST para `/tools`.
2. O backend extrai `call.id`, `call.to`, `toolCallList[0].id`, `toolCallList[0].name` e `arguments`.
3. O tenant e resolvido a partir do numero discado usando `TENANT_MAP`.
4. Se `WEBHOOK_SECRET` estiver configurado, o header definido em `WEBHOOK_SECRET_HEADER` e validado.
5. A tool e executada pelo provider ativo (`mock` ou `external_api`).
6. O resultado e normalizado em `ToolResponse`.
7. Metricas em memoria sao atualizadas.
8. Se `DB_ENABLED=true`, um evento mascarado e persistido em `call_events`.
9. A resposta sempre volta em HTTP 200 com `results[]`, inclusive em falhas funcionais.

### Modos de dados

- `mock`: simula autenticacao, status de autorizacao e rede credenciada. Ideal para desenvolvimento e demonstracao.
- `external_api`: implementa hoje apenas a busca de prestadores em API externa. As tools de autenticacao e status ainda retornam indisponibilidade nesse modo.
- `protheus`: e aceito apenas por compatibilidade e convertido internamente para `external_api`.

## Requisitos

- Python instalado
- Ambiente virtual recomendado
- Postgres disponivel se quiser auditoria e dashboard com dados persistidos
- Credenciais da Vapi se quiser sincronizar custos reais

## Instalacao

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Configuracao

As configuracoes sao carregadas automaticamente do arquivo `.env`.

### Variaveis de ambiente

| Variavel | Obrigatoria | Default | Descricao |
|---|---|---:|---|
| `APP_NAME` | nao | `Integrix AI Call Center Pilot` | Nome exibido no FastAPI |
| `ENVIRONMENT` | nao | `dev` | Ambiente logico da aplicacao |
| `DATABASE_URL` | se usar DB | `postgresql+psycopg://postgres:postgres@localhost:5432/integrix` | String de conexao SQLAlchemy |
| `DB_ENABLED` | nao | `false` | Habilita persistencia de auditoria e endpoints dependentes de DB |
| `DB_CONNECT_TIMEOUT_SECONDS` | nao | `2.0` | Timeout de conexao com Postgres |
| `DATA_MODE` | nao | `mock` | `mock`, `external_api` ou `protheus` |
| `DEFAULT_TENANT` | nao | `demo` | Tenant padrao quando DID nao esta mapeado |
| `TENANT_MAP` | nao | `{}` | JSON com mapeamento `numero -> tenant` |
| `CHAOS_ERROR_RATE` | nao | `0.0` | Percentual de falhas artificiais para simulacao |
| `CHAOS_LATENCY_MS` | nao | `0` | Latencia artificial maxima em ms |
| `LOG_LEVEL` | nao | `INFO` | Nivel de log |
| `AUTH_MAX_ATTEMPTS` | nao | `2` | Limite de tentativas no provider mock |
| `EXTERNAL_API_BASE_URL` | se `DATA_MODE=external_api` | vazio | Base URL da API externa |
| `EXTERNAL_API_AUTH_TYPE` | nao | `basic` no exemplo / `none` no codigo | Tipo de autenticacao: `none`, `bearer`, `basic` |
| `EXTERNAL_API_TOKEN` | depende do auth | vazio | Token bearer |
| `EXTERNAL_API_USERNAME` | depende do auth | vazio | Usuario basic auth |
| `EXTERNAL_API_PASSWORD` | depende do auth | vazio | Senha basic auth |
| `EXTERNAL_API_PROVIDER_SEARCH_PATH` | nao | `/rest02/TNSCallCenter/busca-rede` | Path de busca de prestadores |
| `EXTERNAL_API_TIMEOUT_SECONDS` | nao | `3.0` | Timeout do provider externo |
| `PROVIDER_MAX_RESULTS` | nao | `3` | Maximo de prestadores retornados no modo externo |
| `EXTERNAL_API_TENANT_CONFIGS` | nao | `{}` | JSON com override por tenant para URL/auth/path/timeout |
| `AUTH_TIMEOUT_SECONDS` | nao | `2.0` | Timeout da tool de autenticacao |
| `STATUS_TIMEOUT_SECONDS` | nao | `2.0` | Timeout da tool de status |
| `PROVIDER_TIMEOUT_SECONDS` | nao | `2.0` | Timeout da tool de busca |
| `WEBHOOK_SECRET` | nao | vazio | Segredo do webhook `/tools` |
| `WEBHOOK_SECRET_HEADER` | nao | `x-webhook-secret` | Header usado para validar o webhook |
| `SPECIALTIES_CSV_PATH` | nao | vazio | Caminho de CSV para catalogo de especialidades |
| `VAPI_API_KEY` | se usar sync de custos | vazio | API key da Vapi |
| `VAPI_BASE_URL` | nao | `https://api.vapi.ai` | Base URL da Vapi |
| `VAPI_CALLS_PATH` | nao | `/call` | Path usado no sync de custos |
| `OPS_DASHBOARD_TOKEN` | se usar ops/dashboard | vazio | Token de acesso aos endpoints operacionais |
| `OPS_TOKEN_HEADER` | nao | `x-ops-token` | Header do token operacional |
| `OPS_COST_SYNC_PAGE_SIZE` | nao | `100` | Tamanho da pagina no sync da Vapi |
| `OPS_COST_SYNC_LOOKBACK_MINUTES` | nao | `60` | Lookback inicial quando ainda nao existe cursor |

### Exemplo minimo para desenvolvimento local

```env
APP_NAME=Integrix AI Call Center Pilot
ENVIRONMENT=dev
DATA_MODE=mock
DB_ENABLED=false
DEFAULT_TENANT=demo
TENANT_MAP={"+5511999999999":"tenant_demo"}
LOG_LEVEL=INFO
OPS_DASHBOARD_TOKEN=troque-este-token
```

### Exemplo com Postgres e dashboard

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/integrix
DB_ENABLED=true
OPS_DASHBOARD_TOKEN=troque-este-token
```

### Exemplo com API externa

```env
DATA_MODE=external_api
EXTERNAL_API_BASE_URL=https://customer-api.example
EXTERNAL_API_AUTH_TYPE=basic
EXTERNAL_API_USERNAME=seu-usuario
EXTERNAL_API_PASSWORD=sua-senha
```

## Banco de dados e migrations

Quando `DB_ENABLED=true`, o sistema persiste auditoria e habilita os endpoints de dashboard com base em dados reais.

### Tabelas principais

- `call_events`: trilha de auditoria de execucao das tools
- `vapi_call_costs`: custos de chamadas sincronizados da Vapi
- `ops_sync_state`: cursor do ultimo sync de custos

### Executar migrations

```bash
alembic upgrade head
```

### Observacoes

- Os endpoints `/ops/audit/*`, `/ops/dashboard/*` e `/ops/costs/sync` exigem `DB_ENABLED=true`.
- O dashboard HTML em `/dashboard` tambem depende de `OPS_DASHBOARD_TOKEN` configurado.

## Execucao local

### Opcao 1: via modulo principal

```bash
python -m app.main
```

### Opcao 2: via Uvicorn

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Healthcheck

`GET /health`

Exemplo de resposta:

```json
{
  "status": "ok",
  "environment": "dev",
  "data_mode": "mock"
}
```

## API principal

### POST `/tools`

Endpoint principal para receber tool-calls.

Caracteristicas importantes:

- aceita payload no formato com `message.toolCallList` ou `toolCallList` na raiz;
- retorna sempre `HTTP 200` com `results[]`;
- aplica validacao de segredo se `WEBHOOK_SECRET` estiver configurado;
- persiste auditoria mascarada se `DB_ENABLED=true`.

### Tools suportadas

| Tool | Finalidade | Provider atual |
|---|---|---|
| `authenticate_member` | valida CPF + data de nascimento | mock |
| `get_authorization_status` | consulta status de guia | mock |
| `search_providers` | busca rede credenciada | mock e external_api |
| `handoff_human` | forca transferencia para humano | interno |

### Exemplo de payload

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
          "cpf": "12345678901",
          "city": "sao paulo",
          "neighborhood": "bela vista",
          "query": "cardiologia"
        }
      }
    ]
  }
}
```

### Exemplo de resposta

```json
{
  "results": [
    {
      "toolCallId": "tc_001",
      "result": {
        "ok": true,
        "tool_name": "search_providers",
        "data": {
          "providers": [
            {
              "name": "Clinica Alpha",
              "specialty": "cardiologia",
              "address": "Av. Paulista, 1000",
              "city": "sao paulo",
              "neighborhood": "bela vista",
              "phone": "11 3333-1000"
            }
          ]
        },
        "error": null,
        "final_state": "RESOLVIDA_AUTOMATICO"
      }
    }
  ]
}
```

### Codigos de erro funcionais

| Codigo | Significado |
|---|---|
| `VALIDATION` | payload ou argumentos invalidos |
| `TIMEOUT` | timeout em processamento/upstream |
| `UPSTREAM_503` | indisponibilidade de servico externo |

## Endpoints operacionais

Todos os endpoints abaixo exigem o token enviado no header definido por `OPS_TOKEN_HEADER`.

### GET `/ops/baseline`

Retorna metricas em memoria acumuladas desde o boot da aplicacao.

### GET `/ops/audit/recent`

Lista eventos recentes da tabela `call_events`.

Filtros suportados:

- `limit`
- `tool_name`
- `call_id`
- `final_state`
- `ok`
- `event_type`

### GET `/ops/audit/summary`

Agrega eventos de auditoria. Aceita `since_minutes`.

### POST `/ops/costs/sync`

Sincroniza custos de chamadas da Vapi e faz upsert em `vapi_call_costs`.

### GET `/ops/dashboard/overview`

KPIs agregados por janela:

- `15m`
- `1h`
- `24h`
- `7d`

Filtros opcionais:

- `tenant_id`
- `assistant_id`

### GET `/ops/dashboard/costs`

Retorna serie temporal e resumo de custo em USD.

### GET `/ops/dashboard/tools`

Retorna performance e custo por tool, fazendo correlacao por `call_id`.

## Dashboard HTML

### GET `/dashboard`

Serve uma pagina HTML embutida para operacao. O acesso pode ser feito de duas formas:

- header com o token operacional;
- query string `?token=...`.

Funcionalidades da UI:

- KPIs de volume, handoff, duracao e custo
- series temporais
- tabela de custo por tool
- filtro por `tenant_id`
- filtro por `assistant_id`
- botao de sync de custos
- refresh automatico a cada 45 segundos

Exemplo:

```text
http://localhost:8000/dashboard?token=troque-este-token
```

## Seguranca

- O endpoint `/tools` pode validar segredo via `WEBHOOK_SECRET`.
- Os endpoints `/ops/*` e `/dashboard` exigem `OPS_DASHBOARD_TOKEN`.
- Payloads persistidos no banco passam por masking de chaves sensiveis como `cpf`, `token`, `secret`, `authorization` e `password`.
- O token operacional e comparado com `hmac.compare_digest`.

## Multi-tenant

O tenant e resolvido pelo numero de destino da chamada:

```env
DEFAULT_TENANT=demo
TENANT_MAP={"+5511999999999":"tenant_demo","+5511888888888":"tenant_b"}
```

Regras:

- se `call.to` estiver no `TENANT_MAP`, o tenant correspondente e usado;
- caso contrario, o sistema cai em `DEFAULT_TENANT`.

## Catalogo de especialidades

Se `SPECIALTIES_CSV_PATH` estiver configurado, a tool `search_providers` passa a validar a especialidade informada contra um catalogo CSV.

Comportamento:

- normaliza acentos, caixa e palavras de preenchimento;
- aceita aliases e aproximacoes;
- sugere especialidades proximas quando a informada nao e encontrada;
- prioriza variantes pediatricas quando o texto indicar essa intencao.

Se o catalogo nao estiver configurado, a busca usa `query` diretamente.

## Observabilidade

### Logs

- formato JSON via `structlog`
- contexto com `call_id` e `tenant_id`
- eventos de sucesso, erro, timeout, validacao e sync operacional

### Metricas

Em memoria:

- total de chamadas por tool
- sucesso/falha
- handoff
- duracao media

Persistidas:

- eventos detalhados em `call_events`
- custos em `vapi_call_costs`

## Limitacoes atuais

- no modo `external_api`, apenas `search_providers` esta implementada;
- nao existe suite de testes automatizados no repositorio neste momento;
- o dashboard depende de DB habilitado e populado;
- os dados do modo mock sao deterministicos, mas nao representam regras reais de negocio;
- o arquivo `.env.example` hoje diverge em um ponto do codigo: ele sugere `EXTERNAL_API_AUTH_TYPE=basic`, enquanto o default real em `app/config.py` e `none`.

## Sugestao de fluxo para subir o projeto

1. Criar e ativar o ambiente virtual.
2. Instalar dependencias.
3. Copiar `.env.example` para `.env`.
4. Ajustar pelo menos `DATA_MODE`, `DB_ENABLED` e `OPS_DASHBOARD_TOKEN`.
5. Se usar banco, executar `alembic upgrade head`.
6. Iniciar a aplicacao com `uvicorn`.
7. Validar `GET /health`.
8. Testar `POST /tools`.
9. Se usar ops, acessar `/dashboard?token=...`.

## Proximos passos recomendados

- adicionar testes automatizados para rotas e services;
- criar exemplos versionados de payload para cada tool;
- alinhar `.env.example` com os defaults reais do codigo;
- separar o dashboard HTML em frontend dedicado se ele crescer;
- adicionar autenticacao e status reais no provider externo.
