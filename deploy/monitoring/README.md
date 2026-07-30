# Monitoramento Da VPS E Da API

Esta configuracao envia somente metricas tecnicas para o Grafana Cloud:
host Linux, containers Docker e requisicoes HTTP da API. Logs, payloads, PII,
`tenant_id`, telefones e identificadores de chamadas nao sao enviados.

## 1. Criar As Credenciais No Grafana Cloud

No portal do Grafana Cloud, abra a configuracao de envio de metricas
Prometheus e copie:

- a URL de `remote_write`;
- o usuario da instancia Prometheus;
- um token com permissao somente para escrever metricas.

Adicione os valores somente em `/opt/IntegrixAI/.env.production`:

```text
GRAFANA_CLOUD_PROMETHEUS_URL=https://prometheus-REGIAO.grafana.net/api/prom/push
GRAFANA_CLOUD_PROMETHEUS_USERNAME=SEU_ID
GRAFANA_CLOUD_API_KEY=SEU_TOKEN
MONITORING_INSTANCE=srv1742572
```

Nao imprima o arquivo de ambiente nem grave o token no Git.

## 2. Validar E Iniciar

Use os dois arquivos Compose para comandos do monitoramento:

```bash
cd /opt/IntegrixAI
docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  config >/dev/null

docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  run --rm --no-deps alloy validate /etc/alloy/config.alloy

docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  up -d alloy
```

O Alloy e executado com privilegios e acesso de leitura ao host/Docker porque o
coletor de containers exige esses recursos. A interface do Alloy escuta somente
em `127.0.0.1` dentro do proprio container e nenhuma porta e publicada na VPS.

Confira a inicializacao sem exibir variaveis de ambiente:

```bash
docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  ps

docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  logs --tail=100 alloy
```

No Grafana Explore, a consulta abaixo deve retornar tres jobs:

```promql
up{deployment="integrix"}
```

Os jobs esperados sao `integrix-api`, `integrix-vps` e `integrix-docker`.

## 3. Importar O Dashboard

No Grafana, abra **Dashboards > New > Import**, envie
`deploy/monitoring/grafana-dashboard.json` e selecione a fonte Prometheus do
Grafana Cloud.

O painel usa atualizacao de 10 segundos e mostra:

- disponibilidade interna da API;
- requisicoes por segundo, erro 5xx, latencia p95 e requisicoes em andamento;
- CPU, memoria e disco da VPS;
- CPU e memoria por container.

Para disponibilidade externa, crie tambem um HTTP check do Grafana Synthetic
Monitoring para `https://api.integrix.com.br/health`. Configure falha ou ausencia
de dados como alerta.

## 4. Alertas Iniciais

Configure estes alertas depois que houver pelo menos 15 minutos de dados:

| Alerta | Condicao inicial | Duracao |
|---|---|---|
| API sem coleta | `up{job="integrix-api"} != 1` ou sem dados | 2 min |
| Erro HTTP 5xx | taxa de 5xx acima de 5% | 5 min |
| Latencia da API | p95 acima de 2 segundos | 5 min |
| Disco da VPS | uso acima de 85% | 10 min |
| Memoria da VPS | uso acima de 90% | 10 min |

O check sintetico externo e a fonte correta para detectar queda completa da
VPS. O `up` interno ajuda a diagnosticar o coletor e o processo da API.

## 5. Seguranca E Rollback

O endpoint `/internal/metrics` existe dentro do FastAPI para o Alloy, mas o
Caddy responde `404` a requisicoes publicas. Valide depois do deploy:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://api.integrix.com.br/internal/metrics
```

O resultado esperado e `404`.

Para interromper somente o monitoramento:

```bash
docker compose \
  -f docker-compose.production.yml \
  -f docker-compose.monitoring.yml \
  --env-file .env.production \
  stop alloy
```

Isso nao interrompe a API, o PostgreSQL ou o Caddy.
