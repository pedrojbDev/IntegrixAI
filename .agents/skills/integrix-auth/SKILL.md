---
name: integrix-auth
description: Guide authentication and authorization reasoning in an existing system without enforcing a specific auth architecture. Use when designing or reviewing identity flows, permission models, role changes, tenant-scoped access rules, privilege escalation controls, and auth-related audit/logging behavior.
---

# Authentication And Authorization Reasoning Skill

Use this skill to evaluate auth changes for security, correctness, and operational traceability.
Do not prescribe provider choice, protocol stack, token format, or framework implementation patterns.

## Identity Context Rules

1. Resolve identity context explicitly for every protected operation.
2. Distinguish clearly between authentication (who) and authorization (what allowed).
3. Propagate identity context through request, background work, and downstream calls.
4. Treat missing, ambiguous, or conflicting identity context as deny-by-default.
5. Bind effective permissions to explicit subject, tenant, and action scope.
6. If auth dependencies degrade (policy store, session, introspection), fail closed for privileged operations and degrade safely for low-risk reads only when explicitly approved.


## Privilege Escalation Risk Patterns

1. Implicit role inheritance without explicit approval path.
2. Trusting client-provided role or scope claims without server-side validation.
3. Broad wildcard permissions attached to low-trust principals.
4. Inconsistent authorization checks between API, batch jobs, and admin tools.
5. Default-allow fallbacks when permission lookup fails or times out.
6. Cross-tenant role assignment paths that skip tenant boundary validation.
7. Privileged endpoints lacking step-up verification for sensitive actions.
8. Require step-up verification for high-risk actions (role changes, exporting PII, billing changes, tenant admin operations).


## Tenant-Scoped Permission Guardrails

1. Resolve tenant context before permission evaluation.
2. Evaluate permissions within tenant scope, not global scope, unless explicitly intended.
3. Prevent identity from one tenant granting or using permissions in another tenant.
4. Scope roles, groups, and policy bindings to tenant boundaries where applicable.
5. Validate tenant scope in reads, writes, exports, and administrative actions.
6. Require explicit justification and approval for any cross-tenant privileged operation.

## Audit And Logging Considerations

1. Log authentication outcomes with principal ID, tenant ID (if present), and correlation ID.
2. Log authorization decisions with action, resource, decision, and policy basis.
3. Record permission changes as immutable audit events with actor, target, before, after, and reason.
4. Redact secrets and sensitive claims while keeping security-relevant metadata.
5. Ensure failed and denied auth events are observable and alertable.
6. Preserve audit trace continuity across async jobs and retries.

## Security Checklist

1. Is identity context explicit and validated for every protected request?
2. Is authentication separated from authorization in logic and tests?
3. Are deny-by-default behaviors enforced for missing permission context?
4. Are privilege escalation paths identified and blocked?
5. Are tenant boundaries enforced consistently in permission checks?
6. Are high-risk actions protected with stronger verification where required?
7. Are token/session expiry, revocation, and replay risks considered?
8. Are permission caches invalidated safely after role/policy changes?
9. Are auth failures and denials logged without leaking sensitive data?
10. Are audit records tamper-evident and queryable for incident response?

## Review Checklist

1. What identity assumptions does this change introduce?
2. Which operations become newly allowed, denied, or conditionally allowed?
3. Are checks consistent across UI/API/background/admin execution paths?
4. Can a lower-privileged principal reach higher-privileged behavior indirectly?
5. Are tenant-scoped roles and permissions enforced end to end?
6. Are fallback paths fail-closed when auth services are degraded?
7. Are migration and backfill operations constrained by the same permission model?
8. Are audit and monitoring updates included with the auth change?
9. Are negative tests included for unauthorized and cross-tenant access attempts?
10. Is rollback strategy defined if permission behavior regresses in production?
11. Are key metrics/alerts defined for the changed path (error rate, latency, queue lag, retries, dead-letter volume) to detect regressions quickly?


## Output Format For Permission Changes

When proposing permission changes, always return this structure:

1. `Context`
- What flow or resource is changing.
- Current auth behavior and known pain points.

2. `Identity Model`
- Subjects involved (user, service, admin, job).
- How identity context is resolved and propagated.

3. `Permission Delta`
- Before and after allowed actions.
- Resource scope, tenant scope, and constraints.

4. `Escalation Risks`
- Potential privilege escalation paths introduced or mitigated.
- Severity and rationale for each risk.

5. `Tenant Scope Impact`
- How tenant boundaries are enforced.
- Any intentional cross-tenant capability and required controls.

6. `Audit And Logging Plan`
- Events to log for auth decisions and permission mutations.
- Redaction rules and incident investigation traceability.

7. `Validation Plan`
- Unit, integration, and negative test coverage.
- Manual verification steps for sensitive operations.

8. `Rollout And Rollback`
- Rollout guards, monitoring signals, and rollback conditions.
- Safe fallback behavior if auth dependencies fail.

9. Treat service-to-service callers and background jobs as first-class principals with explicit identity and tenant scope (no “internal = trusted” shortcuts).

