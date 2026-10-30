# Evidence: bounded `$ref` resolution on the real Stripe pair

Date: 2026-10-31. Base commit: `f696156` (`feat(detect): detect component copies by identity`).
One run on the real code; the two snapshots were downloaded once and are not committed. No
production code changed for this evidence.

## 1. Commands

```sh
mkdir -p .cache
curl -sSL --fail -o .cache/v2500.json \
  https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json
curl -sSL --fail -o .cache/v2596.json \
  https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json
.venv/bin/python .cache/run_evidence.py
```

| Tag | URL | Bytes | SHA-256 |
|---|---|---|---|
| `v2500` | `https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json` | 4,518,735 | `2c31317cdff103e4495b5b3501004d9ddc0af61f43b0ab819e2db392eef008f6` |
| `v2596` | `https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json` | 4,663,536 | `9119e72c7ff8ad142e94f7efa9cf49d8e6eec69df3592e17e8fba15099726ed7` |

Both tags exist; the `latest/` path inside a release tag is immutable. The runner times `load` per
document, then `diff`:

```python
import time
from tenon.detect import diff, load

start = time.perf_counter(); old = load(".cache/v2500.json"); print("load v2500", time.perf_counter() - start)
start = time.perf_counter(); new = load(".cache/v2596.json"); print("load v2596", time.perf_counter() - start)
start = time.perf_counter(); result = diff(old, new); print("diff", time.perf_counter() - start)
print(len(result.changes), sum(c.breaking for c in result.changes), len(result.unanalyzed))
```

Python 3.13.15 on macOS 26.5 (arm64). Times are one run, not a benchmark.

## 2. Times

| Step | `v2500` | `v2596` |
|---|---|---|
| read + `yaml.safe_load` | 3.618 s | 4.246 s |
| `resolve_refs` (memoised) | 0.055 s | 0.065 s |
| `load` end to end | 3.81 s | 4.21 s |
| `diff` | 0.231 s | — |
| distinct resolved dict/list nodes | 57,633 | 59,580 |

Load is dominated by PyYAML parsing a JSON document; resolution itself is 55-65 ms and the DAG
stays linear (57k-60k nodes). Both loads are under the 5 s plan threshold, so no tuning was done.
The prototype's 0.2 s figure used `json.load` (0.02 s) plus the same resolver, not `load`'s YAML
parse.

## 3. Diff result

| Measure | Value |
|---|---|
| changes | 289 |
| breaking | 52 |
| renames | 1 |
| `len(unanalyzed)` | 1,873 |

Kind histogram:

| Kind | Count |
|---|---|
| `endpoint_added` | 18 |
| `property_added` | 130 |
| `property_removed` | 43 |
| `property_required_added` | 4 |
| `property_type_changed` | 2 |
| `renamed` | 1 |
| `schema_added` | 89 |
| `schema_removed` | 2 |

## 4. The renamed record

```json
{
  "kind": "renamed",
  "location": {
    "method": "post",
    "path": "/v1/checkout/sessions",
    "pointer": "#/paths/~1v1~1checkout~1sessions/post/requestBody/content/application~1x-www-form-urlencoded/schema/properties"
  },
  "before": "payment_method_types",
  "after": "allowed_payment_method_types",
  "breaking": true,
  "confidence": "inferred"
}
```

This is the one rename a T3 rule could target: a request-body field rename on
`POST /v1/checkout/sessions`.

## 5. What was skipped, and why

`unanalyzed` holds 1,873 entries: 1,867 `UNSUPPORTED_COMPOSITION` and 6 `CYCLIC_REF` (back-edge
markers from `resolve_refs`). Top five pointers:

| Pointer | Reason |
|---|---|
| `#/components/schemas/account/properties/business_profile` | `UNSUPPORTED_COMPOSITION` |
| `#/components/schemas/account/properties/external_accounts/properties/data/items` | `UNSUPPORTED_COMPOSITION` |
| `#/components/schemas/account/properties/groups` | `UNSUPPORTED_COMPOSITION` |
| `#/components/schemas/account/properties/settings` | `UNSUPPORTED_COMPOSITION` |
| `#/components/schemas/account_branding_settings/properties/icon` | `UNSUPPORTED_COMPOSITION` |

That is the composition policy from `real-spec-readability`, not this card. The one analyzable
rename is enough to exercise the M0.3 path.

## 6. Twilio pair (unchanged)

`tests/detect/test_real_twilio_specs.py` still passes unchanged: 37 changes, 3 breaking (all
`schema_removed`), 0 renames, `unanalyzed == ()`.

## 7. What this does **not** do

- **No repo chosen.** No SDK repo was inspected, and no call site was located.
- **No patch.** T3 has not proposed a fix for `payment_method_types`; the rename record is the
  input to that step.
- **No proof.** No repo tests ran, so no `TESTS_PASSED` / `UNVERIFIED` label exists.
- **No gate.** M0.3 is ready, not done.

Remaining M0.3 steps: pick a repo pinned to an SDK version that contains this rename; run T2 on
`POST /v1/checkout/sessions` + `payment_method_types`; run T3/T4 and record the proof level.

## 8. Verification

- Full suite: 602 passed.
- No network in `tests/`; `.cache/` (snapshots and runner) was deleted before this file was
  committed.
