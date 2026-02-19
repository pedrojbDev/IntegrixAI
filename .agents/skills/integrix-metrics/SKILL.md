---
name: integrix-metrics
description: Guide analytics and metrics implementation in an existing system without prescribing storage architecture or framework patterns. Use when defining instrumentation, proposing dashboards or KPI logic, validating metric correctness, reviewing aggregation rules, and handling tenant-aware or time-range analytics behavior.
---

# Metrics And Analytics Reasoning Skill

Use this skill to review or design analytics flows with correctness, performance, and tenant safety in mind.
Do not prescribe datastore choice, table layout, stream engine, or framework-specific implementation details.

## Core Principles

1. Separate immutable raw events from derived aggregations.
2. Treat aggregations as rebuildable projections, not the source of truth.
3. Preserve traceability from every metric back to contributing raw events.
4. Scope analytics access and computation by tenant context where applicable.
5. Define metric semantics explicitly (numerator, denominator, filters, time basis).
6. Validate both correctness and performance before release.
7. Every metric must specify its time basis explicitly: event-time (producer timestamp) vs ingest-time (receipt timestamp) and how late arrivals are handled.


## Raw Events Versus Aggregations

1. Keep raw events append-oriented and minimally transformed.
2. Build rollups/materialized metrics as separate derived outputs.
3. Record aggregation version or logic identifier to support safe recomputation.
4. Avoid mixing ingestion-time mutations with reporting-time calculations.
5. Ensure backfills and replays can rebuild aggregations from raw events without semantic drift.
6. Do not change metric definitions silently: version formulas/filters and backtest against historical data before switching defaults.


## Tenant-Aware Analytics Guardrails

1. Resolve tenant context explicitly for every analytics request and job.
2. Enforce tenant scoping in filters, joins, caches, exports, and dashboards.
3. Avoid global identifiers in analytics logic unless tenant scope is guaranteed.
4. Ensure shared metrics clearly document whether they are tenant-scoped or cross-tenant by design.
5. Include tenant identifiers in audit metadata and operational traces where safe.

## Time-Range Query Edge Cases

1. Boundary inclusivity mismatch (`start <= t < end` vs `start <= t <= end`).
2. Time zone conversion drift between storage, query, and display layers.
3. Daylight saving transitions causing duplicated or missing local-hour buckets.
4. Late-arriving events shifting previously reported windows.
5. Partial current-period windows being compared to complete historical periods.
6. Backfill/replay overlap causing double counting in range-based reports.
7. Clock skew between producers creating out-of-order event timestamps.
8. Granularity mismatch (event timestamp vs bucket timestamp) causing off-by-one bins.
9. When comparing periods, normalize for partial windows (e.g., exclude the current incomplete day/hour or label comparisons as partial).


## Validation Checklist

1. Are metric definitions unambiguous and documented?
2. Can each aggregate be traced back to raw event inputs?
3. Are deduplication and idempotency rules defined for event ingestion?
4. Are tenant-scope rules explicit for reads, writes, and exports?
5. Are filtering rules identical across API, batch jobs, and dashboard queries?
6. Are time-range boundary rules explicitly tested?
7. Are late events and replay scenarios validated?
8. Are null, missing, and malformed fields handled deterministically?
9. Are sampling rules (if any) documented with known error bounds?
10. Are acceptance tests aligned to business definitions, not implementation details?
11. Is there a reconciliation method (sampling or full) to compare aggregates vs raw-event truth for a known window?


## Performance Checklist

1. Is expected query latency defined per metric or dashboard use case?
2. Are high-cardinality dimensions identified and load-tested?
3. Is query cost validated under peak tenant concurrency?
4. Are expensive range scans bounded by safe defaults and limits?
5. Are recomputation/backfill workflows tested at realistic data volume?
6. Are cache hit behavior and invalidation correctness measured?
7. Are timeout, retry, and cancellation behaviors verified for analytics endpoints/jobs?
8. Are cold-start and warm-cache performance both measured?
9. Is metric freshness/lag measured and surfaced operationally?
10. Are regressions guarded with repeatable benchmarks in CI or release checks?

## Output Format For Analytics Proposals

When proposing analytics changes, always return this structure:

1. `Context`
- What product flow or reporting need is being addressed.
- Current instrumentation and known constraints.

2. `Metric Definitions`
- Exact formulas, filters, and time window semantics.
- Raw events required and derivation rules for each aggregate.

3. `Tenant Scope`
- How tenant context is resolved and enforced.
- Any intentional cross-tenant metrics and their controls.

4. `Edge Cases`
- Time-range and ordering edge cases that can bias results.
- Expected behavior for late, duplicated, and missing events.

5. `Validation Plan`
- Tests for correctness, reconciliation, and tenant isolation.
- Backfill/replay validation and acceptance criteria.

6. `Performance Plan`
- Latency/cost targets and benchmark method.
- Peak-load assumptions, bottlenecks, and mitigation steps.

7. `Rollout And Safety`
- Phased rollout, monitoring signals, and rollback triggers.
- How to compare new and old metric outputs during transition.
