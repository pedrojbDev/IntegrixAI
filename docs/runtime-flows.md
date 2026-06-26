# Fluxos De Runtime

Este documento resume os fluxos que o Codex deve entender antes de alterar
runtime, tenant, ops ou persistencia.

## `/tools`

1. `app/api/routes/tools.py` registra handlers de `pbsaude` e expoe `POST /tools`.
2. A rota cria `ToolDispatcher` com `Settings`.
3. O dispatcher extrai `call.id`, `call.to` e `toolCallList`.
4. `call.to` e usado para resolver tenant via `app/core/tenant/resolver.py`.
5. Em producao, fallback de tenant desconhecido ou ausente pode ser rejeitado.
6. O webhook e autorizado por `app/core/security/webhook.py`.
7. O `tenant_id` resolvido e convertido em `implementation_key` por
   `TenantConfigService`.
8. Cada tool call passa por idempotencia, registry tenant-aware, handler,
   metricas, auditoria e persistencia do resultado.
9. A resposta preserva o envelope `{"results": [...]}`.

Esse fluxo deve continuar retornando o contrato esperado pelo orquestrador de
voz, inclusive para validacoes, tools desconhecidas, eventos ignorados e erros
de upstream.

## Resolucao De Tenant

`resolve_tenant_details` usa `TENANT_MAP` para mapear DID para `tenant_id`.
Quando o DID nao existe ou `call.to` esta ausente, o codigo registra fallback
para `DEFAULT_TENANT`.

`should_reject_tenant_resolution` impede fallback silencioso em producao. Essa
regra e uma protecao de isolamento, nao uma conveniencia de ambiente.

Ao mudar esse fluxo:

- mantenha a origem da resolucao observavel;
- registre `tenant_id`, `call_id`, `tool_name` e origem quando houver fallback;
- preserve comportamento deny-by-default em producao para tenant nao resolvido.

## Dispatch E Registry

O registry e tenant-aware por `implementation_key`. A implementacao atual real e
`pbsaude`, registrada a partir de `app/tenants/pbsaude/tool_handlers.py`.

Handlers recebem argumentos, settings, `call_id` e `tenant_id`. Essa assinatura
mantem tenant explicito ate o workflow. Nao introduza handlers que dependam de
estado global para descobrir tenant.

## Auditoria, Metricas E Idempotencia

O dispatcher registra metricas em `metrics_store` e eventos por
`record_call_event`. Quando `DB_ENABLED=true`, auditoria e idempotencia podem
persistir dados nas tabelas configuradas.

Idempotencia usa escopo com `tenant_id`, `call_id` e `tool_call_id`. Nao reduza
essa chave para identificadores globais sem comprovar isolamento equivalente.

Payloads de auditoria devem ser suficientes para diagnostico, mas nao devem
expor segredos ou PII desnecessaria.

## Dashboard E Ops

O console operacional inclui login por token, sessao HttpOnly, endpoints ops e
visoes de auditoria/custos/diagnostico. Mudancas nessa area normalmente tocam:

- `app/api/routes/ops.py`;
- `app/api/routes/ops_session.py`;
- `app/api/routes/dashboard.py`;
- `app/core/ops`;
- `app/core/security/ops.py`;
- `app/static/dashboard` ou `frontend/`.

Em producao, consultas operacionais sem `tenant_id` dependem de configuracao
explicita. Preserve limites, filtros e autorizacao operacional.

## Sync De Custos Vapi

O sync de custos vive em `app/core/ops/cost_sync_service.py` e shims
relacionados. Ele usa estado operacional para cursor e persiste custos em
modelos SQLAlchemy.

Ao alterar sync, retention ou agregacoes:

- mantenha janelas de tempo e limites de execucao claros;
- evite scans sem filtro;
- preserve idempotencia ou deduplicacao do dado sincronizado;
- valide com os testes de custo e dashboard.
