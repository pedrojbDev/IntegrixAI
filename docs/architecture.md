# Arquitetura Do Repositorio

Este backend FastAPI ja tem uma divisao arquitetural intencional. Ao adicionar
ou alterar codigo, preserve os limites abaixo em vez de mover tudo para uma
camada generica de `services`.

## Entrada HTTP

`app/api/routes` contem rotas concretas e wiring HTTP. Rotas devem permanecer
finas: extrair dependencias, receber payloads, chamar componentes de core,
platform ou tenant, e devolver o contrato esperado.

Alguns arquivos em `app/api/*` existem por compatibilidade. Nao remova nem
desvie esses imports sem atualizar a superficie publica e os testes de shims.

## Core Compartilhado

`app/core` contem logica transversal de runtime:

- `core/tools`: parsing, dispatch, registry, contratos, erros e idempotencia de
  tool calls.
- `core/tenant`: resolucao de tenant, modelos de resolucao e politicas de
  fallback.
- `core/security`: validacao de webhook e seguranca operacional.
- `core/audit`: registro de eventos operacionais.
- `core/metrics`: metricas em memoria.
- `core/ops`: servicos de dashboard, sync de custo e retention.

Codigo em `core` deve falar linguagem da plataforma. Evite colocar vocabulario
ou regras especificas de um cliente aqui quando uma policy, adapter, translator
ou workflow em `app/tenants` puder expressar a variacao.

## Platform

`app/platform` e a camada de seams que devem sobreviver a uma implementacao de
tenant especifica. Use esta area para configuracao de tenant, feature flags,
repositorios de tenant e modelos persistidos que representam capacidade da
plataforma.

`default_tenant_implementation` e `tenant_implementation_map` sao seams ativos.
Mudancas nessa area precisam manter claro como um `tenant_id` vira uma
implementacao registrada.

## Tenants

`app/tenants` contem implementacoes concretas por tenant ou por familia de
implementacao. Hoje `app/tenants/pbsaude` e a implementacao real registrada.

Mantenha aqui:

- workflows de tools;
- contratos e modelos especificos do tenant;
- mappings e translators;
- clientes e adapters de integracao;
- policies de tools habilitadas.

Nao leve comportamento especifico de `pbsaude` para `app/core` apenas para
facilitar uma chamada. Se a plataforma precisa conhecer uma variacao, prefira
um contrato estreito ou uma policy explicita.

## Services De Compatibilidade

`app/services` e alguns arquivos top-level em `app/api` sao shims de
compatibilidade. Eles existem para preservar imports antigos enquanto a
arquitetura evolui.

Antes de remover, renomear ou bypassar um shim:

- encontre os imports cobertos por `tests/test_shims.py`;
- confirme se ha consumidores externos esperados;
- planeje uma janela de migracao quando a remocao for intencional.

## Modelos E Migrations

`app/models` contem os modelos SQLAlchemy usados pela aplicacao. `alembic`
contem a historia de migrations. Toda mudanca de persistencia deve atualizar
modelo, migration e teste afetado no mesmo ciclo.

Para dados tenant-scoped, trate ausencia de `tenant_id` ou filtro equivalente
como risco alto ate provar que a tabela e realmente global.

## Dashboard E Frontend Operacional

O backend serve uma interface operacional. A abordagem atual inclui assets
estaticos em `app/static/dashboard` e tambem um app `frontend/` separado.

Nao proponha reescrita de frontend ou troca de stack para mudancas pequenas de
ops. Preserve a abordagem existente salvo pedido explicito.
