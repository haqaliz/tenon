---
name: tenon-report
description: Use when a Tenon unit of work (bug, task, feature) is done and you want a brief, friendly, non-technical completion note saved on Desktop to share with the team.
allowed-tools: Read, Grep, Glob, Bash, Write
arguments: "type id"
---

# Tenon Completion Note

## Arguments

- `type` ∈ `bug | task | feature`
- `id` = the GitHub issue number, or the slug used at begin time

Usage: `/tenon-report bug 12` or `/tenon-report feature openapi-differ`.

## Output

Markdown file saved to `/Users/aliz/Desktop/{type}-{id}-completion.md`.

## The template

```markdown
## #{id} - {Feature or area} - {Short Title}

Hey! Quick note that this one's {verb}.

**What changed (in plain words):**
{One or two friendly sentences. No jargon. No em dashes.}

**See it live:** {link to the PR, or the CLI command}
**Screenshot/video:** {attached, or link}

If anything looks off or you'd like a tweak, just say the word.
```

Verb per type: `bug → fixed`, `task → done`, `feature → shipped`.

## Tone rules

- Plain English. Swap *change record, call-site location, patch proposer, proof
  runner, proof level* for everyday phrasing. "Finds the places your code breaks
  and checks the fix really works" beats "change detection and proof-gated PRs."
- No checklists, no commit hashes, no file paths. **Never use the em dash `—`.**

## Don't over-claim

- Say exactly which proof level a PR reached. Don't call a `TYPES_BUILD_ONLY` PR
  "verified" in plain language — say it only passed a build check, no tests.
- Don't imply Tenon merges anything — it opens a PR; a person merges it.

## Workflow

1. **Get the context.** `gh issue view` / `gh pr view`, or the session's own work.
2. **Distill** into one or two plain sentences.
3. **Pick the "See it live" target**: the PR, or the CLI command
   (`uv run tenon fix <repo> --old SPEC --new SPEC`).
4. **Ask for a screenshot or short video.**
5. **Write** the note.

## Example (feature)

```markdown
## #34 - Upgrader - Keep your code working when an API changes

Hey! Quick note that this one's shipped.

**What changed (in plain words):**
When a vendor changes an API, Tenon now finds every place your code calls it,
tries a fix, and runs your own tests against it before opening a pull request.
The PR says exactly how it was checked, so nothing gets merged on a guess.

**See it live:** run `uv run tenon fix <repo> --old old.json --new new.json`
**Screenshot/video:** attached

If anything looks off or you'd like a tweak, just say the word.
```
