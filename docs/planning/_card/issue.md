# Card: feat/lazy-ref-resolution

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T1 follow-on slice** — bounded `$ref` resolution (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** unblocks M0.3 (`docs/ROADMAP.md`)
- **Branch:** `feat/lazy-ref-resolution/aliz`
- **Worktree:** `.claude/worktrees/feat-lazy-ref-resolution`

## Brief

`resolve_refs` inlines every `$ref` occurrence. On a real vendor DAG that is exponential: Stripe's
`v2590` document expands to ~652 billion nodes and never loads. Replace the expansion with
memoisation by node identity: every raw node resolves once, refs share the resolved object, and a
back-edge stays a marker. Replace the canonical-JSON component-copy detection with identity checks,
which is what the DAG makes possible.

Acceptance: a synthetic 30-level two-ref DAG (2^30 nodes under eager resolution) resolves to fewer
than 100 nodes and diffs; Stripe `v2500` -> `v2596` loads and diffs in seconds with real changes;
the Twilio pair is unchanged; the full suite is green; output stays deterministic.

## Constraints carried in from the repo

- `CLAUDE.md` §3: machine-readable sources first. This card makes the existing source readable; it
  does not add a new source.
- `ARCHITECTURE.md`: "Change record is the unit". The resolved document's internal sharing must not
  leak into `Change`.
- `VISION.md`: honest labels. The `unanalyzed` list stays the record of what was skipped.
- Risk `R3` (machine-readable changes are rare): the real Stripe diff found a request rename
  (`payment_method_types` -> `allowed_payment_method_types`), so the next card can attempt M0.3.

## Scope fence

Not this card: semantic `oneOf`/`anyOf`, the `format` false positive, T3 rules, choosing the real
repo or running M0.3 (the next card).
