# Indice De Contexto Para Codex

Este arquivo e o roteador de contexto do repositorio. Leia `AGENTS.md`, encontre
a tarefa abaixo e carregue somente os documentos indicados antes de confirmar o
comportamento no codigo. O limite normal e de dois documentos por tarefa.

O [readme.md](../readme.md) e a referencia humana completa; nao deve ser
carregado automaticamente para uma mudanca localizada.

## Rotas Por Tarefa

Use a coluna `Dono / skill` para escolher o agente ou a skill, nao para carregar
mais contexto. Leia [.codex/SKILLS.md](../.codex/SKILLS.md) apenas quando houver
duvida entre skills sobrepostas.

| Tarefa | Contexto minimo | Codigo principal | Dono / skill | Validacao minima |
|---|---|---|---|---|
| Arquitetura ou limites multi-tenant | [architecture.md](architecture.md) + [tenant-safety.md](tenant-safety.md) | `app/core`, `app/platform`, `app/tenants` | `architecture-multitenant`; `software-architecture-consultant` para analise ou `saas-multitenant-architect-writer` para implementar | contratos e shims afetados |
| Identidade inbound, Billing, Wallet ou Ledger | [voice-billing-architecture.md](voice-billing-architecture.md) + [tenant-safety.md](tenant-safety.md) | `app/core/tenant`, `app/core/ops`, `app/platform`, `app/models`, `frontend` | `architecture-multitenant`; `saas-multitenant-architect-writer` | ownership, tenant negativo, idempotencia, reconciliacao inbound e contratos do dashboard |
| `/tools` ou dispatch Vapi | [runtime-flows.md](runtime-flows.md) + [tenant-safety.md](tenant-safety.md) | `app/api/routes/tools.py`, `app/core/tools`, `app/core/tenant` | `backend-runtime`; `integrix-multitenant` se o escopo de tenant mudar | `test_tool_dispatcher.py`, `test_tools_route.py`, `test_tenant.py` |
| Webhook de evento Vapi | [runtime-flows.md](runtime-flows.md) + [tenant-safety.md](tenant-safety.md) | rota de ingestao, seguranca, auditoria e idempotencia | `backend-runtime`; `integrix-vapi-webhooks` | autenticidade, duplicata, retry e tenant negativo |
| Implementacao PB Saude | [PB Saude README](../app/tenants/pbsaude/README.md) + [tenant-safety.md](tenant-safety.md) | `app/tenants/pbsaude` | `tenant-implementation` | workflow, provider ou translator afetado |
| Frontend operacional | [frontend/README.md](../frontend/README.md) + [runtime-flows.md](runtime-flows.md) | `frontend/src`, rotas `/ops` consumidas | `platform-ops-data`; `frontend-design` somente para trabalho visual | `npm run typecheck`, `npm run lint`, `npm run build` |
| Dashboard, metricas ou custos | [runtime-flows.md](runtime-flows.md) + [development.md](development.md) | `app/core/ops`, `app/api/routes/ops.py`, `frontend` | `platform-ops-data`; `integrix-metrics` para semantica de KPI | testes de dashboard e custo aplicaveis |
| PDF ou entrega diaria | [operational-reports.md](operational-reports.md) + [tenant-safety.md](tenant-safety.md) | `app/core/ops`, `app/config.py` | `platform-ops-data`; `pdf:pdf` somente para layout/render | report, delivery e config afetados |
| Auth, sessao ops ou autorizacao | [runtime-flows.md](runtime-flows.md) + [tenant-safety.md](tenant-safety.md) | `app/core/security`, `ops_session.py` | `backend-runtime`; `integrix-auth` | rota, sessao, CSRF, permissao e tenant negativos |
| Banco ou migrations | [architecture.md](architecture.md) + [development.md](development.md) | `app/models`, `alembic` | `platform-ops-data`; `pydantic-models-py` apenas para contratos Pydantic | modelo, migration e teste afetado |
| Deploy ou operacao da VPS | [production-vps.md](production-vps.md) + [deploy/README.md](../deploy/README.md) | Compose, Dockerfile, Caddy e env examples | `platform-ops-data` | build, migration aplicavel, health e logs |
| Landing page | [landing/README.md](../landing/README.md) + [deploy/README.landing.md](../deploy/README.landing.md) | `landing` | `docs-skills`; `frontend-design` se houver UI | test, typecheck, lint e build |
| Carga ou idempotencia | [load README](../scripts/load/README.md) + [runtime-flows.md](runtime-flows.md) | `scripts/load`, `/tools` | `backend-runtime`; `integrix-change-review` para risco de release | health, carga progressiva e idempotencia |
| Docs, agentes ou skills | [.codex/ORCHESTRATION.md](../.codex/ORCHESTRATION.md) + [.codex/SKILLS.md](../.codex/SKILLS.md) | `docs`, `.codex`, `.agents/skills` | `docs-skills`; `skill-creator` para skills | links, TOML, validacao de skills e `git diff --check` |

## Regras De Uso

- Confirme paths, contratos e comandos no repositorio antes de editar.
- Nao carregue documentos de outra area por precaucao generica.
- Use [development.md](development.md) apenas quando precisar selecionar ou
  executar validacoes.
- Nao combine duas skills amplas de arquitetura. Use a de analise ou a de
  implementacao conforme o pedido.
- Mudancas tenant-sensitive exigem tenant explicito e cenarios negativos.
- Inspecione `git status` antes de editar e preserve alteracoes locais que nao
  pertencem a tarefa.
- Atualize este indice quando uma responsabilidade real mudar; nao crie um novo
  documento sem uma fronteira de contexto clara.
