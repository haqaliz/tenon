---
name: tenon-next
description: Use when deciding what to build next in Tenon and you want the single highest-leverage capability picked from the repo's own roadmap and planning files (not invented), grounded in the moat and in what has already shipped or been deferred, ending with a ready-to-run handoff. Triggers on "tenon-next", "tn", "what's next", "next feature", "pick next".
arguments: ""
---

# Tenon Next (pick the most important capability)

## Overview

Read the repo's own roadmap and planning files, rank the real candidate capabilities
against the moat and against what has shipped or been deferred, and recommend the
single highest-leverage one to build next. End with a ready-to-paste
`tenon-begin-fast` invocation.

This skill RECOMMENDS and hands off. It does NOT create a worktree itself.

## When to use

- "what should I build next", at the start of a session.
- Not for: executing a chosen capability (use `tenon-begin-fast`), or planning an
  already-chosen one (use `prd-interview` / `tech-plan`).

## The candidate set is the FILES, never invented

- `docs/technical/CAPABILITY_ROADMAP.md`: the **T1..T11** engine capabilities in
  build order. The primary candidate set.
- `docs/ROADMAP.md`: the phases, milestones, and **R1..R8 risk register**.
- `CLAUDE.md` and `VISION.md`: the wedge, the moat, the guardrails.
- `docs/technical/ARCHITECTURE.md`: the detect → locate → propose → prove → PR design.
- `docs/planning/*/`: in-flight, completed, and deferred work, once any exists.
- `git log` / the test suite: what actually shipped. **Today there are no commits
  beyond the scaffold** — say so plainly.

If a file is missing, reference it by path and say it isn't written yet.

## How to rank (grounded in CLAUDE.md)

1. **Execution-grounded proof only.** A candidate that lets a model's patch stand
   in for a passed check is dropped.
2. **Respect the build order.** T2 needs T1; T3-T5 need T1+T2; T6-T8 widen reach
   after the core works; T10 needs T4-T9.
3. **T1+T2 unblock the first end-to-end case; T4 (the proof runner) is the moat.**
4. **The gate beats the feature.** Before Phase 0's gate (one real API change, one
   real repo, one patch that passes a real check), that gate is the priority.
5. **Follow-on slices count.** A new proof level, a new language locator.

## Process

1. Read the files above. Build the candidate list.
2. For each candidate: shipped-state (cite the file), dependency status,
   moat-leverage, the risk it retires (by R-id), any known blocker.
3. Rank. Pick ONE, plus one or two alternates.
4. Sanity-check against the guardrails and the current phase gate.
5. Produce the handoff.

## Output format

- **The pick**: one line naming the capability (with its T-id) and a kebab-case slug.
- **Why**: 2 to 3 bullets.
- **Alternates.**
- **Known caveat**: nearest feasibility risk (R-id).
- **Handoff prompt**: a `tbf feat <slug>` line plus a 3 to 5 sentence brief,
  including the capability's acceptance tests.

## Honesty rules

- Ground every claim in a named file. Say "not started" rather than implying progress.

## Common mistakes

| Mistake | Fix |
|---|---|
| Inventing a capability not in the docs | The candidate set is T1..T11 |
| Recommending a capability whose dependencies are unbuilt | Check the dependency line |
| Recommending a model-proposed patch as proof | Drop it — the proof runner decides |
| Reaching for T10 (provider/hosted) early | It depends on T4-T9 |
| Starting the worktree from this skill | Only recommend; the user runs `tbf` |
