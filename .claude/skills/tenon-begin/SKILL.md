---
name: tenon-begin
description: Use when starting work on a Tenon unit of work (a GitHub issue id or an inline brief) and you need stakeholder proposals (technical + non-technical PDFs with diagrams) before planning. Triggers on "tenon-begin", "tb", "tb bug 12", "tb feat openapi-differ", "begin full".
arguments: "type id"
---

# Tenon Begin (Full Track)

## Overview

Same pipeline as `tenon-begin-fast`, plus a **proposal phase**: diagrams and two
review PDFs for stakeholders, then an approval gate, then planning.

**Invocation:** `tb <type> <id>`.

## Pipeline

**REQUIRED SUB-SKILL:** Use `tenon-begin-fast` for the base pipeline.

Run its **Phase 0 → Phase 4 and the ⛔ PRD review gate exactly as written.**

### Phase A — Proposals (diagrams → PDFs)

See `references/proposals.md`.

1. **Diagram** — `excalidraw`, saved to `docs/planning/{slug}/diagrams/*.excalidraw`.
2. **Export** — `excalidraw-to-svg`.
3. **Write two proposals** in `docs/planning/{slug}/proposals/`.
4. **PDF** — `md-to-pdf`.

### ⛔ Approval gate — STOP

### Final phases — Plan & implement

Run `tenon-begin-fast`'s **Phase 5** then **Phase 6**.

## Artifact layout

```
docs/planning/
├── _card/issue.md
├── {slug}/prd.md
├── {slug}/diagrams/*.excalidraw|.svg
├── {slug}/proposals/<type>-<id>-technical-proposal.{md,pdf}
├── {slug}/proposals/<type>-<id>-non-technical-proposal.{md,pdf}
└── {slug}/{aspect}/plan_*.md
```

## Common mistakes

| Mistake | Fix |
|---|---|
| Writing proposals before the PRD is approved | Phase A starts only after the first ⛔ gate |
| One proposal for both audiences | Always two |
| Overstating what a PR proves | State the proof level it actually reached, never more |
