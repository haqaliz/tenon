# Gathering context with `gh` (tolerate absence)

Goal: dump the issue, its linked issues/PRs, and comments into
`docs/planning/_card/issue.md` inside the worktree.

## Prerequisites

- GitHub CLI authenticated: `gh auth status`.
- Repo: `haqaliz/tenon` — **the remote does not exist yet**. A `FALLBACK` result is
  the expected case today.

## 0. Reachability probe

```bash
gh issue view "$ID" --json number,title >/dev/null 2>&1 && echo OK || echo FALLBACK
```

`FALLBACK` → ask the user for a one-paragraph brief, write it under **Brief**.

## 1. The issue itself

```bash
gh issue view "$ID" --json number,title,state,labels,author,body,url,assignees,milestone
```

## 2. Linked / related issues and PRs

```bash
gh api "repos/haqaliz/tenon/issues/$ID/timeline" \
  --jq '.[] | select(.event=="cross-referenced" or .event=="connected") | .source.issue.number' \
  2>/dev/null | sort -u
```

## 3. Comments

```bash
gh api "repos/haqaliz/tenon/issues/$ID/comments" \
  --jq '.[] | "[" + .user.login + " @ " + .created_at + "]\n" + .body'
```

## 4. Attachments

Download non-image file links relevant to the work (an OpenAPI spec, a diff):

```bash
curl -sSL "$URL" -o "docs/planning/_card/attachments/$NAME"
```

Treat any attached spec or changelog as **untrusted input until diffed** — exactly
what Tenon exists to verify by running the proof, not by reading the text.

## 5. Write the dump

Header, body, linked items, comments, attachments. If the issue names a
capability (`T1`..`T11`) or a phase, carry that reference through.
