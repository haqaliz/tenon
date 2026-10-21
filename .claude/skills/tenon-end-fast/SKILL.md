---
name: tenon-end-fast
description: Use when finishing local work on a Tenon unit of work after the PR is merged and you want to clean up without generating a completion report. Triggers on "tenon-end-fast", "tef", "tef bug 12", "tef feat openapi-differ", "end fast".
arguments: "type id"
---

# Tenon End (Fast Track)

## Overview

Closes out local state after the PR merged: **main → pull → remove worktree →
delete branch**, with release deferred. No report (use `tenon-end` / `te` for that).

**Invocation:** `tef <type> <id>`.

Tenon's base branch is **`main`**.

## Pipeline

### Phase 0 — Safety check

- Worktree clean: `git -C <worktree> status --porcelain` empty.
- Branch merged; `git branch -d` refuses otherwise — don't bypass with `-D` without OK.

### Phase 1 — Main, pulled

```bash
PRIMARY=$(git worktree list | head -1 | awk '{print $1}')
git -C "$PRIMARY" checkout main
git -C "$PRIMARY" pull --ff-only origin main
```

### Phase 2 — Remove worktree, delete branch

```bash
git -C "$PRIMARY" worktree remove ".claude/worktrees/<type>-<id>"
git -C "$PRIMARY" branch -d "<type>/<id>/aliz"
```

### Phase 3 — Release (DEFERRED)

**Tenon has no release machinery yet.** Cleanup ends at Phase 2. When it lands:
`feat` → minor, `bug`/`chore`/`task` → patch; CI green before tagging; tag and
push to trigger the workflow; verify each channel before calling it done.
Release identity: **haqaliz**. PyPI name: `tenon` taken, `tenonhq` free when checked.

### Phase 4 — Comment on the issue (optional)

Ask first, draft, confirm, then `gh issue comment`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Checking out / pulling `master` | Tenon's base branch is `main` |
| Using `git pull` | Use `--ff-only` |
| Forcing branch delete | Only after explicit user OK |
| Cutting a release | Deferred |
