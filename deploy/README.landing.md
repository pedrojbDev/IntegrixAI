# Deploy Da Landing Em VPS

Este guia publica somente a landing page em `https://integrix.com.br`.
O backend completo pode ficar depois em outro subdominio, por exemplo `api.integrix.com.br` ou `ops.integrix.com.br`.

## 1. DNS

No painel onde voce comprou o dominio, crie registros apontando para o IP da VPS:

```text
integrix.com.br      A      IP_DA_VPS
www.integrix.com.br  CNAME  integrix.com.br
```

Aguarde a propagacao antes de iniciar o Caddy.

## 2. Preparar A VPS

Use Ubuntu 24.04 LTS.

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin ufw
sudo systemctl enable --now docker
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

## 3. Enviar O Projeto

Na VPS:

```bash
git clone <repo-url> IntegrixAI
cd IntegrixAI
```

## 4. Gerar A Landing

Na VPS:

```bash
cd landing
npm ci
npm run build
cd ..
```

O Caddy vai servir os arquivos gerados em `landing/dist`.

## 5. Criar Ambiente Da Landing

Na raiz do projeto, crie um arquivo `.env.landing`:

```env
LANDING_DOMAIN=integrix.com.br
CADDY_EMAIL=seu-email@dominio.com
```

Use um e-mail real para emissao e renovacao automatica do HTTPS.

## 6. Subir A Landing

```bash
docker compose -f deploy/docker-compose.landing.yml --env-file .env.landing up -d
```

## 7. Validar

```bash
curl -I https://integrix.com.br
```

Abra no navegador:

```text
https://integrix.com.br
```

## 8. Atualizar Depois De Mudancas

Sempre que alterar a landing:

```bash
git pull
cd landing
npm ci
npm run build
cd ..
docker compose -f deploy/docker-compose.landing.yml --env-file .env.landing restart caddy
```

## 9. Quando O Backend For Para VPS

Mantenha a landing no dominio raiz:

```text
https://integrix.com.br
```

Publique o backend e o painel operacional em um subdominio:

```text
https://api.integrix.com.br
https://ops.integrix.com.br
```

Depois configure a landing com:

```env
VITE_OPS_CONSOLE_URL=https://ops.integrix.com.br/dashboard
```

e rode novamente:

```bash
cd landing
npm run build
```
