# Codex Orchestration Guide

Start with [docs/INDEX.md](../docs/INDEX.md) and load only the context routed for
the task. Agents supplement repository docs; they do not replace code and tests
as the source of truth.

## Agent Ownership

| Agent | Owns | Does not own |
|---|---|---|
| `architecture-multitenant` | shared-vs-tenant boundaries, isolation analysis, compatibility and refactoring strategy | routine route fixes or tenant implementation details |
| `backend-runtime` | FastAPI routes, `/tools`, dispatch, shared security, audit, metrics and runtime defects | tenant-specific workflows or persistence/dashboard ownership |
| `platform-ops-data` | models, Alembic, dashboard/ops, React console, reports, schedulers and cost sync | PB Saude workflows or generic architecture reviews |
| `tenant-implementation` | tenant workflows, contracts, translators, catalogs and provider adapters | shared-core behavior without an explicit integration seam |
| `docs-skills` | repository docs, AGENTS, Codex metadata, landing docs and skills | runtime behavior changes |

Do not create a separate frontend or landing agent while their ownership remains
small and aligned with `platform-ops-data` or `docs-skills`.

## Selection Rules

- Pick the narrowest owning agent. Split work only when file ownership can be
  disjoint; otherwise keep one owner.
- Use [SKILLS.md](SKILLS.md) to disambiguate skills. Do not pair both broad
  architecture skills or load skill references preemptively.
- Agents supplement repository docs and code. Their prompts must not duplicate
  task routing, schemas or validation commands.

## Coordination

- Give every delegated task a bounded, disjoint ownership area.
- Do not assign the same runtime files to multiple agents concurrently.
- Keep shared-core and tenant-specific changes with their owning agents.
- Tell delegated agents they share the worktree and must preserve other edits.
- Validate the smallest relevant slice first; use broad tests for cross-cutting
  changes.
- Preserve compatibility shims unless retirement is explicitly planned.
- Update the context index when real ownership changes, not for one-off tasks.
