---
name: prd-interview
description: Conduct a collaborative product requirements interview between PM and engineering. Use when turning a brief or feature idea into a structured PRD and aspect-level specs through guided discovery and pressure-testing. Triggers on "prd interview", "requirements interview", "prd-interview".
tags:
  - documentation
  - planning
metadata:
  status: trial
---

# PRD Interview

Conduct a structured product requirements interview to turn a brief or feature idea into a complete PRD.
This is a collaborative exercise — the PM hat brings product context, the engineering hat brings technical reality.
Challenge assumptions. Pressure-test scope. Document what survives.

Do not create files until the Document phase.
If the tool supports a read-only or plan mode, switch to it now.

## Context

This skill is the first step in the brief-to-code pipeline (it's Phase 3 of `tenon-begin-fast`).
Output is a structured PRD plus aspect-level specs that feed directly into `tech-plan`.

**Tenon guardrail:** before documenting, sanity-check the work against `CLAUDE.md`. The moat is
detecting a change from a machine-readable source, locating the affected calls, and **proving**
the fix against a check the user trusts. It is **not** a model drafting a plausible patch and
calling it done. If requirements drift toward "the model wrote it, so it's fixed," flag it in the
interview, not after.

## Discover & Challenge

Read the user's input. Read key files: Tenon is **greenfield** — today that means
`docs/technical/CAPABILITY_ROADMAP.md` (T1..T11), `docs/technical/ARCHITECTURE.md`, and
`docs/ROADMAP.md`, plus `src/tenon/` once it exists.

Then pressure-test. Do not soften these.

- "What happens if we don't build this?"
- "Imagine this launched 6 months ago and failed. What went wrong?"
- "What are we choosing NOT to build if we build this?"

Fill remaining gaps with focused questions, 2-3 at a time:

- **Users & Problem**: Who has this problem? Cost of the status quo?
- **Success**: How measured? Target numbers?
- **Scope**: Explicitly out of scope?
- **Requirements**: Must/should/nice?
- **Technical Fit**: Which capability (`T1`..`T11`) and phase? Dependencies built?
- **Proof impact**: Does this keep the user's own checks as the only thing that decides the
  proof level? Is the PR honest about which level it reached? What's the `UNVERIFIED` path when
  no acceptable proof can run?

**Stop when** the problem is clear, success metrics are measurable, must-haves have testable
criteria, out-of-scope is explicit, and major technical risks are identified.

## Confirm

Summarize and confirm the feature slug (kebab-case, e.g. `openapi-differ`). Do not name the
slug `<type>-<id>`.

## Document

**Filename:** `prd.md`
**Location:** `docs/planning/{slug}/`.

```
docs/planning/{slug}/
├── prd.md
├── {aspect}/
│   ├── spec.md
│   ├── plan_YYYYMMDD.md
│   └── ...
└── ...
```

### PRD structure

- **Problem Statement**, **Goals & Success Metrics**, **User Personas & Scenarios** (Tenon ICP:
  developers whose integrations break silently, teams who want proof before merging a migration),
  **Requirements** (must/should/nice), **Technical Considerations** (name the `T`-capability, the
  proof contract impact), **Risks & Open Questions** (reference `R1`..`R8`), **Out of Scope**.

Include when relevant: Change-Record Schema, Proof Contract, PR Format, Non-Functional Requirements.

After writing, surface open questions. Offer to continue into aspect decomposition.

## Aspect Decomposition Mode

1. Propose aspect candidates, each with a one-line boundary.
2. Confirm aspect names (`kebab-case`).
3. Write or update `docs/planning/{slug}/{aspect}/spec.md`.

Each `spec.md`: problem slice, in-scope requirements, out-of-scope boundaries, acceptance
criteria (testable), dependencies/sequencing, open questions/risks.

## Edge Cases

- **Update existing PRD**: Read, ask what changed, update in place.
- **User says "just write it"**: Write from what you have, flag gaps, include one challenge question.
- **No brief exists**: Run full discovery from conversation.
- **Greenfield with no code to read**: Ground in the roadmap/design docs; say plainly no implementation exists yet.
