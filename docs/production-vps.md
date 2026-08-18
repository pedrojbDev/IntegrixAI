# Operacao Da Aplicacao Em VPS

Este documento define o procedimento seguro para inspecionar, atualizar e
recuperar a instalacao existente da Integrix. Dados de acesso, IPs, usuarios,
chaves e inventario do host pertencem ao ambiente operacional privado, nao ao
repositorio.

Conhecer este procedimento nao autoriza o Codex a alterar producao. Deploy,
migration, mudanca de variavel, sync manual ou qualquer outra mutacao remota
exige pedido explicito do usuario e confirmacao do alvo antes da execucao.

## Fonte De Verdade

- A branch canonica de producao e `main` depois da consolidacao do historico.
- O Compose da aplicacao e `docker-compose.production.yml`.
- Variaveis e segredos vivem no arquivo privado `.env.production` do host.
- O schema e controlado por Alembic; confirme `current` e `heads` em cada
  rollout.
- O endereco, usuario e diretorio do host devem ser obtidos do inventario
  operacional autorizado no momento do acesso.

Nunca copie para este documento valores observados em producao, credenciais,
enderecos privados, snapshots financeiros ou detalhes temporarios de uma
sessao de manutencao.

## Topologia Esperada

O ambiente usa Docker Compose com tres servicos:

| Servico | Container | Funcao |
|---|---|---|
| `app` | `integrix-api` | FastAPI, dashboard React, jobs e relatorios |
| `postgres` | `integrix-postgres` | Persistencia PostgreSQL 16 |
| `caddy` | `integrix-caddy` | HTTPS e proxy reverso |

O PostgreSQL deve publicar sua porta apenas em loopback. O Caddy publica HTTP e
HTTPS; a API fica acessivel internamente pela rede do Compose.

## Pre-Flight Obrigatorio

Antes de qualquer mudanca:

1. Confirmar autorizacao, host, diretorio, branch e commit esperados.
2. Inspecionar o worktree e registrar qualquer estado local intencional.
3. Confirmar que `main` local e remota apontam para o release aprovado.
4. Verificar containers, health, logs recentes e migration atual.
5. Validar localmente os testes e builds afetados.
6. Preparar rollback compativel com o schema que sera aplicado.
7. Fazer backup do PostgreSQL antes de mudancas que possam afetar dados, salvo
   dispensa explicita para aquele rollout.

Comandos de inspecao, executados dentro do diretorio autorizado do deploy:

```bash
git branch --show-current
git rev-parse --short HEAD
git status --short
git remote -v
docker compose -f docker-compose.production.yml --env-file .env.production ps
docker compose -f docker-compose.production.yml --env-file .env.production logs --tail=100 app
docker compose -f docker-compose.production.yml --env-file .env.production exec -T app alembic current
docker compose -f docker-compose.production.yml --env-file .env.production exec -T app alembic heads
```

Se houver arquivos modificados ou nao rastreados no host, interrompa a
atualizacao ate identificar sua finalidade. Nao use `git reset --hard`,
`git clean`, `git checkout --` ou outra operacao que possa apagar estado local.

## Segredos E Acesso

Segredos permanecem somente no ambiente privado. Nunca:

- imprima `.env.production` inteiro;
- copie tokens, senhas, chaves Vapi, SMTP ou banco para logs, commits ou
  respostas;
- use comandos de inspecao que despejem todo o ambiente do container;
- persista credencial pessoal para atualizar o repositorio;
- mantenha chave temporaria de manutencao depois do encerramento da sessao.

Prefira uma credencial de leitura dedicada para obter o release. Se o host nao
tiver acesso ao repositorio, entregue um artefato ou Git bundle verificavel sem
gravar credenciais permanentes.

## Atualizacao Segura

Leia tambem [deploy/README.md](../deploy/README.md). Para uma instalacao
existente:

1. Entregar ao host o commit aprovado de `main` sem sobrescrever estado local.
2. Confirmar novamente o hash recebido e o diff esperado.
3. Construir a nova imagem da aplicacao.
4. Aplicar migrations em container temporario.
5. Substituir somente o servico `app` quando banco e proxy nao mudaram.
6. Validar health interno e publico, migration, logs e o fluxo alterado.
7. Observar erros e metricas durante a janela definida para o rollout.

Comandos da etapa de aplicacao, somente depois das confirmacoes anteriores:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production build app
docker compose -f docker-compose.production.yml --env-file .env.production run --rm app alembic upgrade head
docker compose -f docker-compose.production.yml --env-file .env.production up -d --no-deps app
docker compose -f docker-compose.production.yml --env-file .env.production exec -T app alembic current
docker compose -f docker-compose.production.yml --env-file .env.production logs --tail=100 app
```

O Caddy e o PostgreSQL nao devem ser recriados em uma atualizacao exclusiva da
aplicacao. Use a URL de health registrada no inventario privado para o teste
externo.

## Dashboard, Custos E Jobs

O bootstrap do dashboard e uma operacao unica. Depois que existe um
`platform_admin`, `OPS_DASHBOARD_TOKEN` nao autentica rotas e nao deve ser
restaurado como mecanismo de login.

Antes de alterar sync ou custos, confirme no ambiente os valores e o suporte do
plano Vapi para:

- `OPS_COST_SYNC_ENABLED`;
- `OPS_COST_V2_ENABLED`;
- `OPS_COST_BACKFILL_DAYS`;
- `OPS_COST_SYNC_INTERVAL_SECONDS`;
- `OPS_COST_SYNC_OVERLAP_MINUTES`.

O sync usa custo oficial da Vapi, conversao PTAX e exclusao mutua no PostgreSQL.
Custos sem tenant confiavel nao entram nas metricas de cliente. Nao transforme
um snapshot de reconciliacao em invariante do sistema.

## Reconciliacao Financeira

O reconciliador deve ser executado como modulo Python e sempre com tenant e
intervalo explicitos:

```bash
docker compose -f docker-compose.production.yml --env-file .env.production exec app \
  python -m scripts.reconcile_vapi_costs \
  --start AAAA-MM-DD \
  --end AAAA-MM-DD \
  --tenant-id TENANT_ID
```

`--end` e exclusivo. Libere custo v2 somente quando contagem, chamadas com
custo e USD coincidirem, `missing_fx` for zero e `within_tolerance` for
verdadeiro.

## Contencao E Rollback

Em regressao financeira, desative `OPS_COST_V2_ENABLED`. Em falha persistente
do provedor ou sync, desative `OPS_COST_SYNC_ENABLED`. Depois de alterar uma
flag, recrie somente `app` e valide logs, health e backlog.

Nao execute downgrade de migration ou remocao de dados automaticamente. Para
rollback de codigo:

1. identificar a ultima imagem ou commit saudavel;
2. confirmar sua compatibilidade com o schema ja aplicado;
3. preservar chamadas e eventos brutos para reprocessamento;
4. substituir somente a aplicacao;
5. validar os mesmos sinais usados no rollout.

Suspenda o rollout quando houver migration divergente, health instavel, erro de
autorizacao, perda de tenant scope, duplicacao financeira ou aumento persistente
de erros no fluxo de voz.
