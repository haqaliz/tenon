---
name: tenon-worktrees
description: Isolate parallel work in the Tenon repo using the Claude Code worktree layout. Use when starting a new bug/feature that should not collide with another running Claude session. Covers branch naming, worktree placement under .claude/worktrees, per-worktree uv setup, and cleanup.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Tenon Worktree Workflow

## When to Use

- Another Claude session is running on a different branch in Tenon.
- You want to run two branches side by side.
- The primary checkout is dirty and switching branches would mix work.

## Layout

```
/Users/aliz/dev/at/tenon/                                    ← primary (main)
/Users/aliz/dev/at/tenon/.claude/worktrees/bug-12/
/Users/aliz/dev/at/tenon/.claude/worktrees/feat-openapi-differ/
```

Verify ignore status: `git check-ignore -v '.claude/worktrees/'` (keep the trailing slash).

## Branch naming convention

`<type>/<id>/<owner>` — owner is `aliz`.

- `bug/12/aliz`
- `feat/openapi-differ/aliz`

Worktree dir drops the slashes: `<type>-<id>`.

## The base branch is `main`

Tenon's base branch is **`main`**. The remote (`git@github.com:haqaliz/tenon.git`)
**does not exist yet**. Branch from local `main` until a remote exists:

```bash
git worktree add -b feat/openapi-differ/aliz .claude/worktrees/feat-openapi-differ main
# once a remote exists:
git fetch origin main
git worktree add -b feat/openapi-differ/aliz .claude/worktrees/feat-openapi-differ origin/main
```

## Creating a worktree

```bash
git worktree add .claude/worktrees/feat-openapi-differ feat/openapi-differ/aliz
# or
claude --worktree feat-openapi-differ   # names the branch worktree-feat-openapi-differ; create
                                          # your own branch first if you need issue/slug naming
```

## Auto-copying gitignored config (`.worktreeinclude`)

No secrets exist yet. Once a `.env` exists for BYOK model-assist keys, create
`.worktreeinclude` and copy manually for bare `git worktree add`.

**Never copy recorded API traffic, change records, or proof runs between
worktrees** — they're tied to the run that produced them.

## Per-worktree setup (Python core — uv)

```bash
cd .claude/worktrees/feat-openapi-differ
uv sync
uv run pytest
uv run tenon --help
```

⚠️ **Greenfield caveat:** no `pyproject.toml` yet. If your work *is* the
scaffolding, the failing test comes first.

## Switching between worktrees

```bash
git -C /Users/aliz/dev/at/tenon worktree list
```

## Cleaning up

```bash
git -C /Users/aliz/dev/at/tenon worktree remove .claude/worktrees/feat-openapi-differ
git -C /Users/aliz/dev/at/tenon branch -d feat/openapi-differ/aliz
```

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `invalid reference: origin/main` | No remote yet | Branch from local `main` |
| Branching from `master` | Tenon's base branch is `main` | Use `main` |
| `uv sync` fails: no `pyproject.toml` | Greenfield | Scaffold test-first, or skip for docs-only work |
| `git worktree add` fails: "already checked out" | Branch checked out elsewhere | `git checkout main` there, retry |
