# Spec: real-spec-evidence

**Slug:** `lazy-ref-resolution` · **Aspect 3 of 3** · depends on aspects 1-2.

## Problem slice

Prove the resolver on the document that blocked the gate, record the numbers, and update the
roadmap's blocker note. No network in the test suite; the run is an evidence artifact.

## In scope

- Fetch `latest/openapi.spec3.json` at `v2500` and `v2596` into a scratch cache (not committed).
- Run `load` + `diff`; record:
  - elapsed load and diff time;
  - total changes, breaking count, kind histogram;
  - `len(unanalyzed)` and the top five pointers;
  - the single `renamed` record with its path, before and after.
- `docs/planning/lazy-ref-resolution/evidence.md` with the commands, tags, numbers, and the
  remaining M0.3 steps.
- Update `docs/planning/real-spec-readability/evidence.md` §4: ref expansion is fixed; composition
  skip and T3 coverage are the remaining limits.
- Update `docs/ROADMAP.md` M0.3: from "Blocked: T1 eager `$ref` expansion..." to "Ready: T1 reads
  Stripe `v2500` -> `v2596` (one real rename); the repo run is the next card."
- Update `docs/technical/CAPABILITY_ROADMAP.md` T1 limits: resolution is memoised; the real Stripe
  pair diffs; composition subtrees are still skipped and recorded.
- Twilio regression: 37 changes, 3 breaking, 0 renames, `unanalyzed == ()`.

## Out of scope

- Choosing the real repo, running M0.3, or committing the Stripe specs.
- T3 rules for the rename (the next card).
- Performance beyond the measured run.

## Acceptance criteria

1. `evidence.md` contains load/diff times, change counts, the kind histogram, the `renamed` record,
   and `len(unanalyzed)` with examples.
2. The Stripe run is reproducible from the recorded tags and URLs; no spec file is committed.
3. The old evidence's blocker list is updated, not deleted; the history stays readable.
4. The roadmap no longer says ref expansion blocks M0.3; it says the repo run is next.
5. The Twilio test still passes unchanged.
6. Full suite green (593 baseline plus the new tests).

## Dependencies & sequencing

Last. Needs the resolver and identity changes merged.

## Open questions

- Is `v2500` the right baseline for M0.3? It yields one real rename and 52 breaking records over
  ~96 releases. The next card should confirm the rename exists in the SDK version the repo pins.
