# Card: feat/real-spec-readability

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T1 follow-on slice** — real-spec readability (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** unblocks M0.3 (`docs/ROADMAP.md`)
- **Branch:** `feat/real-spec-readability/aliz`
- **Worktree:** `.claude/worktrees/feat-real-spec-readability`

## Brief

T1 currently refuses an entire document when it meets a cyclic `$ref` or a composition keyword it
cannot analyze. The M0.3 dig (`docs/planning/stripe-real-case/evidence.md`) proved this makes every
rich real vendor spec unusable: Stripe has a `file -> file_link -> file` cycle and 2,124 `anyOf` /
354 `oneOf`.

Change the policy: tolerate cycles by leaving a `$ref` marker, skip only the subtree that carries an
unsupported construct, and record every skipped subtree in a new `DiffResult.unanalyzed` list so
nothing is silent. Keep refusing input that is not a spec, an unsupported version, unparseable YAML,
external refs, and unresolved pointers.

Acceptance: the real Stripe v2590 spec loads and diffs with a non-empty `unanalyzed` list; the
committed Twilio pair still yields 37 changes and an empty list; a cycle fixture and a composition
fixture each produce their change plus their recorded skip; the full suite is green; output stays
byte-stable.

## Constraints carried in from the repo

- `CLAUDE.md` §3: machine-readable sources first. This card widens what counts as readable, not what
  counts as trusted.
- `ARCHITECTURE.md`: "never silently skip a subtree". A recorded `unanalyzed` list is the price of
  skipping; the alternative (refuse everything) is what this card removes.
- `VISION.md`: honest labels. A diff with skipped subtrees must say so.
- Risk `R3` (machine-readable changes are rare): this card is the precondition for measuring it.

## Scope fence

Not this card: semantic `oneOf`/`anyOf` comparison; the `format`-based type false positive; any T3
rule; re-running M0.3 (the next card).

## Outcome (2026-10-30)

- **Shipped:** `DiffResult.unanalyzed`, cycle tolerance (`$ref` markers + `CYCLIC_REF`), and
  per-subtree composition skip (`UNSUPPORTED_COMPOSITION`). 593 tests green.
- **Not met:** the real Stripe document still cannot load. With cycles and composition handled,
  `resolve_refs` remains the blocker: eager inlining of the shared-ref DAG expands to ~652 billion
  nodes (evidence: `docs/planning/real-spec-readability/evidence.md`).
- **Next:** `lazy-ref-resolution` (T1 resolver), then re-run M0.3. The gate stays blocked.
