---
name: pydantic-models-py
description: Create or change Pydantic v2 request, response, tool, or tenant contracts in IntegrixAI. Use when validation, serialization, aliases, discriminators, or API model boundaries change; do not use for SQLAlchemy ORM models or force a generic Base/Create/Update/InDB hierarchy.
---

# Pydantic Contracts In IntegrixAI

## Place The Contract Correctly

- Put HTTP-facing schemas in `app/schemas`.
- Put shared tool envelopes in `app/core/tools/contracts.py`.
- Put tenant-specific request/response vocabulary in the owning
  `app/tenants/<tenant>/contracts.py` module.
- Keep SQLAlchemy persistence models in `app/models`; they are not Pydantic
  `InDB` documents.
- Preserve compatibility re-exports in `app/schemas/__init__.py` or existing
  shims when callers depend on them.

## Modeling Rules

1. Inspect adjacent contracts and consumers before creating a hierarchy.
2. Use Pydantic v2 APIs such as `ConfigDict`, `field_validator` and
   `model_validator`; do not add v1 `class Config` patterns.
3. Set `extra="forbid"` for controlled internal/admin inputs and
   `extra="ignore"` only where provider compatibility requires forward
   tolerance.
4. Add aliases only when an external contract requires them. Preserve provider
   field names at the boundary and translate to internal names explicitly.
5. Keep update fields optional only when the endpoint truly supports partial
   updates; distinguish omitted values from explicit `null` when behavior
   depends on it.
6. Bound strings and collections that reach persistence, logs or external
   systems. Normalize deterministically in validators.
7. Never silently add a Retell envelope to the Vapi contract; introduce a
   provider-specific boundary translator and retain one internal invocation
   model.

## Validation

- Test valid input, missing/extra fields, normalization and serialization.
- Test compatibility envelopes with representative provider payloads.
- For persistence changes, update SQLAlchemy models and Alembic separately and
  validate all three together.
