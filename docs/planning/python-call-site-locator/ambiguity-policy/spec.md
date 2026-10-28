# Spec: ambiguity-policy

**Slug:** `python-call-site-locator` · **Aspect 4 of 4** · depends on `locate-result`, `symbol-contract`, `python-scan`.

## Problem slice

The locator's product value is not recall, it is refusing to claim what it cannot see. This aspect
is the only place that converts scan evidence and a query into `certain` and `ambiguous` lists. It
is deliberately small and table-tested: every rule that could turn a guess into a certainty lives
here, in one readable file.

## In scope

- `resolve(query, scan, config) -> LocateResult`, plus the `locate(change, root, config)` wrapper
  that derives the query, scans, and resolves.
- Result ordering and serialization come from aspect 1; this aspect only builds the values.
- Rule order (first match wins, all rules deterministic):
  1. `query.reason` → pass it through, both lists empty.
  2. No scanned modules → `NO_SDK_IMPORT`.
  3. `scope="operation"`:
     - If `query.origin == "none"` → `OPERATION_NOT_MAPPED`.
     - Resolve operation candidates against `chain` of rooted `call` hits. Two or more distinct
       candidates resolving → one `MULTIPLE_CANDIDATES` group holding all those call sites.
       Zero → `DYNAMIC_GETATTR` when a `getattr` dynamic names one of the candidate leaves (the
       dynamic's own site is the candidate), else `NO_SITES`.
     - With a field:
       - `field_presence="must_exist"` (removed, renamed, type-changed): certain = rooted
         `keyword`/`dict_key` hits with `symbol == field_name` and `chain == resolved chain`.
         A resolved call with `star_kwargs` → `DYNAMIC_KWARGS` group with the call site.
       - `field_presence="must_be_added"` (added, required-added): certain = the resolved call
         sites themselves (the fix is an added argument), and rooted keyword hits for the field are
         also certain when already present.
       - A `getattr` dynamic naming the field → `DYNAMIC_GETATTR` group.
  4. `scope="component"`: match `symbol == field_name` across shapes.
     - Rooted `keyword`/`dict_key`/`attribute` hits → certain.
     - Non-rooted hits → `UNROOTED_RECEIVER` group with candidates.
     - Rooted but reached through an `alias_chain` → `ALIAS_CHAIN` group.
     - Nothing → `NO_SITES`.
  5. If no field name could be extracted and the query is not an operation query, the query itself
     carries `UNSUPPORTED_CHANGE_KIND` (aspect 2), so this aspect never invents one.
- Invariants enforced at construction: a hit is never both certain and a candidate; a group reason
  is from the closed enum; `UNMAPPED_SYMBOL` is used when a component-scoped field has rooted hits
  only under a different spelling than the mapped name (i.e. the map says `amount_cents`, the repo
  says `amount`), so the caller sees both.
- `AMBIGUOUS_CALL_SITE` is the aggregate cause T4/T5 report (`docs/technical/ARCHITECTURE.md`); T2
  does not emit it. Any non-empty `ambiguous` list maps to it in one line at the T4 boundary.

## Out of scope

- Producing more certainty than the scan supports (no re-scanning, no fuzzy name matching).
- Choosing between candidates, or ranking them.
- T4 proof levels, `UNVERIFIED` causes beyond the aggregate mapping note.
- Human-readable explanations; the reason enum is the explanation.

## Acceptance criteria

1. **Decoy, the core test.** In a reachable module, `amount=1` passed to a non-SDK function is never
   certain; it appears only as an `UNROOTED_RECEIVER` candidate or not at all. In a non-reachable
   module it does not appear at all.
2. `client.charges.create(amount=1)` for a `renamed` `amount → amount_cents` on operation scope is
   certain, at the right line and column.
3. `client.charges.create(**row)` for the same change is `DYNAMIC_KWARGS` with the call site as a
   candidate, and produces no certain site.
4. `getattr(client.charges, "delete")("ch")` for `endpoint_removed DELETE /v1/charges/{id}` with a
   mapping is `DYNAMIC_GETATTR`, never certain.
5. A `GET /v1/customers/{id}` change in a repo where both `customers.get(...)` and
   `customers.retrieve(...)` are called → `MULTIPLE_CANDIDATES`, all sites kept.
6. A `parameter_required_added` on an operation returns its resolved call sites as certain, with no
   field-name requirement.
7. An unsupported kind returns `UNSUPPORTED_CHANGE_KIND` with both lists empty; a change with no
   matching sites returns `NO_SITES`; the two are distinguishable.
8. The same inputs produce byte-identical `to_json()`; a result with reasons and sites never
   constructs (aspect 1 invariant holds through this code path).
9. Property-style table over the 10 supported kinds × 4 shapes: no unhandled combination, no
   exception, and every non-empty result has a resolvable reason for each ambiguous group.

## Dependencies & sequencing

Last. Needs aspects 1-3 complete; it is the only aspect that should contain certainty logic.

## Open questions

- Should an `UNROOTED_RECEIVER` candidate ever be promoted to certain when the module imports the
  SDK but the receiver is a local wrapper (`class Client: def create(self): self._sdk...`)? Current
  answer: no — that is exactly the case a wrong patch looks right in. Revisit only with evidence
  from M0.3.
