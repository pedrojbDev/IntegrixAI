# IntegrixAI Codex Instructions

## Source Of Truth

This repository is a FastAPI backend for multi-tenant voice tool orchestration,
with a React operational console. Treat the repository and its tests as the
source of truth.

Start every task with [docs/INDEX.md](docs/INDEX.md). It routes each task to at
most two context documents, the relevant code, and the smallest validation set.
Do not load the full [readme.md](readme.md) unless broad human-facing setup or
product context is required.

Core stack references:

- FastAPI entrypoint: [app/main.py](app/main.py)
- settings: [app/config.py](app/config.py)
- SQLAlchemy and Alembic: [app/db.py](app/db.py) and [alembic](alembic)
- tests: [tests](tests)
- active operational UI: [frontend](frontend), served at `/dashboard`

## Architecture Invariants

- `app/api/routes` contains thin HTTP wiring.
- `app/core` owns shared dispatch, security, audit, metrics, tenant resolution,
  and operational services.
- `app/platform` contains platform seams intended to outlive one tenant.
- `app/tenants` contains tenant workflows, contracts, translators, policies,
  and provider adapters. `app/tenants/pbsaude` is the active implementation.
- `app/services` and top-level `app/api/*` may be compatibility shims. Preserve
  them unless retirement is explicitly in scope and covered by tests.
- `app/models` and `alembic` must evolve together.
- `frontend/` is the source for the React console. `app/static/dashboard` is a
  legacy compatibility surface, not the primary frontend source.

Do not flatten `core`, `platform`, and `tenants` into a generic services layer.
Keep tenant-specific vocabulary and behavior out of shared core code.

## Safety Rules

- Resolve and propagate tenant scope explicitly. Missing tenant scope is unsafe
  by default; silent fallback in production is high risk.
- Keep tenant filters in reads, writes, cache keys, jobs, syncs, exports, and
  reports. Treat optional tenant filters as potential leakage.
- Keep routes thin and put orchestration in the owning core or tenant module.
- Update models, migrations, compatibility notes, and affected tests together.
- Preserve response envelopes, tool registration semantics, idempotency scope,
  structured logging, and secret/PII masking.
- Treat each voice provider payload as a separate external contract. The active
  `/tools` parser is Vapi-specific; add an explicit translator before accepting
  Retell or another provider envelope.
- Keep scheduled reports tenant-scoped and multi-worker safe. Never log SMTP
  credentials or recipient addresses.
- Preserve the current React stack unless a rewrite is explicitly requested.

## Validation

Use [docs/development.md](docs/development.md) for commands. Run the smallest
relevant tests first and the broad suite for cross-cutting changes. If runtime
validation cannot be completed, state exactly what remains. Validate migration
files whenever persistence changes.

## Agents And Skills

Agent ownership is defined in [.codex/ORCHESTRATION.md](.codex/ORCHESTRATION.md)
and `.codex/agents`; skill selection is defined in
[.codex/SKILLS.md](.codex/SKILLS.md). Skills remain in
[.agents/skills](.agents/skills). Prefer one narrow skill over overlapping broad
skills; add a new agent or skill only when ownership or workflow genuinely
diverges. Delegated tasks must have bounded, non-overlapping ownership.

## Knowledge Graph (Graphify)

`graphify-out/` holds the repo's knowledge graph (`graph.json`,
`GRAPH_REPORT.md`). Every agent must consult it when planning or changing code:

- Before touching code, run `graphify explain "<symbol>"` on each symbol you
  plan to change and `graphify path "<A>" "<B>"` to check blast radius between
  callers and effects (e.g. upsert paths vs `CallEvent` reconciliation).
- Treat the graph as a navigation aid, not the source of truth: it can be
  stale (check `Built from commit` in `GRAPH_REPORT.md` vs `git rev-parse
  HEAD`). Confirm line numbers and callers in the code before editing.
- `graphify-out/` is gitignored, so fresh worktrees start without it. If it is
  missing, run `graphify update .` first (free, no API cost).
- After merges that change architecture, run `graphify update .` so the graph
  does not rot.

## Evolution And Non-Goals

Keep these instructions aligned with real architecture. Refine existing docs,
agents, and skills before creating near-duplicates. Do not propose microservices,
replace unittest, remove compatibility imports, or rewrite the frontend by
default.
