# Architecture Review Rubric

Use this reference when a request needs a deeper architectural audit than the main skill body provides.

## Reviewer Mindset

1. Look for structural causes, not only local code smells.
2. Prefer identifying the few highest-leverage issues over listing every stylistic imperfection.
3. Name the antipattern directly when the evidence supports it.
4. Judge architecture by changeability, failure isolation, and scale behavior, not by diagram neatness.

## System Shape

1. What are the major modules, services, jobs, and integration points?
2. What contracts exist between them?
3. Which components own business rules, persistence, orchestration, and side effects?
4. Which components are acting as accidental coordination hubs?

## Boundary Quality

1. Are responsibilities split by domain capability rather than framework convenience?
2. Are abstractions hiding complexity or merely relocating it?
3. Are interfaces stable enough that internals can change independently?
4. Are there layers that exist nominally but are bypassed in practice?

## Change Amplification

1. How many files or modules must change for a normal feature?
2. Do changes require touching unrelated layers?
3. Are there modules that attract edits for nearly every feature?
4. Does adding a field or rule require repeated edits across handlers, services, schemas, jobs, and serializers?

## Scalability

1. What are the highest-cardinality datasets and hottest execution paths?
2. Which parts depend on synchronous coordination?
3. Where could load spikes, retries, or backfills create cascading failures?
4. Which queries, jobs, and reports degrade as tenant count or history length grows?

## SaaS Safety

1. Is tenant context explicit at every data boundary?
2. Are exports, reports, cache keys, and search paths tenant-safe?
3. Are admin flows and support tooling held to the same scoping rules?
4. Could async retries or replayed events cross tenant boundaries or duplicate side effects?

## Authorization Drift

1. Are permission checks centralized or copied per endpoint and worker?
2. Do background jobs and webhook handlers enforce the same invariants as synchronous APIs?
3. Is there a path where internal calls bypass actor or tenant checks?

## Data Integrity

1. Is data ownership clear?
2. Are invariants enforced in one place or duplicated across layers?
3. Are read models, caches, and async consumers protected against stale or partial state?
4. Are migration scripts, backfills, and repair jobs held to the same invariants as runtime code?

## Operability

1. Can failures be isolated to a component or request path?
2. Are logs and metrics mapped to architectural boundaries?
3. Is rollback practical for schema, queue, and API changes?
4. Is there clear ownership for retries, dead letters, replay, and incident diagnosis?

## Team Scalability

1. Can engineers work in parallel without frequent conflicts?
2. Is ownership of modules and workflows clear?
3. Does the architecture reduce coordination cost or increase it?
4. Are there shared modules so central that every team change collides there?

## Refactoring Plan Template

Structure major recommendations into:

1. `now`
- Immediate fixes for correctness, tenant safety, authorization, or severe scale bottlenecks.

2. `next`
- Boundary cleanup, extraction of domain services, query hardening, and workflow reliability improvements.

3. `later`
- Lower urgency simplifications, platform improvements, and deeper reshaping once risks are reduced.

## Recommendation Filter

Before recommending any architectural change, check:

1. Does it solve a current or near-term pain?
2. Is it cheaper than the operational and cognitive cost it adds?
3. Can it be rolled out incrementally?
4. Does it make testing and diagnosis easier?
5. Would a simpler option solve enough of the problem?
