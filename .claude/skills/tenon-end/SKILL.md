---
name: tenon-end
description: Use when finishing local work on a Tenon unit of work after the PR is merged and you also need a completion report on Desktop. Triggers on "tenon-end", "te", "te bug 12", "te feat openapi-differ", "end full".
arguments: "type id"
---

# Tenon End (Full Track)

## Overview

Same cleanup as `tenon-end-fast`, plus a completion report via `tenon-report`.

**Invocation:** `te <type> <id>`.

## Pipeline

**REQUIRED SUB-SKILL:** `tenon-end-fast`. Run Phase 0 → Phase 2. Base branch `main`.
Phase 3 (release) deferred.

### Phase 4 — Completion report

**REQUIRED SUB-SKILL:** `tenon-report`.

| `te` arg | `tenon-report` arg |
|---|---|
| `bug` | `bug` |
| `task` / `chore` | `task` |
| `feat` / `feature` | `feature` |

### Phase 5 — Comment on the issue (optional)

Skip if no reachable issue.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the report before cleanup | Phases 0–2 first |
| Cleaning up against `master` | Tenon's base branch is `main` |
