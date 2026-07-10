# Deploy Em VPS

Guia operacional para subir o backend em uma VPS usando Docker Compose, PostgreSQL local e Caddy com HTTPS automático.

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

### Relatório diário por e-mail

Para habilitar o envio automático às 07:00 de Brasília, preencha no
`.env.production` as variáveis `DAILY_REPORT_TENANT_ID`, `SMTP_HOST`,
`SMTP_FROM_EMAIL` e, quando necessário, `SMTP_USERNAME` e `SMTP_PASSWORD`.
Mantenha `DAILY_REPORT_RECIPIENTS=pedrojesuinobatista@gmail.com` e acrescente
futuros destinatários separados por vírgula. Só então defina
`DAILY_REPORT_ENABLED=true` e recrie o serviço `app`.

Os valores de exemplo com `replace-with-...` e dominios `.example` sao placeholders.
Em `ENVIRONMENT=production`, o backend recusa esses valores e nao inicia ate que sejam trocados por segredos, dominio e credenciais reais.

Voce nao precisa editar `deploy/Caddyfile` para o caso padrao. O Caddy usa `DOMAIN` e `CADDY_EMAIL` do `.env.production`, abre HTTPS automaticamente e encaminha as requisicoes para o container `app`.

## 5. Subir Serviços

```bash
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
```

Aplicar migrations:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec app alembic upgrade head
```

## 6. Validar

Health público:

```bash
curl -fsS https://api.seudominio.com/health
```

Smoke remoto a partir da sua máquina local:

```powershell
.\venv\Scripts\python.exe scripts\smoke_local.py --base-url https://api.seudominio.com --tenant-id tenant_demo --to-number +5511999999999 --webhook-secret "<WEBHOOK_SECRET>" --ops-token "<OPS_DASHBOARD_TOKEN>" --load-calls 20 --load-workers 5
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
- Vapi envia `x-webhook-secret`.
- Logs não mostram `webhook_unauthorized`, `tenant_resolution_rejected` ou `UPSTREAM_503` em chamadas válidas.
