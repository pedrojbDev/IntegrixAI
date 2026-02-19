---
name: integrix-vapi-webhooks
description: Guide safe ingestion of Vapi webhook events in existing backends without assuming framework or architecture layout. Use when implementing or reviewing webhook endpoints, event pipelines, retries, deduplication, signature checks, and failure handling for inbound webhook traffic.
---

# Webhook Ingestion Safety Skill

Use this skill to design or review webhook ingestion with strong safety defaults.
Do not prescribe project structure, queue technology, framework, or deployment model.

## Safety Rules

1. Treat every webhook as untrusted input until validated.
2. Verify authenticity before processing business logic.
3. Enforce idempotency using a stable deduplication key per provider event.
4. Persist raw webhook payloads and metadata before downstream side effects whenever possible.
5. Return webhook responses quickly; never block on heavy processing, external API calls, or long transactions.
6. Separate ingest acknowledgment from business processing using asynchronous or deferred execution.
7. Bound retries and apply backoff with jitter; avoid infinite retry loops.
8. Classify failures as retryable or non-retryable and handle them differently.
9. Keep an immutable audit trail for event receipt, validation result, processing attempts, and final outcome.
10. Redact sensitive fields in logs while preserving traceability identifiers.
11. Associate every event with a tenant/account boundary before processing side effects.
12. Every event must carry a correlation ID across ingestion and processing.
13. Bind every event to an explicit tenant/account boundary before any side effects; treat ambiguous tenant mapping as terminal unless a safe quarantine path exists.
14. Require a stable correlation ID across ingest and processing (provider delivery ID, call_id, or generated event_trace_id).





## Baseline Processing Pattern

1. Receive event and capture request metadata (headers, timestamp, source IP, delivery ID if present).
2. Validate required envelope fields and authenticity checks.
3. Derive an idempotency key from provider event ID, or a deterministic hash when no stable ID exists.
4. Store raw event plus ingestion metadata with a uniqueness constraint on the idempotency key.
5. If duplicate is detected, return success response without re-running side effects.
6. Acknowledge webhook promptly after safe persistence and minimum validation.
7. Process business effects in a separate worker/transaction.
8. Record per-attempt status (`received`, `validated`, `processing`, `succeeded`, `failed_retryable`, `failed_terminal`).

## Validation Strategy

1. Validate transport-level authenticity first (signature/token/timestamp window).
2. Validate schema and required fields before mapping to internal models.
3. Validate semantic constraints (state transitions, entity existence, tenant/account ownership).
4. Reject impossible or stale transitions as terminal failures.
5. Keep validation deterministic so retries do not produce divergent decisions.
6. Allow configurable clock-skew tolerance for timestamp validation to avoid rejecting valid events during minor time drift.



## Retry Strategy

1. Retry only transient failures (timeouts, temporary network errors, lock contention, upstream 5xx).
2. Do not retry deterministic validation failures or business rule rejections.
3. Use bounded exponential backoff with jitter.
4. Keep retry count, next-attempt time, and last error in persistent state.
5. Route exhausted retries to a dead-letter path for manual or scheduled replay.
6. Ensure replay path reuses the same idempotency guardrails as live ingestion.
7.Ensure processing workers use a lease/lock or single-flight mechanism per idempotency key to prevent concurrent duplicate side effects.


## Failure Scenarios

1. Duplicate deliveries: Provider sends the same event multiple times.
   Response: Deduplicate via idempotency key and return success without duplicate side effects.
2. Out-of-order events: Later state arrives before earlier state.
   Response: Enforce version/sequence or state machine rules; defer or reject invalid transition.
3. Partial downstream outage: Ingestion works but a dependency fails.
   Response: Persist event, acknowledge quickly, and retry processing asynchronously.
4. Signature mismatch or expired timestamp: Authenticity check fails.
   Response: Reject event, log minimal forensic metadata, avoid business processing.
5. Slow handler causing provider timeout: Endpoint blocks on processing.
   Response: Move heavy work out of request path and return immediate acknowledgment.
6. Poison payload: Malformed or unsupported schema repeatedly retried.
   Response: Classify as terminal failure, stop retries, quarantine for inspection.
7. Storage write fails before acknowledgment: Raw event cannot be safely persisted.
   Response: Return non-success response so provider retries instead of losing event.
8. Replay without protection: Manual replay triggers duplicate side effects.
   Response: Force replay through the same idempotency and validation pipeline.

## Event Processing Checklist

1. Is authenticity validated before business logic?
2. Is a deterministic idempotency key defined and uniqueness-enforced?
3. Is raw event payload persisted with headers and receipt timestamp?
4. Does the endpoint return quickly without blocking on heavy work?
5. Are ingestion and business processing decoupled?
6. Are retryable and terminal errors explicitly separated?
7. Are retries bounded, backoff-based, and observable?
8. Are all attempts and state transitions auditable?
9. Is sensitive data redacted in logs while preserving correlation IDs?
10. Can replay run safely through the same validation and idempotency controls?
