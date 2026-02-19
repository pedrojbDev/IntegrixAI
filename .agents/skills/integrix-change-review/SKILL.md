---
name: integrix-change-review
description: Safety reviewer for backend changes that focuses on risk detection without enforcing architecture. Use when reviewing code or proposals for tenant leaks, unsafe assumptions, missing validation, performance regressions, and security concerns before implementation or release.
---

# Backend Change Safety Review Skill

Use this skill to analyze backend changes and surface concrete risks early.
Do not prescribe framework, folder layout, database topology, or service architecture.
Prioritize review depth, threat awareness, and practical mitigation guidance.

## Review Focus

1. Detect tenant isolation violations and cross-tenant data exposure paths.
2. Detect unsafe assumptions about identity, input shape, ordering, retries, and defaults.
3. Detect missing validation at trust boundaries and state transitions.
4. Detect performance risks in hot paths, high-cardinality queries, and unbounded workloads.
5. Detect security weaknesses in access control, secret handling, and auditability.

## Risk Categories

Use these categories when evaluating or reporting issues:

1. `tenant-leak`
- Cross-tenant reads/writes, cache key collisions, export/report leakage, mis-scoped joins.

2. `unsafe-assumption`
- Hidden assumptions about uniqueness, ordering, actor trust, null handling, or fallback behavior.

3. `validation-gap`
- Missing or inconsistent input/schema/business validation, especially at API/job boundaries.

4. `performance-risk`
- N+1 patterns, unbounded scans, missing limits, lock contention, expensive recomputation.

5. `security-concern`
- Auth/authz bypass risk, privilege escalation paths, weak secret/token handling, insufficient logging.

6. `operability-risk`
- Missing metrics/alerts, poor error classification, no safe rollback or replay plan.

## Detection Heuristics

1. Trace data scope end to end: request -> service -> storage -> cache -> async job -> export.
2. Treat missing explicit scope (`tenant`, `actor`, `resource`) as a potential critical gap.
3. Check all writes for validation parity with reads and updates.
4. Check failure paths, not only success paths (timeouts, partial failure, retries, fallback).
5. Compare behavior across interfaces (API, admin tooling, worker jobs, scripts).
6. Flag assumptions not encoded as checks, constraints, or tests.

## Review Checklist

1. Is tenant context explicit and enforced for all relevant operations?
2. Are access checks present, consistent, and deny-by-default where context is missing?
3. Are inputs validated at boundaries and re-validated before critical side effects?
4. Are state transitions validated for legality and ordering?
5. Are idempotency and deduplication defined for retried or replayed flows?
6. Are retries bounded and classified into retryable vs terminal failures?
7. Are query patterns bounded (pagination, limits, filters) and appropriate for expected scale?
8. Are hot paths protected from N+1 behavior and full-table/large-range scans?
9. Are logs and audits sufficient for incident reconstruction without leaking secrets/PII?
10. Are negative tests present for cross-tenant access, invalid input, and unauthorized actions?
11. Are migration/backfill scripts held to the same safety checks as runtime paths?
12. Is rollback or feature-disable strategy defined for unexpected production behavior?

## Output Format For Change Analysis

When reviewing a backend change, always return this structure:

1. `Scope`
- What component/flow changed.
- What assumptions were inferred from the change.

2. `Findings`
- List each issue with: `severity` (`high|medium|low`), `category`, `evidence`, `impact`.

3. `Risk Summary`
- Top risks by blast radius and likelihood.
- Which risks block release vs can be deferred.

4. `Mitigations`
- Specific fixes or guardrails for each finding.
- Validation, authorization, performance, and logging improvements.

5. `Validation Plan`
- Required tests (unit/integration/negative/load) and what each test proves.

6. `Release Safety`
- Monitoring signals, rollback conditions, and safe fallback behavior.

## Severity Guidance

1. `high`
- Likely tenant leak, security bypass, destructive data corruption, or severe production degradation.

2. `medium`
- Correctness/performance/security risk with limited blast radius or compensating controls.

3. `low`
- Maintainability or observability gaps with minor immediate impact but long-term risk.
