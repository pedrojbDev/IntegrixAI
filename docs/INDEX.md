# Indice De Contexto Para Codex

Este diretorio e o mapa de leitura rapido para agentes e humanos que vao alterar o
repositorio. Use estes documentos junto com `AGENTS.md`, que continua sendo a
fonte principal de regras operacionais para Codex.

## Ordem De Leitura

1. Leia `AGENTS.md` antes de qualquer alteracao relevante.
2. Leia este indice para escolher o contexto certo.
3. Leia apenas os documentos necessarios para a area tocada.
4. Confirme o comportamento no codigo e nos testes antes de editar.

## Por Tipo De Tarefa

### Mudancas em `/tools`, dispatch ou contratos de tool

- Leia [runtime-flows.md](runtime-flows.md).
- Leia [tenant-safety.md](tenant-safety.md).
- Consulte `app/api/routes/tools.py`, `app/core/tools`, `app/core/tenant` e
  `app/tenants/pbsaude`.
- Valide com `venv\Scripts\python.exe -m unittest discover -s tests -p "test_tool_dispatcher.py"`,
  `venv\Scripts\python.exe -m unittest discover -s tests -p "test_tools_route.py"` e
  `venv\Scripts\python.exe -m unittest discover -s tests -p "test_tenant.py"`.

### Mudancas de arquitetura ou limites entre modulos

- Leia [architecture.md](architecture.md).
- Leia [tenant-safety.md](tenant-safety.md).
- Preserve a separacao entre `app/core`, `app/platform`, `app/tenants` e shims
  de compatibilidade.
- Use as skills `saas-multitenant-architect-writer`, `integrix-multitenant` e
  `integrix-change-review` quando a tarefa envolver risco de tenant, contrato ou
  refatoracao.

### Mudancas em dashboard, ops, custos ou dados operacionais

- Leia [runtime-flows.md](runtime-flows.md).
- Leia [development.md](development.md).
- Para exportacao em PDF, entrega por email ou agendamento, leia tambem
  [operational-reports.md](operational-reports.md).
- Consulte `app/api/routes/ops.py`, `app/core/ops`, `app/models`, `frontend` e
  `alembic`.
- Valide com `venv\Scripts\python.exe -m unittest discover -s tests -p "test_dashboard_route.py"` e
  `venv\Scripts\python.exe -m unittest discover -s tests -p "test_dashboard_service.py"`.
- Para sincronizacao de custos, inclua `venv\Scripts\python.exe -m unittest discover -s tests -p "test_vapi_cost_sync.py"`.
- Para entrega diaria, inclua `venv\Scripts\python.exe -m unittest discover -s tests -p "test_daily_report_delivery.py"` e
  `venv\Scripts\python.exe -m unittest discover -s tests -p "test_config.py"`.

### Mudancas em persistencia ou migrations

- Leia [architecture.md](architecture.md).
- Leia [tenant-safety.md](tenant-safety.md).
- Atualize modelos SQLAlchemy, migrations Alembic e testes juntos.
- Confirme que scripts, backfills e queries novas sao tenant-scoped quando
  operam sobre dados de tenant.

### Mudancas apenas de documentacao, AGENTS ou skills

- Leia `AGENTS.md`, `.codex/ORCHESTRATION.md` e `.codex/SKILLS.md`.
- Preserve `.agents/skills` no local atual.
- Prefira atualizar indices e ponteiros antes de reescrever skills completas.

## Documentos

- [architecture.md](architecture.md): responsabilidades dos principais pacotes e
  limites que nao devem ser achatados.
- [runtime-flows.md](runtime-flows.md): fluxos de runtime para `/tools`,
  tenant, auditoria, idempotencia, dashboard e sync de custos.
- [tenant-safety.md](tenant-safety.md): invariantes e riscos de isolamento
  multi-tenant.
- [development.md](development.md): comandos e criterios de validacao por area.
- [operational-reports.md](operational-reports.md): exportacao de relatorios,
  configuracao SMTP e entrega diaria multi-worker.
- [decisions/README.md](decisions/README.md): ponto de entrada para decisoes
  arquiteturais futuras.
