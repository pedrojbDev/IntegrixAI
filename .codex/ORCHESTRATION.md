# Codex Orchestration Guide

This repository already has project-specific skills in [`.agents/skills`](c:/Users/55719/Desktop/IntegrixAI/.agents/skills) and now has Codex agent metadata in [`.codex/agents`](c:/Users/55719/Desktop/IntegrixAI/.codex/agents).
Use them conservatively: start from the real code, keep ownership clear, and preserve compatibility seams.

For task-specific repository context, start with [docs/INDEX.md](c:/Users/55719/Desktop/IntegrixAI/docs/INDEX.md). It links to the current architecture, runtime flows, tenant-safety invariants, and validation commands without duplicating `AGENTS.md`.

## When To Use Each Agent

1. `architecture-multitenant`
Use for boundary analysis, migration strategy, tenant-isolation review, or planning an incremental refactor.

2. `backend-runtime`
Use for `/tools`, route handling, dispatch behavior, audit/metrics wiring, and runtime bug fixes.

3. `platform-ops-data`
Use for dashboard, ops endpoints, models, migrations, cost sync, and static dashboard assets.

4. `tenant-implementation`
Use for work inside `app/tenants/*`, including workflows, translators, adapters, and tenant contracts.

5. `docs-skills`
Use for repo docs, skill docs, AGENTS, and Codex workflow documentation.

## Skill Usage

Skills remain in [`.agents/skills`](c:/Users/55719/Desktop/IntegrixAI/.agents/skills).
Prefer the project-specific ones when the task matches:

1. `saas-multitenant-architect-writer`
Use for architecture-plus-implementation work in the multi-tenant backend.

2. `integrix-multitenant`
Use for tenant isolation review and tenant-aware behavior changes.

3. `integrix-auth`
Use for auth/authz reasoning and permission safety.

4. `integrix-change-review`
Use for backend risk review before implementing or releasing a change.

5. `integrix-vapi-webhooks`
Use for webhook ingestion, retries, deduplication, and inbound event safety.

6. `integrix-metrics`
Use for metrics, dashboard logic, and KPI reasoning.

## Practical Flows

### Analyze a Feature

1. Use `architecture-multitenant` to map current boundaries and identify risks.
2. Use `tenant-implementation` if the feature is tenant-specific.
3. Use `docs-skills` only if the change also requires updated operational or architectural docs.

### Implement a Backend Change

1. Use `backend-runtime` for route and dispatch changes.
2. Use `tenant-implementation` for tenant-specific workflow or adapter changes.
3. Use `platform-ops-data` if the change touches models, migrations, ops endpoints, or dashboard data.

### Debug a Multi-Tenant Issue

1. Start with `architecture-multitenant` or `integrix-multitenant` to locate the tenant boundary.
2. Use `backend-runtime` for runtime path fixes.
3. Use `platform-ops-data` if the issue appears in reports, dashboard data, or sync jobs.

### Generate Documentation

1. Use `docs-skills` to update [readme.md](c:/Users/55719/Desktop/IntegrixAI/readme.md), [AGENTS.md](c:/Users/55719/Desktop/IntegrixAI/AGENTS.md), or Codex docs.
2. Use [docs/INDEX.md](c:/Users/55719/Desktop/IntegrixAI/docs/INDEX.md) as the map for new or updated repository docs.
3. Keep documentation synchronized with actual file paths, commands, and current architecture.

## Coordination Rules

1. Give each agent a disjoint primary ownership area.
2. Do not assign the same runtime files to multiple agents in parallel.
3. Validate the smallest relevant test slice after changes.
4. Preserve legacy shims unless the task explicitly includes their retirement plan.
