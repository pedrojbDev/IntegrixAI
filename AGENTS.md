# IntegrixAI Codex Instructions

## Project Scope

This repository is a Python backend for multi-tenant voice tool orchestration built on FastAPI.
The current codebase is not flat: it already contains an architectural split between shared core flows, platform seams, tenant-specific implementations, and compatibility shims.
Any agent working here must preserve that direction instead of flattening it back into generic service folders.

## Stack And Runtime

Use the repository itself as the source of truth:

1. Backend framework: FastAPI in [app/main.py](c:/Users/55719/Desktop/IntegrixAI/app/main.py).
2. Configuration: Pydantic Settings in [app/config.py](c:/Users/55719/Desktop/IntegrixAI/app/config.py).
3. Persistence: SQLAlchemy 2 and Alembic in [app/db.py](c:/Users/55719/Desktop/IntegrixAI/app/db.py) and [alembic](c:/Users/55719/Desktop/IntegrixAI/alembic).
4. Logging: structlog JSON logging in [app/logging.py](c:/Users/55719/Desktop/IntegrixAI/app/logging.py).
5. Tests: unittest-style test suite in [tests](c:/Users/55719/Desktop/IntegrixAI/tests).
6. Static operational UI: dashboard assets in [app/static/dashboard](c:/Users/55719/Desktop/IntegrixAI/app/static/dashboard).

## Architectural Shape

Respect these repository responsibilities:

1. `app/api/routes`
Use for concrete HTTP routes and request wiring only.

2. `app/core`
Use for cross-cutting runtime logic such as tool dispatch, security, metrics, audit, and tenant resolution.

3. `app/platform`
Use for platform seams intended to outlive a single tenant implementation, such as tenant configuration and feature-flag style services.

4. `app/tenants`
Use for tenant or implementation-specific workflows, integrations, mappings, contracts, and translators.

5. `app/services` and some top-level `app/api/*`
Treat as compatibility shims unless the file clearly contains active logic.
Do not delete or bypass them casually; tests explicitly cover these compatibility imports.

6. `app/models` and `alembic`
Keep ORM and migration changes synchronized.

## Safe Modification Rules

1. Preserve compatibility shims unless the task explicitly includes removing them and the import surface is updated safely.
2. Do not collapse `core`, `platform`, and `tenants` into a single generic services layer.
3. Keep tenant resolution explicit. Missing tenant scope is unsafe by default.
4. Avoid introducing tenant-specific branching into shared core code when a tenant policy, configuration, or tenant implementation seam can express the behavior.
5. Keep routes thin. Push orchestration into core or tenant workflow layers as appropriate.
6. When changing persistence, update models, migrations, and affected tests together.
7. Keep dashboard changes aligned with the current static asset approach unless the user explicitly asks for a frontend rewrite.
8. Preserve the repository's current style: direct modules, small focused files, pragmatic comments, and minimal framework ceremony.

## Multi-Tenant Constraints

1. DID-based tenant resolution and fallback behavior are already part of the current system.
2. `default_tenant_implementation` and `tenant_implementation_map` are active seams in [app/config.py](c:/Users/55719/Desktop/IntegrixAI/app/config.py) and [app/platform/services/tenant_config_service.py](c:/Users/55719/Desktop/IntegrixAI/app/platform/services/tenant_config_service.py).
3. `app/tenants/pbsaude` is the real implementation key currently wired into tool registration.
4. Treat cross-tenant leakage, optional tenant filters, or silent fallback behavior as high-risk changes.

## Testing And Validation

Before concluding meaningful backend changes, prefer running the smallest relevant validation set first:

1. `python -m unittest`
Use for broad project validation when changes are cross-cutting.

2. `python -m unittest tests.test_tool_dispatcher tests.test_tools_route tests.test_tenant`
Use when changing dispatch, tenant resolution, contracts, or compatibility behavior.

3. `python -m unittest tests.test_dashboard_route tests.test_vapi_cost_sync`
Use when changing dashboard or ops/cost logic.

If a change touches migrations, validate migration files and explain any runtime validation still pending.

## Skills

Project skills already live in [`.agents/skills`](c:/Users/55719/Desktop/IntegrixAI/.agents/skills).
Do not move them unless the user explicitly requests a migration.
Prefer the existing project-specific skills over generic advice when the task matches them, especially:

1. `integrix-multitenant`
2. `integrix-auth`
3. `integrix-change-review`
4. `integrix-vapi-webhooks`
5. `integrix-metrics`
6. `saas-multitenant-architect-writer`

## Agent Usage Guidance

1. Use architecture-oriented agents for boundary analysis, refactoring plans, and compatibility strategy.
2. Use backend-oriented agents for concrete FastAPI/core/tenant implementation work.
3. Use docs-oriented agents for `README`, `AGENTS.md`, skill docs, and operational guides.
4. Delegate only bounded work with clear ownership. Avoid overlapping file ownership across agents.

## Evolution Rules

Treat this Codex setup as living project infrastructure, not as a fixed contract.

1. Update these instructions when the real architecture changes, not preemptively.
2. Add or split agents only when repository responsibilities genuinely diverge.
3. Merge or remove agents when they stop matching real ownership boundaries.
4. Prefer refining existing skills over creating near-duplicates without a clear new workflow.
5. If the project outgrows current conventions, evolve the rules with the codebase instead of forcing the codebase to obey stale rules.
6. When a rule starts blocking pragmatic delivery without protecting a real risk, revise the rule.

## Non-Goals

1. Do not propose microservices by default.
2. Do not replace unittest with another test framework unless explicitly requested.
3. Do not replace the static dashboard stack unless the task requires it.
4. Do not remove backward-compatible imports merely because the new architecture exists.
