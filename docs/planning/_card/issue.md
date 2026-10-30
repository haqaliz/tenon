# Card: feat/stripe-real-case

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Milestone:** **M0.3 — one end-to-end case** (`docs/ROADMAP.md`, the Phase 0 gate)
- **Capabilities exercised:** T1-T4 (all shipped)
- **Branch:** `feat/stripe-real-case/aliz`
- **Worktree:** `.claude/worktrees/feat-stripe-real-case`

## Brief (from the `tenon-next` handoff)

Vendor two dated Stripe OpenAPI snapshots and diff them with T1; pick a real OSS Python repo at a
pinned commit that uses the Stripe SDK and has a green test command. Run the whole pipeline through
the Python API and write an evidence record stating the repo, commit, spec versions, exact command,
proof level, cause, and every skipped site. If the outcome is `UNVERIFIED`, end with a scoped
follow-on slice and do not claim the gate.

## Dig result (2026-10-30)

**The gate is blocked before the repo choice, by T1's real-spec policy.** Details and exact counts
are in `docs/planning/stripe-real-case/evidence.md`.

1. **Stripe refuses at load.** Both the v1-only and the v1+v2 spec at tag `v2590` raise
   `UNRESOLVED_REF` on a cyclic `$ref` (`file -> file_link -> file`). Even if cycles were resolved,
   the same document carries 2,124 `anyOf` and 354 `oneOf`, which T1 refuses wholesale by policy.
2. **Twilio is readable but yields nothing T3 can fix.** `twilio_lookups_v2`, `twilio_verify_v2`
   and `twilio_api_v2010` load and diff cleanly between tags `2.0.0` (2024-06-18) and `2.10.0`
   (2026-10-12). Across 113 changes in `api_v2010` there are **no `renamed`, no endpoint removals
   and no parameter removals**; the breaking records are `int -> int64` format noise, ten removed
   enum schemas, one format change, and seven response pagination properties.
3. **No repo was chosen.** Picking one would not change the outcome: the change classes above are
   either not locatable as certain sites (response attributes) or have no rule in T3.

## Committed evidence

- `tests/fixtures/specs/twilio-lookups-2.0.0.json` and `-2.10.0.json` — the first real vendor spec
  pair in the repository, offline.
- `tests/detect/test_real_twilio_specs.py` — pins the real diff: 37 changes, three breaking schema
  removals, zero renames.

## Constraints carried in from the repo

- `CLAUDE.md` §2: the gate is not met on an `UNVERIFIED` outcome; do not dress this up as a pass.
- `CLAUDE.md` §3: machine-readable sources only; no changelog parsing.
- `ARCHITECTURE.md`: T1 refuses rather than silently skipping a subtree. The refusal is doing its
  job; the policy is the question.

## Scope fence

Not this card: implementing composition or cycle support in T1 (a follow-on), choosing a different
vendor to force a green run, or weakening the gate's definition.
