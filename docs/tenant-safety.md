# Seguranca Multi-Tenant

Este repositorio trata ausencia de tenant como insegura por padrao. Use este
documento como checklist antes de alterar rotas, dispatch, repositorios,
dashboard, jobs, syncs, caches ou exports.

## Invariantes Obrigatorias

- Resolva tenant explicitamente e cedo no fluxo.
- Propague `tenant_id` por servicos, workflows, repositorios, jobs e chamadas
  externas quando a operacao for tenant-scoped.
- Nao faca read, write, update ou delete de dados de tenant sem filtro de
  tenant ou prova documentada de escopo global.
- Nao use identificadores de negocio como globalmente unicos sem confirmar o
  escopo do tenant.
- Chaves de cache, idempotencia e deduplicacao devem incluir `tenant_id` quando
  armazenam resultado de tenant.
- Logs e auditoria devem incluir `tenant_id` quando disponivel, junto com
  `call_id`, `tool_call_id` ou outro correlacionador estavel.
- Fallback de tenant deve ser observavel e seguro. Em producao, tenant ausente
  ou DID desconhecido nao deve virar outro tenant silenciosamente.
- Autenticacao nao substitui autorizacao tenant-aware em endpoints
  privilegiados.
- Payloads de log/auditoria devem evitar segredos, tokens e PII desnecessaria.

## Pontos De Alto Risco

- `/tools`, porque recebe payload externo e executa workflows por tenant.
- Dashboard e ops, porque podem consultar auditoria, custos e metricas de varios
  tenants.
- Syncs, retention e backfills, porque rodam fora do request path e podem
  escapar checks de rota.
- Idempotencia, porque colisao de chave pode devolver resultado de outro tenant.
- Feature flags e tenant config, porque definem quais comportamentos estao
  habilitados por tenant.
- Shims de compatibilidade, porque podem expor caminhos antigos sem os mesmos
  guardrails do caminho novo.

## Checklist Antes De Implementar

1. Onde o tenant e resolvido?
2. O que acontece quando o tenant nao e resolvido?
3. Todas as queries e writes de dados tenant-scoped recebem `tenant_id`?
4. Caches, idempotencia e deduplicacao incluem tenant?
5. Jobs, syncs e scripts seguem as mesmas regras de tenant do request path?
6. Logs e eventos de auditoria incluem tenant e correlacionador?
7. Existe teste negativo para acesso ou mistura cross-tenant?
8. A mudanca preserva fallback seguro em producao?

## Testes Esperados

Para mudancas tenant-sensitive, prefira testes que exercitem pelo menos dois
tenants no mesmo teste ou suite. Inclua cenarios negativos como:

- DID desconhecido em producao rejeita fallback.
- Query de tenant A nao retorna dados de tenant B.
- Cache ou idempotencia de tenant A nao atende chamada de tenant B.
- Endpoint ops sem `tenant_id` respeita `OPS_ALLOW_GLOBAL_QUERIES`.
- Tool nao registrada para uma implementacao retorna erro controlado.

Se a mudanca nao conseguir demonstrar isolamento, trate como bloqueio de
release ate existir guardrail ou teste suficiente.
