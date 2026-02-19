---
name: integrix-multitenant
description: Reason about multi-tenant behavior in existing backends without enforcing a specific architecture. Use when reviewing or proposing code/data changes that may affect tenant isolation, tenant-aware queries, tenant-scoped permissions, or tenant-specific customization.
---
# Always activate when:
- tenant, multi-tenant, isolation, segmentation
- shared tables, tenant_id, org_id, account_id, workspace_id
- caching keys, exports, reports, metrics, background jobs
- admin tooling, backfills, migrations, batch processing

# Multi-Tenant Reasoning Skill

Use this skill to review and propose backend changes with explicit tenant awareness.
Do not prescribe folder layout, deployment model, or a specific architecture pattern.

## Hard Safety Rules

1. Treat missing tenant context as unsafe by default.
2. Never propose reads, writes, updates, or deletes without explicit tenant scoping.
3. Never assume global uniqueness for business identifiers unless tenant scope is confirmed.
4. Flag any cross-tenant data path (joins, caches, logs, exports, metrics, queues) as high risk until proven isolated.
5. Require tenant-aware authorization checks in addition to authentication.
6. Require tenant-safe defaults for fallbacks and retries (no implicit fallback to another tenant).
7. Require masking/redaction for tenant-sensitive PII in logs and audit payloads.
8. If isolation cannot be demonstrated, recommend blocking release of the change.
9. Logs must include tenant_id whenever available.
10. Ensure correlation-friendly logging: include tenant_id and a stable request/call/job correlation ID whenever available.


## Review Checklist

Use this checklist for any proposal, review, or refactor:

1. Is tenant identity resolved explicitly and early in the request flow?
2. Is tenant identity propagated through service, repository, async jobs, and external calls?
3. Are all data operations tenant-scoped, including background and batch operations?
4. Are caches, keys, and invalidation tenant-aware?
5. Are audit records tenant-tagged and queryable by tenant?
6. Are authorization rules tenant-aware for every privileged operation?
7. Are rate limits, quotas, and feature flags tenant-scoped where relevant?
8. Are monitoring and alerts able to distinguish tenant-level failures?
9. Are migration/backfill scripts safe against cross-tenant writes?
10. Are failure modes defined (timeout, partial data, fallback) without tenant leakage?

## Guardrails to Suggest

- Enforce tenant scope at data-access boundaries (query helpers, repository guards, policies).
- Add negative tests for cross-tenant access attempts.
- Add integration tests that exercise at least two tenants in the same run.
- Add invariants in code review: "no tenant_id, no query."
- Add audit assertions for tenant_id presence on critical events.

## Output Format for Proposed Changes

When proposing changes, always return this structure:

1. `Context`
- What flow/component is being changed.
- How tenant is identified today.

2. `Risks`
- Explicit list of cross-tenant failure modes.
- Severity: `high`, `medium`, `low`.

3. `Proposed Changes`
- Concrete changes in behavior and validation rules.
- Tenant guardrails added.
- Data and auth implications.

4. `Validation Plan`
- Unit, integration, and negative tests.
- What proves tenant isolation is preserved.

5. `Rollback / Safe Fallback`
- How to disable safely if production issues appear.

## Non-Goals

- Do not mandate a specific architecture style.
- Do not prescribe tenant-per-db, tenant-per-schema, or shared-table as a fixed requirement.
- Do not require framework-specific patterns unless already present in the codebase.
