# Spec: rename-inference

**Slug:** `openapi-differ` · **Aspect 4 of 4** · depends on `diff-core`.

## Problem slice

M0.1 requires a `renamed` change kind, and renames are the majority of real breakage (81–97% of
breaking changes are refactorings — `CLAUDE.md`). This aspect is the only producer of
`confidence: "inferred"`, and it must never guess.

## In scope

- A post-pass over the record list: pair `removed` with `added` records of the same family
  (parameter↔parameter, property↔property, endpoint↔endpoint) under the same parent pointer.
- A pair is accepted only when the match is **unambiguous in both directions**: exactly one removed
  candidate for that added record *and* exactly one added candidate for that removed record, and the
  comparison basis agrees — same `type` and `format` (and same HTTP method for endpoints).
- On acceptance, replace the two records with one `renamed` (`before`=old name, `after`=new name,
  `breaking=True`, `confidence="inferred"`).
- Everything unmatched stays as `removed` + `added`, `confidence="certain"`.

## Out of scope

- Fuzzy/similarity scoring, embeddings, model calls (`CLAUDE.md` §5: no unapproved egress; and
  rename inference must be deterministic).
- Cross-family pairing (a removed property renamed to a parameter is not a rename).
- Repairing the pair — that is T3.

## Acceptance criteria

1. One removed property and one added property with the same type/format under the same schema →
   exactly one `renamed`, zero `property_removed`/`property_added`.
2. Two added candidates of the same shape for one removed record → no rename; 3 records retained.
3. Same name, different type → **not** a rename; `property_removed` + `property_added` retained.
4. Rename plus type change → not a rename.
5. An endpoint rename (`/v1/users` → `/v2/users`, same method) is detected; a path change with a
   different method is not.
6. Ordering after the pass is still canonical and `to_json()` still byte-stable.
7. An ambiguity caused by a genuine two-way swap (two removed, two added, all same shape) produces
   zero renames.

## Dependencies & sequencing

Last. Needs `diff-core`'s records and `Change` from `change-record`.

## Open questions

- Endpoint renames with a changed path parameter name (`/users/{id}` → `/users/{user_id}`) are very
  common. Rule says same method + same type — path templates make shape comparison non-trivial.
  Default: normalise `{...}` to a placeholder before comparing, and refuse the pair if the parameter
  count differs.
