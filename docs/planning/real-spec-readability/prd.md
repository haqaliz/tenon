# PRD: Real-spec readability (T1 follow-on)

- **Slug:** `real-spec-readability`
- **Capability:** T1 follow-on slice, unblocks M0.3
- **Status:** approved for implementation on 2026-10-30
- **Card:** `docs/planning/_card/issue.md`
- **Evidence:** `docs/planning/stripe-real-case/evidence.md`

## Problem Statement

T1 is fail-closed: a cyclic `$ref` or a composition keyword it cannot analyze refuses the **entire
document**. That is the right instinct (never silently skip a subtree) with the wrong blast radius.
The M0.3 dig showed the consequence: Stripe's real spec is refused on a `file -> file_link -> file`
cycle, and past that carries 2,124 `anyOf` and 354 `oneOf`; every rich vendor spec is unreadable.
Twilio is readable but has nothing to fix over 2.3 years, so the readable path is empty too.

The gate cannot be attempted until T1 can read a real spec. The fix is not to trust more; it is to
**skip less, and say what was skipped**.

**For whom:** M0.3 (the gate), T2/T3/T4 (they need changes from real documents), and the developer
who must know that a diff is partial.

## Goals & Success Metrics

1. **Readable real specs.** `load` + `diff` on Stripe's `v2590` document succeeds instead of
   refusing; the Twilio pair keeps its exact 37-change, 3-breaking, 0-rename result.
2. **No silent skip.** Every subtree T1 cannot analyze appears in `DiffResult.unanalyzed` with a
   pointer and a closed reason. A diff with skips says so in `to_json()`.
3. **Cycles are bounded, not fatal.** A cyclic `$ref` is left as a marker; the differ records
   `CYCLIC_REF` at that subtree and continues.
4. **Structural refusals stay.** Not-a-spec, unsupported version, unparseable input, external refs
   and unresolved pointers still raise `SpecRefusal`.
5. **No regression.** 569 existing tests, updated only where the refusal contract intentionally
   changed; determinism and byte-stability preserved.

Measured by fixtures in `tests/detect/` plus one manual run against the real Stripe document.

## Requirements

### Must have

- **M1 — `Unanalyzed` contract.** `Unanalyzed(pointer, reason)` with
  `UnanalyzedReason ∈ {CYCLIC_REF, UNSUPPORTED_COMPOSITION, UNRESOLVED_REF}`, frozen and JSON-safe.
- **M2 — `DiffResult.unanalyzed`.** A tuple, defaulting to `()`, ordered by `(pointer, reason)`,
  included in `to_dict()`/`to_json()`. Existing construction `DiffResult(changes)` still works.
- **M3 — Cycle tolerance in ingest.** `resolve_refs` leaves `{"$ref": ref}` in place when the ref is
  already in the current chain, instead of raising. External refs still refuse.
- **M4 — Cycle skip in diff.** A `$ref` marker records `CYCLIC_REF` at its pointer and skips that
  subtree; the rest of the document is diffed.
- **M5 — Composition skip in diff.** `oneOf`, `anyOf`, `discriminator`, and non-plain `allOf` record
  `UNSUPPORTED_COMPOSITION` at their pointer and skip that subtree; siblings and the rest of the
  document are still diffed.
- **M6 — No false records from a skip.** A skipped subtree is never compared as an empty schema. If
  either side is unanalyzable, the pair is skipped; no `property_removed`/`type_changed` is invented.
- **M7 — Dedupe and determinism.** `unanalyzed` is deduplicated by `(pointer, reason)` and sorted;
  `to_json()` is byte-stable across hash seeds.
- **M8 — Real evidence.** A manual run against Stripe `v2590` records the diff counts and the
  `unanalyzed` size; the result is appended to the evidence file. The 4.4 MB spec is not committed.

### Should have

- **S1 — A fixture per skip reason.** A small cycle pair and a small composition pair, committed,
  each asserting the change plus the skip.
- **S2 — `unanalyzed` is empty for clean specs.** The Twilio pair asserts `unanalyzed == ()`.

### Nice to have

- **N1 — `DiffResult.complete` property** (`not unanalyzed`). Not added unless a consumer needs it;
  `not result.unanalyzed` is one line.

## Data Model

```
UnanalyzedReason  CYCLIC_REF | UNSUPPORTED_COMPOSITION | UNRESOLVED_REF

Unanalyzed
  pointer: str      # RFC 6901 fragment pointer to the skipped subtree
  reason: UnanalyzedReason

DiffResult
  changes: tuple[Change, ...]
  unanalyzed: tuple[Unanalyzed, ...] = ()
  to_dict() / to_json()
```

`DiffResult.to_dict()` becomes `{"changes": [...], "unanalyzed": [...]}`. This is an additive change
to the JSON shape; T2/T3 read `.changes` and are unaffected.

## API Contract

```python
from tenon.detect import diff, load

result = diff(load("stripe-v2590.json"), load("stripe-v2596.json"))
result.changes       # analyzable changes, as before
result.unanalyzed    # skipped subtrees, never silent
result.to_json()     # byte-stable; includes both lists
```

## Technical Considerations

- **Skip, don't compare empty.** `_flatten` returns `dict | None`; `None` means "already recorded,
  do not compare". Callers skip the pair. Returning `{}` would manufacture removals.
- **Cycle marker.** Leaving `{"$ref": ...}` in the resolved document is the smallest faithful
  representation: the back-edge adds no new depth, and the pointer in `unanalyzed` says where the
  analysis stopped. Fully inlining by identity would require a visited set through every walk.
- **One policy, one place.** The skip decisions live in `_flatten` and the two `$ref` guards;
  the rest of the differ is unchanged.
- **Refusal vocabulary.** `SpecRefusal` keeps its role for input that cannot be analyzed at all.
  `UNSUPPORTED_COMPOSITION` stays in the refusal enum for compatibility but is no longer raised by
  `diff`; a follow-up may remove it.
- **Determinism.** `unanalyzed` ordering uses the same canonical keys as `changes`.

## Risks & Open Questions

- **A change inside a skipped subtree is invisible.** That is the honest trade: the diff says it
  skipped `#/components/schemas/foo/anyOf`, so a caller can refuse to act or ask for a narrower
  spec. Mitigation: T4/T5 must surface `unanalyzed`; this card only makes it visible.
- **Cycle markers could hide a changed recursive property.** The non-recursive occurrence of the
  same schema is still diffed, so a change in `file` is reported at its first occurrence; only the
  back-edge is skipped.
- **The real Stripe run may still be slow.** 4.4 MB with 1,701 schemas; the manual run records the
  time. If it is unusable, that is a separate performance card, not a readability one.
- **Open question — should `unanalyzed` block a "verified" PR?** Product decision for T5/T7. This
  card provides the data; it does not decide the policy.

## Out of Scope

- Semantic `oneOf`/`anyOf` comparison.
- The `format`-based type false positive (`int32 -> int64` reported as breaking).
- New T3 rules, T5 PR text, CLI output.
- Re-running M0.3 (the next card).
- Performance work beyond making the run finish.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `unanalyzed-contract` | `Unanalyzed`, `UnanalyzedReason`, `DiffResult.unanalyzed`, ordering, JSON, defaults. No ingest or diff changes. |
| `cycle-tolerance` | `resolve_refs` leaves markers; `$ref` guards record `CYCLIC_REF`; small cycle fixture. |
| `composition-skip` | `_flatten` returns `None` and records `UNSUPPORTED_COMPOSITION`; callers skip pairs; composition fixture; real Stripe evidence run. |
