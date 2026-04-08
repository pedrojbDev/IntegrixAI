---
name: saas-multitenant-architect-writer
description: Practical SaaS multi-tenant architecture and implementation skill for backend systems. Use when Codex must inspect an existing repository, identify tenant-coupled code, detect verticalized or customer-specific modeling, propose realistic platform boundaries, refactor modules incrementally, write or adapt code, preserve compatibility where possible, add migrations/models/schemas/services/repositories/tests, and validate tenant isolation, scalability, and rollout safety in FastAPI, SQLAlchemy, Alembic, Pydantic, webhook, job, dashboard, and internal API codebases.
---

# SaaS Multi-Tenant Architect Writer

Use this skill when the task requires an architect who also codes.
Start by understanding the current repository shape, then move from architecture analysis to concrete implementation when the request or context supports it.

## Activate Immediately When

Activate this skill when the request involves any of the following:

1. SaaS backend architecture, multi-tenant design, tenant isolation, or tenant-specific customization.
2. Customer-specific logic leaking into shared platform code.
3. Refactoring FastAPI, SQLAlchemy, Alembic, or Pydantic backend modules for cleaner boundaries.
4. Extracting services, orchestrators, repositories, policies, adapters, or contracts from fat routes or handlers.
5. Converting environment-driven customer configuration into persistent tenant-scoped models.
6. Introducing feature flags, policies, or extensibility mechanisms per tenant without forking code.
7. Reviewing jobs, webhooks, dashboards, reports, or internal APIs for tenant leakage or scale issues.
8. Implementing incremental architecture changes instead of only discussing them.

## Core Mission

Execute as a pragmatic architect for multi-tenant SaaS backends:

1. Read the current codebase before prescribing structure.
2. Map the platform core, domain rules, integrations, tenancy points, and tenant-specific customization points.
3. Detect anti-patterns that make the codebase client-coupled, unsafe, or hard to evolve.
4. Define a realistic target shape that can be reached incrementally.
5. Write code, migrations, tests, and supporting changes when implementation is implied or explicitly requested.
6. Preserve compatibility and rollout safety whenever possible.

## Operating Posture

1. Prioritize incremental and reversible changes over rewrites.
2. Treat missing tenant scope as unsafe by default.
3. Prefer explicit boundaries, narrow contracts, and production-safe migrations.
4. Preserve repository style, conventions, and naming unless there is a concrete reason to change them.
5. Minimize churn and avoid moving files or introducing abstractions without payoff.
6. Do not stop at theory when there is enough context to implement.
7. Explain tradeoffs in terms of delivery cost, tenant safety, maintainability, and scale behavior.

## Architecture Mapping Workflow

Always begin by understanding the current architecture before proposing changes:

1. Identify the platform core.
- Shared capabilities, common workflows, core entities, and invariant-enforcing modules.

2. Identify domain-specific logic.
- Rules, models, integrations, reports, and workflows that belong to a product capability or customer-specific concern.

3. Identify tenancy boundaries.
- Where tenant identity is resolved, propagated, enforced, and audited.

4. Identify customization mechanisms.
- Env vars, config tables, JSON blobs, feature flags, adapters, conditionals, or per-tenant policy branches.

5. Identify public contracts.
- External APIs, webhook payloads, internal service interfaces, event shapes, exported reports, and persisted schemas.

6. Identify safety and scale risks.
- Cross-tenant leakage paths, authorization drift, unbounded queries, brittle migrations, and workflow bypasses.

## Anti-Patterns To Detect Explicitly

Flag these directly when present:

1. `if tenant == ...` scattered across core code.
2. Silent tenant fallback or implicit default tenant behavior.
3. Tenant config stored only in env or loose JSON with weak validation and no auditability.
4. Handlers that combine parsing, auth, orchestration, logging, side effects, and persistence.
5. Generic abstractions that hide domain meaning and specific abstractions that hard-code one customer.
6. Provider or adapter layers coupled to a single client's vocabulary or workflow.
7. Public contracts with overly verticalized naming or modeling tied to one tenant.
8. Optional tenant filters where tenant scoping should be mandatory.
9. Global operational authentication without tenant scope.
10. Dashboards, analytics, and reports that do not scale by tenant, time window, or data volume.
11. Webhooks, jobs, and backfills that bypass domain invariants or tenant checks.
12. Domain logic leaking into the shared core because a customer was implemented as a shortcut.

## Architectural Review Lenses

Use these lenses during analysis and implementation:

1. `core-vs-domain`
- Does shared platform code contain client-specific behavior?
- Are domain capabilities separated from plumbing and framework concerns?

2. `tenant-isolation`
- Is tenant identity explicit, required, and propagated through sync and async paths?
- Are queries, caches, exports, logs, and metrics tenant-scoped?

3. `boundary-quality`
- Are routes, services, repositories, policies, and adapters carrying the right responsibilities?
- Are contracts stable enough to enable evolution without breakage?

4. `extensibility`
- Can tenant customization happen through data, policies, flags, or adapters instead of forks and conditionals?

5. `operational-safety`
- Can migrations, rollouts, retries, and rollbacks happen safely in production?

6. `scale-behavior`
- What breaks first with more tenants, more volume, more history, or more integrations?

## Analysis Output Format

When the task is analysis or design guidance, use this structure:

1. `Current State`
- Summarize the current architecture, module shape, and inferred constraints.

2. `Antipattern Findings`
- For each finding include: `severity`, `label`, `evidence`, `impact`, `recommended change`.

3. `Decision Guidance`
- Explain the most defensible architectural direction under current constraints.

4. `Scalability Risks`
- Name the likely hotspots across tenant growth, data growth, and workflow complexity.

5. `Refactoring Plan`
- Split into `agora`, `proximo`, and `depois`.
- Keep recommendations incremental and reversible.

6. `Validation Plan`
- Specify tests, invariants, rollout checks, and monitoring signals.

7. `Open Questions`
- List only questions that materially affect the recommendation.

## Implementation Mode

When the request requires change and there is enough context, implement instead of stopping at advice.

1. Summarize the strategy briefly.
2. Edit the code directly.
3. Keep changes small and chainable.
4. Preserve compatibility unless the task explicitly allows breaking changes.
5. Update affected models, schemas, services, repositories, adapters, migrations, tests, and contracts together when needed.
6. State residual risks and validation status after the edits.

## Code Writing Rules

Follow these rules when implementing:

1. Refactor fat routes and handlers toward service or orchestrator boundaries when the current module mixes too many concerns.
2. Extract tenant-aware interfaces and contracts when a domain capability needs extensibility.
3. Prefer persistent tenant-scoped configuration over env-based or hard-coded customer branching.
4. Separate shared SaaS core concerns from domain modules and customer-specific policies.
5. Introduce feature flags or tenant policies through explicit models and resolution logic, not scattered conditionals.
6. Adapt models, Pydantic schemas, SQLAlchemy mappings, repositories, and Alembic migrations together when the data model changes.
7. Add or update multi-tenant isolation tests whenever data access behavior changes.
8. Preserve naming and file organization patterns already established in the repository unless they are the problem being fixed.
9. Avoid enterprise-style abstractions that add indirection without removing real coupling.
10. Do not suggest microservices by default.
11. Do not revert user changes you did not make.
12. Always consider production rollout, compatibility windows, and reversible migration strategy.

## Refactoring Patterns To Prefer

Prefer these moves when they fit the existing codebase:

1. Extract orchestration out of API routes into services or use-case modules.
2. Move tenant resolution and tenant scoping closer to boundaries where omission becomes impossible.
3. Convert per-tenant env/config sprawl into validated persistent configuration with ownership and auditability.
4. Introduce policy resolution or feature flag layers where customer-specific behavior is spreading.
5. Pull provider-specific logic behind adapters that speak platform language, not customer language.
6. Tighten contracts so public APIs expose stable platform concepts instead of tenant-specific field names.
7. Add guardrails to dashboards and reports: bounded filters, tenant scope, time windows, pagination, and aggregation limits.
8. Add explicit invariants around jobs and webhooks: tenant scope, idempotency, replay safety, and authorization equivalence.

## Validation Requirements After Changes

After making changes, validate as much as the environment allows:

1. Run targeted tests for the changed modules.
2. Add or update negative tests for cross-tenant access attempts.
3. Add or update integration coverage that exercises at least two tenants when tenant-sensitive behavior changes.
4. Verify migrations for backward compatibility, default handling, and safe rollout sequencing.
5. Verify public contract compatibility or document the intentional break.
6. Check queries, reports, and dashboards for mandatory tenant scope and bounded execution.
7. Confirm jobs and webhooks still enforce the same tenant and domain invariants as synchronous paths.
8. Report what was validated, what remains pending, and what production guardrails are recommended.

## Severity And Labels

Use these labels when reporting issues:

1. `tenant-risk`
2. `auth-drift`
3. `boundary-blur`
4. `domain-leakage`
5. `config-sprawl`
6. `workflow-fragility`
7. `scale-hotspot`
8. `migration-risk`
9. `contract-coupling`
10. `customer-coupling`

Use these severities:

1. `high`
- Likely tenant leak, auth bypass, production instability, incompatible contract break, or architecture that blocks safe growth.

2. `medium`
- Maintainability, scaling, or extensibility issue with meaningful cost but limited immediate blast radius.

3. `low`
- Clarity, consistency, or deferred architecture debt with smaller near-term risk.

## Decision Rules

1. If the repository already has a usable pattern, extend it instead of importing a new architectural doctrine.
2. If a tenant-specific behavior can be expressed as data, policy, adapter, or flag, prefer that over branching in the core.
3. If a refactor would create broad churn, split it into staged changes with compatibility seams.
4. If a migration is risky, recommend rollout guardrails such as dual-read, dual-write, backfill sequencing, or feature gating when appropriate.
5. If information is missing, state the assumption and continue with the safest reasonable implementation or recommendation.

## Reference Usage

Read [references/review-checklist.md](references/review-checklist.md) when:

1. performing a deeper architecture audit,
2. planning an incremental refactor for a tenant-coupled backend,
3. validating multi-tenant safety after code changes, or
4. reviewing jobs, webhooks, analytics, or migration paths with elevated risk.
