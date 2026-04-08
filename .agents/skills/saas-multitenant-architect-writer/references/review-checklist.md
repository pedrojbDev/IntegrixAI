# SaaS Multi-Tenant Review Checklist

Use this reference when a request needs a deeper review or a stricter implementation validation pass.

## Current State Mapping

1. What is platform core versus product/domain logic?
2. Where is tenant identity resolved?
3. Where can tenant-specific customization enter the flow?
4. Which modules own public contracts, persistence, orchestration, and integrations?
5. Which modules are edited most often and may be accidental coordination hubs?

## Customer Coupling Review

1. Is customer-specific logic present in shared services, schemas, repositories, or adapters?
2. Are field names, event names, or route names biased toward one tenant's language?
3. Are there branches, config lookups, or fallback behaviors that effectively fork behavior per tenant?
4. Can the current behavior be represented as tenant-scoped policy or configuration instead?

## Tenant Isolation Review

1. Is tenant scope mandatory for every query, write, export, and report?
2. Are background jobs, retries, webhooks, and backfills tenant-safe?
3. Are cache keys, audit entries, metrics, and logs tenant-aware?
4. Are support and admin flows scoped as strictly as product flows?

## Boundary Review

1. Are routes and handlers too fat?
2. Do services mix orchestration with persistence and response shaping?
3. Are repositories carrying business rules?
4. Are adapters translating between provider language and platform language correctly?
5. Are interfaces explicit enough to permit safe extension?

## Scale Review

1. Which queries degrade with tenant count, time range, or row count?
2. Which workflows will duplicate work under retries or replay?
3. Which contracts will be hardest to evolve without breaking clients?
4. Which modules will become bottlenecks for team changes?

## Implementation Checklist

When refactoring or adding code:

1. Preserve behavior first unless intentional change is required.
2. Add the new seam before removing the old path when compatibility matters.
3. Keep migrations production-safe and reversible when possible.
4. Update tests alongside the structural change, not later.
5. Prefer mandatory tenant scope at lower layers where omission is hard.
6. Avoid introducing abstractions that are broader than the actual variation.

## Post-Change Validation Checklist

1. Do changed paths require explicit tenant scope?
2. Do tests cover at least one negative cross-tenant case where relevant?
3. Are dashboards and reports bounded by tenant and time window?
4. Are webhooks and jobs enforcing the same invariants as sync APIs?
5. Are migrations safe for live rollout and rollback?
6. Are public contracts still compatible, or is the break documented and staged?
7. Are residual risks and follow-up steps stated clearly?
