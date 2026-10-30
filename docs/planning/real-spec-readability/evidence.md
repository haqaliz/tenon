# Evidence: real-spec readability (composition skip)

Date: 2026-10-30. Base commit: `bc1358c` (`feat(detect): skip an unanalyzable composition subtree
and record it`). All runs offline after the snapshots were fetched once; the 4.4 MB snapshots are
not committed.

## 1. The real Stripe run: blocked by ref expansion, not composition

Snapshots:

| File | URL |
|---|---|
| v2590 | `https://raw.githubusercontent.com/stripe/openapi/v2590/latest/openapi.spec3.json` |
| v2596 | `https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json` |

`load` on `v2590` **does not finish**. `parse` reads and YAML-parses the 4.4 MB document in 15.3 s;
`resolve_refs` then ran for more than 180 s without completing (aborted by `SIGALRM`). No
`changes` / `breaking` / `unanalyzed` numbers exist for the full document, and none are invented
here. In particular, the top five `unanalyzed` pointers cannot be listed: the run stopped in
`load`, before `diff` produced any.

The cause is not a cycle or a composition keyword. `resolve_refs` inlines every `$ref`
occurrence, and the shared-ref DAG expands exponentially:

| Measure | v2590 | v2596 |
|---|---|---|
| paths | 454 | 454 |
| schemas | 1,701 | 1,701 |
| `$ref` nodes | 4,505 | 4,505 |
| unique ref targets | 1,701 | 1,701 |
| memoised resolved node count | 652,429,909,643 | 652,429,909,643 |
| largest component (`credit_note`) | 32,430,552,892 | 32,430,552,892 |

The raw snapshots carry 2,124 `anyOf` and 354 `oneOf` (no `allOf` or `discriminator`); those are
the subtrees the skip would record once the document can be loaded.

Top five expanded component schemas in both snapshots:

| Schema | Resolved nodes |
|---|---|
| `credit_note` | 32,430,552,892 |
| `customer_balance_transaction` | 15,785,231,906 |
| `checkout.session` | 7,462,586,473 |
| `financial_connections.session` | 5,194,304,292 |
| `quote` | 4,654,629,426 |

The memoised count replays `resolve_refs`' rules (a back-edge to a ref already in the chain counts
as one marker node). A faithful count-only replay of the resolver reached 200,000,000 nodes in
488 s and was still running when stopped at 600 s; a faster list-building replica reached
20,000,001 nodes in 22.75 s. Even at the faster rate the full expansion is about 8.6 days. The
v1-only `openapi/spec3.json` variant is no better: 514,046,971,185 nodes over 1,538 schemas.

This is an ingest/resolver issue, not a composition-readability one. The composition-skip contract
is exercised by the committed fixtures below. M0.3 stays blocked until ref resolution is bounded;
that is a separate performance card, as the PRD anticipated.

## 2. Composition fixture pair

`composition-skip-old.yaml` -> `composition-skip-new.yaml` (`Payment` with a `oneOf` `method` and a
changed sibling `amount`):

| Measure | Value |
|---|---|
| changes | 1 |
| breaking | 1 (`property_type_changed`, `amount` integer -> string) |
| unanalyzed | 1 |
| pointer | `#/components/schemas/Payment/properties/method` |
| reason | `UNSUPPORTED_COMPOSITION` |

No `property_removed` for `method` and no change at the skipped pointer: the skip is not compared
as an empty schema.

The `anyOf`, `discriminator` and non-plain `allOf` tests each record exactly one
`UNSUPPORTED_COMPOSITION` entry and produce no change from the skipped subtree.

## 3. Twilio pair (unchanged)

| Measure | Value |
|---|---|
| changes | 37 |
| breaking | 3 (3 `schema_removed`) |
| renames | 0 |
| unanalyzed | 0 (`()`) |
| load + diff | 0.19 s |

## 4. Remaining blockers for M0.3

1. **Ref expansion (new, blocking).** `resolve_refs` materialises the shared-ref DAG; the Stripe
   document needs roughly 6.5e11 nodes. A lazy or memoised resolution that the differ can walk
   without expanding each occurrence is required before the real run can produce numbers.
2. **T3 rule coverage.** The readable Twilio pair still has zero renames over 2.3 years, so the
   gate has nothing to act on even when a spec loads.
3. **`format` false positives.** `int32 -> int64` is still reported as breaking; out of scope for
   this card.

## 5. Verification

- Full suite: 593 passed (baseline 590).
- `to_json()` byte-stability with skips present is covered by
  `tests/detect/test_record.py::test_to_json_is_byte_stable_across_hash_seeds`.
- No network in the test suite; the Stripe snapshots were deleted before this file was committed.
