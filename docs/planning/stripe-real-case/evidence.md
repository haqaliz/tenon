# M0.3 evidence: the first real case

Date: 2026-10-30. Base commit: `4ba0b83` (T1-T4 shipped). All runs offline after the snapshots were
fetched once.

## 1. Stripe: the richest source, refused by T1

Snapshots fetched from `stripe/openapi` at tags `v2590` and `v2596`:

| File | URL |
|---|---|
| v1 only | `https://raw.githubusercontent.com/stripe/openapi/v2590/openapi/spec3.json` |
| v1 + v2 | `https://raw.githubusercontent.com/stripe/openapi/v2590/latest/openapi.spec3.json` |

`tenon.detect.load` on `v2590`, both variants:

```
UNRESOLVED_REF at #/components/schemas/file:
  cyclic $ref: #/components/schemas/account
    -> #/components/schemas/legal_entity_company
    -> #/components/schemas/legal_entity_company_verification
    -> #/components/schemas/legal_entity_company_verification_document
    -> #/components/schemas/file
    -> #/components/schemas/file_link
    -> #/components/schemas/file
```

Composition in the same document, counted by walking every object:

| Spec | `anyOf` | `oneOf` | `allOf` | `discriminator` | paths | schemas |
|---|---|---|---|---|---|---|
| `latest/openapi.spec3.json` | 2,124 | 354 | 0 | 0 | 454 | 1,701 |
| `openapi/spec3.json` | 2,124 | 322 | 0 | 0 | 431 | 1,538 |

T1 refuses `oneOf`/`anyOf`/`discriminator` at the pointer that carries them
(`UNSUPPORTED_COMPOSITION`). Resolving the cycle alone would not make this spec readable.

## 2. Twilio: readable, but no change T3 can fix

Snapshots from `twilio/twilio-oai` at tags `2.0.0` (2024-06-18) and `2.10.0` (2026-10-12), files
under `spec/json/`. All three product specs have **no** `oneOf`, `anyOf`, `allOf` or `discriminator`
and load without refusal.

| Product | changes | breaking | breaking kinds |
|---|---|---|---|
| `twilio_lookups_v2` | 37 | 3 | 3 `schema_removed` |
| `twilio_verify_v2` | 32 | 11 | 10 `parameter_type_changed` (`integer` -> `int64`), 1 `property_type_changed` (`conversion_rate` number -> string) |
| `twilio_api_v2010` | 113 | 79 | 61 `parameter_type_changed` (`integer` -> `int64`), 10 `schema_removed`, 7 `property_removed`, 1 `property_type_changed` |

The seven `property_removed` records are response pagination fields on
`GET /2010-04-01/Accounts/{AccountSid}/AvailablePhoneNumbers.json`: `first_page_uri`,
`next_page_uri`, `previous_page_uri`, `end`, `page`, `page_size`, `start`.

**Across 2.3 years and 113 changes: zero `renamed`, zero `endpoint_removed`, zero `parameter_removed`,
zero `*_required_added`.** Nothing T3's single rename rule can turn into a patch. The type records
are `int32 -> int64` format noise, which does not need a code change; the removed pagination
properties are read as attributes on a response object, which T2's operation-scoped field matching
does not connect to a certain site.

## 3. What this means for the gate

The gate is *one real API change, one real repo, one patch that passes a real check*. It is not met.
The blocker is not the repo choice; it is the capability set:

1. **T1 cannot read the vendor with rich, frequent changes.** The fail-closed composition policy
   (correct by its own guardrail) makes every large real spec unusable. This is the first blocker.
2. **Even with a readable spec, T3 has one rule.** Two years of the readable vendor produced no
   change that rule can apply. This is the second blocker, visible only after the first is fixed.

The evidence is committed as `tests/fixtures/specs/twilio-lookups-2.0.0.json` and `-2.10.0.json`,
with `tests/detect/test_real_twilio_specs.py` pinning the 37-change, 3-breaking, 0-rename result.

## 4. Candidate follow-ons

| Option | What it buys | Cost / risk |
|---|---|---|
| **A. T1 real-spec policy** | Decide cycles and composition: refuse a subtree with a recorded `unanalyzed` list, or support `oneOf`/`anyOf` semantically. Unblocks every rich vendor spec. | Large; changes a guardrail ("never silently skip a subtree") and the refusal contract. |
| **B. T3 rule coverage** | Add a rule for the class the first real case actually needs. | Useless until A lands; the readable spec has no such change today. |
| **C. Another vendor** | Maybe a readable spec with a request-field rename. | Two vendors tried; the odds are unquantified, and the search cost is unbounded. |

Recommendation: **A**, as its own card (`real-spec-readability`), with the Stripe and Twilio snapshots
as acceptance fixtures, then re-run M0.3. The gate stays open until then.
