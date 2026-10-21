---
name: tech-plan
description: Create a phased technical implementation plan from planning artifacts in docs/planning (PRD + aspect spec). Use after prd-interview when ready to execute a specific aspect. Triggers on "tech plan", "implementation plan", "plan from PRD".
tags:
  - planning
  - documentation
metadata:
  status: trial
---

Create a phased technical implementation plan from planning artifacts under `docs/planning/{slug}/`.
This is Phase 5 of `tenon-begin-fast` — the plan it produces is executed in Phase 6 through the agents team under strict TDD.

If artifacts are in context, use them directly. Otherwise, search `docs/planning/*/prd.md` and
`docs/planning/*/*/spec.md`.

Tenon is **greenfield**: today the authoritative reading is `docs/technical/CAPABILITY_ROADMAP.md`
(T1..T11), `docs/technical/ARCHITECTURE.md`, and `docs/ROADMAP.md`; the engine lives under
`src/tenon/` once it exists.

## Handoff Contract

- **Feature requirements source:** `docs/planning/{slug}/prd.md`
- **Aspect requirements source (preferred):** `docs/planning/{slug}/{aspect}/spec.md`
- **Plan output (required):** `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`

## Deliverables

### 1. Project Setup Checklist

Directory/module structure under `src/tenon/`, `tests/`. Dependencies via `uv add`.
**Greenfield:** scaffold `pyproject.toml`/`uv.lock`/`src/` as part of the plan's first phase if
they don't exist — test-first still holds.

### 2. Implementation Phases

Goal, Prerequisites, Files to create/modify, Validation (`uv run pytest <path>`), Commit message.

### 3. File-by-File Build Order

Filepath, one-line purpose, key exports, dependencies.

### 4. Testing Strategy

Unit tests mapped to phases, written first. **Start from the capability's acceptance intent** in
`CAPABILITY_ROADMAP.md` and the aspect `spec.md`. Tests are deterministic, **no network, no real
model call, no live API call** — any proposer or MCP probe sits behind an injectable seam with
recorded fixtures in CI.

### 5. Environment & Determinism

Env vars (BYOK stays in `.env`, never committed). `uv sync`. A proof level must be
reconstructible from the recorded run alone.

### 6. Edge Cases & Error Handling

Name the explicit `UNVERIFIED` cause for anything that fails to evaluate
(`NO_MACHINE_READABLE_CHANGE`, `AMBIGUOUS_CALL_SITE`, `NO_TESTS_FOUND`, `TESTS_FAILED_BEFORE`,
`PATCH_DID_NOT_APPLY`, `REQUIRED_LEVEL_UNREACHED`). A harness failure never silently becomes a
stronger proof level than it earned.

### 7. Agent Execution Notes

Checkpoints for human review, iteration-prone areas, where the agent should ask for clarification.

## Guidelines

- Be extremely explicit. Prefer small, testable increments.
- Don't plan work that lets a model's proposed patch stand in for a passed check — flag it
  against `CLAUDE.md`'s wedge.
- Respect the build order: T2 needs T1; T3-T5 need T1+T2; T6-T8 widen reach; T10 needs T4-T9.

## Edge Cases

- **Greenfield vs. existing codebase**: full setup for greenfield.
- **No aspect spec exists yet**: derive candidates, ask the user to choose, draft `spec.md`.
- **Incomplete PRD**: flag it, recommend `prd-interview`.
- **PRD with flagged gaps**: note in the plan, recommend resolution before the affected phase.
