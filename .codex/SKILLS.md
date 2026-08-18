# Skills Index

Project skills are stored in [`.agents/skills`](../.agents/skills). This file
disambiguates triggers; [docs/INDEX.md](../docs/INDEX.md) selects repository
context. Trigger the minimum set that covers the task.

## Project-Specific Skills

| Skill | Use when | Do not combine by default with |
|---|---|---|
| `software-architecture-consultant` | analysis, design review or refactoring advice without implementation | `saas-multitenant-architect-writer` |
| `saas-multitenant-architect-writer` | cross-cutting architecture change that must also be implemented | `software-architecture-consultant` |
| `integrix-multitenant` | a localized change can affect tenant resolution, scope, isolation or fallback | another broad architecture skill unless the task is cross-cutting |
| `integrix-auth` | identity, session, CSRF, role, permission or authorization behavior | `integrix-vapi-webhooks` unless both trust boundaries change |
| `integrix-change-review` | explicit code/release review for concrete findings and blockers | implementation skills during a review-only request |
| `integrix-metrics` | KPI definitions, aggregation, time windows, cost/report semantics | broad architecture skills for a localized metric change |
| `integrix-vapi-webhooks` | inbound Vapi event authenticity, deduplication, retry or replay | ordinary `/tools` dispatch work |

## Utility Skills

| Skill | Trigger boundary |
|---|---|
| `fastapi-router-py` | creating or materially changing FastAPI routes; inspect neighboring routes first |
| `pydantic-models-py` | creating or changing Pydantic API/contracts; never use it for SQLAlchemy models |
| `skill-creator` | creating, splitting, trimming or validating a skill package |
| `frontend-design` | deliberate visual/UI work, not ordinary frontend data wiring |
| `pdf:pdf` | PDF layout, generation or rendered visual verification |

If no row matches, use repository docs and code without forcing a skill.
