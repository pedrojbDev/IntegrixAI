# Fluxos De Runtime

Este documento resume os fluxos que o Codex deve entender antes de alterar
runtime, tenant, ops ou persistencia.

## `/tools`

1. `app/api/routes/tools.py` registra handlers de `pbsaude` e expoe `POST /tools`.
2. A rota cria `ToolDispatcher` com `Settings`.
3. O dispatcher valida o envelope Vapi e extrai `call.id`, `call.to` e
   `toolCallList`.
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

O contrato atual nao aceita diretamente o payload de Custom Function da Retell
(`name`, `args`, `call`). Integrar outro provedor exige um tradutor explicito
para o contrato interno, resolucao de tenant equivalente e uma chave de
idempotencia estavel; nao reutilize `/tools` supondo compatibilidade de envelope.

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

O registry permite preparacao autenticada da requisicao e limite por tool no
lote. PB Saude ingere o historico do proprio `/tools` antes de validar a busca,
usando a mesma politica de conversa dos eventos Vapi. Falha nessa persistencia
bloqueia a execucao. `app/platform/services/vapi_conversation.py` normaliza os
turnos e coordena locks por tenant/chamada; a interpretacao dos dados pertence
a `app/tenants/pbsaude/conversation.py`. Veja o
[fluxo Vapi PB Saude](../app/tenants/pbsaude/vapi/README.md) e os testes
`test_vapi_conversation_flow.py` e `test_vapi_conversation_postgres.py`.

## Auditoria, Metricas E Idempotencia

O dispatcher registra metricas em `metrics_store` e eventos por
`record_call_event`. Quando `DB_ENABLED=true`, auditoria e idempotencia podem
persistir dados nas tabelas configuradas.

Idempotencia usa escopo com `tenant_id`, `call_id` e `tool_call_id`. Nao reduza
essa chave para identificadores globais sem comprovar isolamento equivalente.

Payloads de auditoria devem ser suficientes para diagnostico, mas nao devem
expor segredos ou PII desnecessaria.

## Dashboard E Ops

O console operacional usa usuarios persistidos, memberships usuario-tenant,
sessao opaca em cookie HttpOnly e CSRF em mutacoes. `platform_admin` pode
selecionar tenants e so recebe visao global quando
`OPS_ALLOW_GLOBAL_QUERIES=true`; `tenant_user` fica limitado aos memberships.
`OPS_DASHBOARD_TOKEN` serve exclusivamente ao bootstrap do primeiro
administrador e nao autentica o dashboard depois disso.

Mudancas nessa area normalmente tocam:

- `app/api/routes/ops.py`;
- `app/api/routes/ops_session.py`;
- `app/api/routes/dashboard.py`;
- `app/core/ops`;
- `app/core/security/ops.py`;
- `frontend/` como fonte ativa da console;
- `app/static/dashboard` apenas quando a tarefa tocar compatibilidade legada.

Consultas operacionais resolvem o tenant a partir do principal. Escopo ausente,
conflitante ou fora dos memberships falha fechado. Preserve limites, filtros,
CSRF, revogacao de sessao e auditoria de autorizacao.

No overview, uma conclusao normal da Vapi conta como resolucao automatica,
independentemente de o cliente ou o agente encerrar a ligacao. Handoff permanece
um resultado separado porque exige continuidade humana.

As metricas do dashboard aceitam janelas moveis ou `window=custom` com
`start_date` e `end_date` (datas inclusivas no fuso `America/Sao_Paulo`,
ate 366 dias). O backend converte o fim para o inicio do dia seguinte e usa
limite superior exclusivo nas consultas de eventos, custos e auditoria.
Eventos usam `CallEvent.created_at`, custos usam `VapiCallCost.started_at` e
tentativas de erro usam `ToolBusinessErrorAttempt.updated_at`; dados recebidos
tardiamente aparecem quando as consultas sao atualizadas.
O relatorio PDF conserva sua selecao independente de periodo.

## Relatório diário por e-mail

Quando `DAILY_REPORT_ENABLED=true`, cada worker inicia um verificador em
memória. Às 07:00 de `America/Sao_Paulo`, somente o worker que obtiver o lock
advisory do PostgreSQL cria e envia o relatório. O estado em `ops_sync_state`
evita novo envio no mesmo dia, inclusive após reinício. O relatório agendado
exige `DAILY_REPORT_TENANT_ID`; destinatários vêm de
`DAILY_REPORT_RECIPIENTS` e o transporte usa as variáveis `SMTP_*`. Antes de
enviar, o fluxo exige sync Vapi e conversao PTAX sem atraso superior a 15
minutos; em caso contrario registra o bloqueio e tenta no proximo ciclo.

## Sync De Custos Vapi

O sync de custos vive em `app/core/ops/cost_sync_service.py`, roda a cada cinco
minutos e usa advisory lock PostgreSQL para uma unica execucao entre workers.
O primeiro ciclo faz backfill de 90 dias por `createdAt`; os seguintes usam
`updatedAt` com sobreposicao de dez minutos. Janelas saturadas sao subdivididas
e o cursor so avanca depois do bloco completo.

`vapi_call_costs.started_at` define a janela financeira. `synced_at` e apenas
metadado operacional. Total ausente permanece `NULL`; zero e valido somente
quando retornado explicitamente pela Vapi. O total oficial vem de `Call.cost`,
componentes divergentes geram ajuste, e registros sem tenant resolvido ficam
fora das metricas de cliente.

USD e a fonte financeira. BRL e derivado pela PTAX de venda do fechamento na
data da chamada em `America/Sao_Paulo`, usando a ultima data util anterior para
fim de semana ou feriado. Taxas do dia ainda sem fechamento sao provisorias e
substituidas posteriormente; falta de taxa deixa BRL nulo.

`OPS_COST_V2_ENABLED=false` mantem valores financeiros ocultos de
`tenant_user`, mas permite pre-visualizacao administrativa para reconciliacao.
Somente depois dos criterios de aceite a flag deve ser ativada. Relatorios
agendados nao sao enviados enquanto ela estiver desativada.

Ao alterar sync, retention ou agregacoes:

- mantenha janelas de tempo e limites de execucao claros;
- evite scans sem filtro;
- preserve idempotencia ou deduplicacao do dado sincronizado;
- valide com os testes de custo e dashboard.
