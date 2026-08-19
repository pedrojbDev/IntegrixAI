# Deploy Em VPS

Guia operacional para subir o backend em uma VPS usando Docker Compose, PostgreSQL local e Caddy com HTTPS automático.

Para operar a instalacao existente da Integrix, leia primeiro
[docs/production-vps.md](../docs/production-vps.md). Este arquivo continua sendo
o guia generico de instalacao e atualizacao.

Para metricas em tempo quase real da VPS, dos containers e da API, use o guia
[monitoring/README.md](monitoring/README.md). O monitoramento e um Compose
opcional e nao altera a inicializacao padrao.

## 1. DNS

Crie um registro `A` apontando o subdomínio para o IP da VPS:

```text
api.seudominio.com -> IP_DA_VPS
```

Aguarde a propagação antes de subir o Caddy.

## 2. Preparar VPS

Use Ubuntu 24.04 LTS.

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin ufw fail2ban
sudo systemctl enable --now docker
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

## 3. Enviar Projeto

Clone o repositório ou envie a branch de produção para a VPS.

```bash
git clone <repo-url> IntegrixAI
cd IntegrixAI
```

## 4. Configurar Ambiente

```bash
cp .env.production.example .env.production
nano .env.production
```

Preencha obrigatoriamente:

```text
DOMAIN
CADDY_EMAIL
POSTGRES_PASSWORD
DATABASE_URL
TENANT_MAP
EXTERNAL_API_BASE_URL
EXTERNAL_API_USERNAME
EXTERNAL_API_PASSWORD
WEBHOOK_SECRET
OPS_DASHBOARD_TOKEN
VAPI_API_KEY
```

Use `ENVIRONMENT=production`, `DB_ENABLED=true`, `DATA_MODE=external_api` e `AUDIT_WRITE_MODE=async`.

`OPS_DASHBOARD_TOKEN` e somente o segredo de bootstrap inicial. Ele nao deve ser
distribuido a clientes e nao autentica o dashboard depois da criacao do
primeiro administrador.

### Relatório diário por e-mail

Para habilitar o envio automático às 07:00 de Brasília, preencha no
`.env.production` as variáveis `DAILY_REPORT_TENANT_ID`, `SMTP_HOST`,
`SMTP_FROM_EMAIL` e, quando necessário, `SMTP_USERNAME` e `SMTP_PASSWORD`.
Preencha `DAILY_REPORT_RECIPIENTS` somente no ambiente privado, usando
destinatários separados por vírgula. Só então defina
`DAILY_REPORT_ENABLED=true` e recrie o serviço `app`.

Os valores de exemplo com `replace-with-...` e dominios `.example` sao placeholders.
Em `ENVIRONMENT=production`, o backend recusa esses valores e nao inicia ate que sejam trocados por segredos, dominio e credenciais reais.

Voce nao precisa editar `deploy/Caddyfile` para o caso padrao. O Caddy usa `DOMAIN` e `CADDY_EMAIL` do `.env.production`, abre HTTPS automaticamente e encaminha as requisicoes para o container `app`.

## 5. Subir Serviços

Na primeira instalacao:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

Aplicar migrations:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec app alembic upgrade head
```

Em uma instalacao existente, construa a nova imagem e aplique a migration em um
container temporario antes de substituir a API em execucao:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production build app
docker compose -f docker-compose.production.yml --env-file .env.production run --rm app alembic upgrade head
docker compose -f docker-compose.production.yml --env-file .env.production up -d --no-deps app
```

Abra `/dashboard`, escolha **Configuracao inicial** e crie o primeiro
administrador usando `OPS_DASHBOARD_TOKEN`. O primeiro sync administrativo faz
o backfill de 90 dias; mantenha o custo v2 restrito a administradores ate
reconciliar um dia e sete dias contra a Vapi.

Use o reconciliador no container para conferir um periodo conhecido (a data
final e exclusiva):

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec app python -m scripts.reconcile_vapi_costs --start 2026-07-01 --end 2026-07-02 --tenant-id tenant_demo
```

Quando contagens, USD e BRL passarem nos criterios, defina
`OPS_COST_V2_ENABLED=true` e recrie o servico `app`. Em regressao financeira,
volte a flag para `false`; os dados brutos permanecem para reprocessamento.

## 6. Validar

Health público:

```bash
curl -fsS https://api.seudominio.com/health
```

Smoke remoto a partir da sua máquina local:

```powershell
.\venv\Scripts\python.exe scripts\smoke_local.py --base-url https://api.seudominio.com --tenant-id tenant_demo --to-number +5511999999999 --webhook-secret "<WEBHOOK_SECRET>" --ops-email "<ADMIN_EMAIL>" --ops-password "<ADMIN_PASSWORD>" --load-calls 20 --load-workers 5
```

## 7. Configurar Vapi

Configure a URL do server/webhook:

```text
https://api.seudominio.com/tools
```

Header:

```text
x-webhook-secret: mesmo valor de WEBHOOK_SECRET
```

Mantenha apenas as tools ativas:

```text
search_providers
handoff_human
```

## 8. Comandos Úteis

Logs da API:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production logs -f app
```

Logs do proxy:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production logs -f caddy
```

Status:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production ps
```

Backup manual do Postgres:

```bash
mkdir -p backups
docker compose -f docker-compose.production.yml --env-file .env.production exec -T postgres pg_dump -U integrix -d integrix > backups/integrix_$(date +%F_%H%M).sql
```

## 9. Critérios Para Liberar Vapi Real

- `curl /health` retorna `ok`.
- `alembic upgrade head` executado sem erro.
- Smoke remoto passa.
- Dashboard abre via `https://api.seudominio.com/dashboard`.
- Sync automatico aparece atual, cobertura de custo e PTAX foram reconciliadas.
- Um cliente de teste nao consegue consultar tenant fora de seu membership.
- Vapi envia `x-webhook-secret`.
- Logs não mostram `webhook_unauthorized`, `tenant_resolution_rejected` ou `UPSTREAM_503` em chamadas válidas.
