---
name: fastapi-router-py
description: Create or materially change FastAPI routes in IntegrixAI while preserving thin HTTP wiring, existing response contracts, authentication dependencies, tenant scope, and focused tests. Use for new endpoints, route extraction, request/query validation, or router mounting; do not trigger for service-only changes.
---

# FastAPI Routes In IntegrixAI

## Workflow

1. Use `docs/INDEX.md` to select at most two context documents.
2. Inspect the target route and one neighboring route before choosing a pattern.
3. Confirm the owning layer: HTTP parsing stays in `app/api/routes`; shared
   orchestration belongs in `app/core`; tenant vocabulary belongs in
   `app/tenants`.
4. Implement the smallest contract-preserving route change.
5. Mount a new router explicitly in `app/main.py` and add focused route tests.

## Repository Rules

- Preserve established prefixes, tags, status codes, response envelopes and
  compatibility imports. Do not impose generic CRUD conventions.
- Reuse dependencies from `app/config.py` and `app/core/security`; do not invent
  placeholder auth modules or trust client-provided tenant/role fields.
- Resolve and authorize tenant scope before tenant data access. Missing or
  conflicting scope fails closed in production paths.
- Keep routes thin. Move database queries, provider calls, dispatch and report
  generation to the owning core or tenant module.
- Validate bounded query parameters and request bodies at the boundary. Keep
  secrets and PII out of errors and logs.
- Treat `/tools` as a compatibility contract: preserve HTTP-200 result shaping,
  Vapi envelope handling, tool registration, audit and idempotency semantics.

## Validation

- Run the route test plus the smallest owning service/contract test.
- Add negative coverage for unauthorized, cross-tenant and invalid-input paths
  when relevant.
- Run `git diff --check`; use `docs/development.md` only to select broader tests.
