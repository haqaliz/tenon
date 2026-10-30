# PRD: Bounded `$ref` resolution (T1 follow-on)

- **Slug:** `lazy-ref-resolution`
- **Capability:** T1 follow-on slice, unblocks M0.3
- **Status:** approved for implementation on 2026-10-31
- **Card:** `docs/planning/_card/issue.md`
- **Evidence:** `docs/planning/real-spec-readability/evidence.md`

## Problem Statement

`resolve_refs` replaces every `$ref` with a fully resolved copy. That is correct for a tree and
fatal for a DAG: a schema referenced from two places is duplicated, and the duplication compounds.
Stripe's `v2590` document expands to roughly **652 billion nodes**; `load` never finishes. Every
real vendor spec with shared schemas hits this. T1 cannot be exercised on real input, so M0.3 stays
blocked.

The fix is not "lazy" in the sense of resolving during the diff (which would touch every walker).
It is **resolve once per raw node, share the result**. The document becomes a DAG of about 59k
nodes for Stripe, loads in 0.2s, and the differ already has a component-copy rule that can use
identity instead of hashing.

**For whom:** M0.3, T2/T3/T4 (they need real changes), and every future change source.

## Goals & Success Metrics

1. **Bounded resolution.** A synthetic DAG that would expand to 2^30 nodes resolves to fewer than
   100 objects. Stripe `v2500` resolves in under a second (prototype: 0.2s, 59,342 nodes).
2. **Real diff.** Stripe `v2500` -> `v2596` diffs in under 5 seconds with real records (prototype:
   0.6s, 289 changes, 52 breaking, 1 `renamed`).
3. **No contract regression.** `Change` records, ordering, `unanalyzed`, and the Twilio pair are
   unchanged. `parse`/`load` still return a dict with the same keys and values; only object sharing
   changes.
4. **Determinism.** Same inputs, same records; `to_json()` byte-stable.
5. **No hidden expansion.** No code path serialises the resolved document; the one that did
   (`_component_canons`) is replaced by identity.

## Requirements

### Must have

- **M1 — Memoised resolution.** `resolve_refs` caches by `id(raw_node)`: every dict/list node is
  resolved once and shared. A `$ref` to a cached node returns the same object.
- **M2 — Cycle markers.** A ref whose target is on the current resolution path returns
  `{"$ref": ref}` exactly, as today. No infinite recursion.
- **M3 — DAG contract.** `parse`/`load` return a document whose subtrees may be shared. Document
  that callers must not `json.dumps` the document (the diff output is the serialisable unit).
- **M4 — Identity component copies.** `_SchemaContext` stores the `id()` of each component schema
  from both documents; `is_component_copy` returns true iff both sides are those exact objects.
  Delete `_component_canons`' canonical hashing from the hot path.
- **M5 — Synthetic DAG regression.** A committed fixture with `L0 -> {a: L1, b: L1}`, ..., `L30`,
  loads with fewer than 100 distinct objects and diffs against a changed copy without hanging.
- **M6 — Real evidence.** Stripe `v2500` and `v2596` (`latest/openapi.spec3.json`) load and diff;
  record changes, breaking, `unanalyzed`, the single `renamed`, and elapsed time in
  `docs/planning/lazy-ref-resolution/evidence.md`. The 4.3 MB specs are not committed.
- **M7 — Twilio unchanged.** The committed pair still yields 37 changes, 3 breaking, 0 renames,
  `unanalyzed == ()`.

### Should have

- **S1 — A node-count helper for tests.** An identity-aware walk counting distinct dict/list
  objects, used only in tests.
- **S2 — A test that two refs to the same schema are the same object** (`is`, not `==`).

### Nice to have

- **N1 — A comment on `_canonical`** explaining it is no longer used for component detection.
  One line, if it helps the next reader.

## Data Model

No public type changes. `Change`, `DiffResult`, `Unanalyzed` are untouched. The internal contract of
the resolved document changes from tree to DAG:

```
before:  every $ref -> a fresh resolved copy (tree, exponential on a DAG)
after:   every raw node -> one resolved object, shared (DAG, linear)
```

`components.schemas.<name>` is the same object a `$ref` to that schema resolves to. That identity is
what makes M4 correct.

## API Contract

```python
old = load("stripe-v2500.json")   # dict; subtrees may be shared
new = load("stripe-v2596.json")
result = diff(old, new)           # unchanged
result.changes                    # 289 in the prototype
result.unanalyzed                 # 1,873 in the prototype
```

No new function. `resolve_refs` keeps its signature and its refusal behaviour for external and
unresolved refs.

## Technical Considerations

- **Why memoise by raw node id, not by ref string.** Two pointers can address the same node; identity
  is the property the differ needs. The raw document stays alive for the whole resolution, so ids
  cannot be reused.
- **Why not resolve lazily in the differ.** It would touch every walker and every pointer; memoising
  at ingest is a smaller change with the same asymptotic result. If a future case needs on-demand
  resolution, the DAG is a stepping stone.
- **Why identity copies are correct.** A component copy is, by construction, the same resolved
  object. A structurally equal inline schema is not a copy and should be diffed where it appears.
  This is stricter than the canonical check, not looser.
- **Serialisation risk.** `json.dumps(document)` would expand the DAG exponentially. No production
  path does it; the docstring must say so. Tests count objects by identity, never by JSON.
- **Memory.** 59k nodes for Stripe, shared; the prototype used well under 100 MB.

## Risks & Open Questions

- **Identity semantics could miss a copy.** If two refs to the same target resolve to different
  objects (should not happen with the cache), a component is diffed twice. The synthetic DAG test
  and the real diff counts are the guard.
- **A schema that is a `$ref` to another component** resolves to the same object as its target; both
  ids are in the set. A nested ref is still skipped. Correct, but worth one test.
- **The real diff's 1,873 `unanalyzed` entries** mean much of Stripe is still skipped. That is the
  composition policy, not this card; the M0.3 case only needs the analyzable rename.
- **Open question — should `resolve_refs` be public API?** It is exported today. The DAG contract
  makes it less useful to external callers; keep it, document the sharing.

## Out of Scope

- Semantic `oneOf`/`anyOf` comparison.
- The `format` false positive.
- T3 rule coverage, T2 changes, M0.3 execution.
- Lazy/on-demand resolution inside the differ.
- Performance tuning beyond making the real document usable.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `memoized-resolution` | `resolve_refs` cache by node id, cycle markers, DAG docstring, synthetic DAG fixture and node-count helper. |
| `identity-copies` | `_SchemaContext` identity sets, `is_component_copy` rewrite, removal of canonical hashing from that path, tests. |
| `real-spec-evidence` | Stripe v2500/v2596 run, counts and time, evidence file, Twilio regression, docs update. |
