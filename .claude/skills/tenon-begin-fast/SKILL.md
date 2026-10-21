---
name: tenon-begin-fast
description: Use when starting work on a Tenon unit of work (a GitHub issue id or an inline brief) and you want the fast path straight to an implementation plan. Triggers on "tenon-begin-fast", "tbf", "tbf bug 12", "tbf feat openapi-differ", "begin fast".
arguments: "type id"
---

# Tenon Begin (Fast Track)

## Overview

Turn a single unit of work into shipped, test-driven code. The fast track is:
**isolate → gather → dig → PRD → plan → implement (TDD).** No proposal/diagram
deliverables (use `tenon-begin` / `tb` when you need those).

**Two non-negotiables:** always work through the agents team; implementation is
always test-first via `superpowers:test-driven-development`.

**Invocation:** `tbf <type> <id>` — e.g. `tbf bug 12`, `tbf feat openapi-differ`.

- `type` ∈ `bug | feat | feature | task | chore`.
- `id` = a GitHub issue number or a short descriptive slug.
- Owner is `aliz`.

## Task source: GitHub issue, tolerate absence

Tenon's remote does not exist yet. Expect the fallback inline-brief path.

## Pipeline

### Phase 0 — Isolate in a worktree

**REQUIRED SUB-SKILL:** `tenon-worktrees`. Branch `<type>/<id>/aliz`, worktree dir
`.claude/worktrees/<type>-<id>`, created from `main` (no remote yet).

### Phase 1 — Gather context

Save a raw dump to `docs/planning/_card/issue.md`. If no issue, write the brief.

### Phase 2 — Deep dig

- Map the relevant code paths. Tenon is **greenfield** — today that means
  `docs/technical/CAPABILITY_ROADMAP.md` (T1..T11), `docs/technical/ARCHITECTURE.md`,
  `docs/ROADMAP.md`. Once the engine exists it lives under `src/tenon/`.
- Honor `CLAUDE.md`: a model may *propose* a patch; only running the user's checks
  decides the proof level. No "verified" PR without the level it actually reached.
  Tenon never touches `main`, never merges.
- Place the work in the pipeline (T1 detect, T2 locate, T3 propose, T4 prove, T5
  PR, T6 TS/JS locator, T7 proof ladder, T8 MCP/probe, T9 benchmark, T10 provider
  layer, T11 more languages).

### Phase 3 — Requirements interview

**REQUIRED SUB-SKILL:** `prd-interview`. Confirm a descriptive kebab-case slug.

### Phase 4 — Generate & self-critique the PRD

**REQUIRED SUB-SKILL:** `prd-generator`.

### ⛔ Review gate — STOP

### Phase 5 — Implementation plan

**REQUIRED SUB-SKILL:** `tech-plan`.

### Phase 6 — Implement (TDD, agents team)

**REQUIRED SUB-SKILL:** `superpowers:test-driven-development`,
`superpowers:subagent-driven-development`.

- `uv run pytest` after each task. Any model proposer sits behind an injectable
  seam with recorded fixtures in CI — no real model call, no live API call.
- Commit per task on `<type>/<id>/aliz`.

## Artifact layout

```
docs/planning/
├── _card/issue.md
├── {slug}/prd.md
└── {slug}/{aspect}/plan_*.md
```

## Common mistakes

| Mistake | Fix |
|---|---|
| Working in the primary checkout | Create the Phase 0 worktree first |
| Branching from anything but `main` | No remote exists yet; use local `main` |
| Treating a missing `pyproject.toml` as fatal | Greenfield — scaffold it, test-first |
| Skipping the review gate | PRD must be approved before tech-plan |
| Letting a model's patch stand in as proof | Stop and flag — only the proof runner decides |
| Opening a PR against `main` directly, or merging it | Never — Tenon proposes, humans merge |
