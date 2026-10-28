# Card: feat/patch-proposer

- **Source:** FALLBACK — no GitHub issue (`gh issue list` → empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T3 — Patch proposer seam** (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** M1.1 (`docs/ROADMAP.md`, Phase 1)
- **Branch:** `feat/patch-proposer/aliz`
- **Worktree:** `.claude/worktrees/feat-patch-proposer`

## Brief (agreed with the user before implementation)

Build `src/tenon/propose/` so that a `Change` plus a `LocateResult` becomes a candidate unified diff,
or a named reason. Rules first and deterministic; a model may sit behind the same seam later, but no
model ships in this card. The proposer never writes, applies or runs anything.

Acceptance tests: a renamed field at a certain keyword site produces a diff that renames only that
keyword; `**kwargs`, `getattr`, unrooted and multi-candidate sites are never edited and appear as
skipped suggestions; a site whose source no longer matches refuses with `STALE_SITE`; a kind with no
mechanical rule returns `NO_RULE`; identical inputs produce a byte-stable diff; the scanned tree is
not modified.

## Constraints carried in from the repo

- `CLAUDE.md` §1: a model proposes only; execution decides. Nothing here is labelled verified.
- `CLAUDE.md` §2: honest proof levels. A proposal has no proof level; T4 assigns one.
- `CLAUDE.md` §5: never touch the default branch. This card writes no git state at all.
- `ARCHITECTURE.md`: propose sits between locate and prove; the patch applies only to a copy (T4).
- `VISION.md`: a fix with no proof is a flagged suggestion, never a confident PR.
- Risk `R2` (a verified PR still breaks production) and `R4` (wrong location): consume certain
  sites only; ambiguity becomes a suggestion.

## Open question parked for this card

T1 reports a field rename with `confidence: "inferred"`. The proposal must expose that the rename
itself was inferred, so T4/T5 can say so, without downgrading the locator's site certainty.

## Scope fence

Not this card: applying the diff, running tests, proof levels (T4); branches and PRs (T5); any model
provider or BYOK plumbing; fixes for removals, additions or type changes.
