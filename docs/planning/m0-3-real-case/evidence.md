# Evidence: the first real end-to-end case (M0.3)

Date: 2026-10-31. Base commit: `0d0cab8` (T1–T4 shipped, plus the mock-assertion T2 slice and the
pinned template test). All runs local; network used once to fetch the two vendor documents and clone
the repo. Nothing under `.cache/` is committed.

## 1. Inputs

| Input | URL / value | SHA-256 |
|---|---|---|
| Stripe spec `v2500` | `https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json` | `2c31317cdff103e4495b5b3501004d9ddc0af61f43b0ab819e2db392eef008f6` |
| Stripe spec `v2596` | `https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json` | `9119e72c7ff8ad142e94f7efa9cf49d8e6eec69df3592e17e8fba15099726ed7` |
| Target repo | `https://github.com/yezz123/stripe-template` at `9d9178c47a191112b86a6ce6edd71962faee80d1` | MIT |

The two committed source files and the licence hash are pinned in
`tests/fixtures/repos/real-stripe-template/PROVENANCE.md`.

Target-repo environment (Python 3.12.13):

```sh
uv venv -p 3.12 .cache/m0-3/venv-yezz
uv pip install -p .cache/m0-3/venv-yezz/bin/python \
  pydantic==1.10.22 fastapi==0.99.1 starlette==0.27.0 httpx==0.27.2 \
  stripe==16.1.0 pytest==9.2.0 pytest-mock==3.17.0 email-validator==2.3.0 \
  python-decouple==3.8 python-dotenv==1.2.4
```

`pydantic` is v1 because the repo imports `BaseSettings` from `pydantic`; `httpx==0.27.2` is needed by
starlette 0.27's `TestClient`.

## 2. The change

T1 `diff(load(v2500), load(v2596))` produced 289 changes, 52 breaking, one rename:

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

The `v2596` schema no longer contains `payment_method_types` and describes the replacement as a
filter, not an explicit list:

> Unlike `payment_method_types`, this acts as a filter on the dynamically computed set of eligible
> payment methods rather than an explicit static list.

The rename is real; the semantics are not equivalent.

## 3. Locate and propose

Config:

```python
LocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
)
```

T2 returned two certain sites and no ambiguity:

| Path | Line | Shape | Symbol |
|---|---|---|---|
| `app/router/v1/payment.py` | 41 | `keyword` | `payment_method_types` |
| `tests/test_payment.py` | 49 | `keyword` | `payment_method_types` |

The second is the mock assertion
`stripe.checkout.Session.create.assert_called_with(payment_method_types=...)`. Before the T2 slice in
this card it was not a site; the production-only patch failed the repo's own test.

T3 proposed exactly two edits:

```diff
--- a/app/router/v1/payment.py
+++ b/app/router/v1/payment.py
@@ -38,7 +38,7 @@
     cancel_url = f"{request['url']['scheme']}://{request['url']['netloc']}/cancel"
 
     checkout_session = checkout.Session.create(
-        payment_method_types=setting.PAYMENT_METHOD_TYPES,
+        allowed_payment_method_types=setting.PAYMENT_METHOD_TYPES,
         mode="setup",
         customer=customer_id,
         success_url=success_url,
--- a/tests/test_payment.py
+++ b/tests/test_payment.py
@@ -46,7 +46,7 @@
     request = {"url": {"scheme": "http", "netloc": "localhost:8000"}}
     url = session_url(customer_id, request)  # noqa: F841
     stripe.checkout.Session.create.assert_called_with(
-        payment_method_types=config.PAYMENT_METHOD_TYPES,
+        allowed_payment_method_types=config.PAYMENT_METHOD_TYPES,
         mode="setup",
         customer=customer_id,
         success_url="http://localhost:8000/success",
```

## 4. The proof run

Command given to T4 (with `STRIPE_API_KEY=sk_test_x` exported):

```sh
.cache/m0-3/venv-yezz/bin/python -m pytest -q -k "not setup_new_method"
```

The interpreter path must be absolute and **not** symlink-resolved: `venv/bin/python` is a symlink to
the uv-managed base interpreter, and `Path.resolve()` drops the venv's site-packages. The first
attempt did exactly that and T4 correctly returned `TESTS_FAILED_BEFORE` with
`No module named pytest`; the clone was untouched.

Result:

| Field | Value |
|---|---|
| `level` | `TESTS_PASSED` |
| `cause` | `null` |
| `patch_applied` | `true` |
| baseline return code | 0 |
| after return code | 0 |
| baseline summary | `5 passed, 2 deselected, 3 warnings in 0.94s` |
| after summary | `5 passed, 2 deselected, 3 warnings in 0.37s` |

The check exercised `tests/test_payment.py::test_session_url` (the changed call path) in both runs.
T4 copied the tree, ran the baseline, applied the two-file diff, and ran the check again; the source
clone at `.cache/m0-3/yezz` was clean afterwards.

## 5. What this proof does not establish

- **The vendor call is mocked.** `test_session_url` patches `stripe.checkout.Session.create`; no live
  Stripe request was made. `TESTS_PASSED` means "the repo's offline tests still pass", not "the new
  field behaves the same against the API".
- **The full suite is red before any patch.** `test_setup_new_method_by_email` and
  `test_setup_new_method_by_id` call the live Stripe API with a fake key and fail on the pristine
  clone. The check deselects exactly those two by name; it is not the full suite.
- **The semantics changed.** The old field listed payment methods explicitly; the new one filters the
  dynamically computed set. The mechanical rename is valid syntax and not behavior-preserving.
- **The repo is a 2024 template**, not a production service, and does not pin `stripe`. This proves a
  code-level rename, not an SDK upgrade or a real customer workload.
- **T4's copy is not a sandbox.** The check is arbitrary code chosen by the operator; the repo's
  dependencies live in a venv outside the copy.

The honest label for this run is `TESTS_PASSED` with a mocked, non-production suite. It is the first
end-to-end result the project has, and it is not stronger than that.

## 6. Reproduction

```sh
mkdir -p .cache/m0-3
curl -sSL --fail -o .cache/m0-3/v2500.json \
  https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json
curl -sSL --fail -o .cache/m0-3/v2596.json \
  https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json
git clone --depth 1 https://github.com/yezz123/stripe-template.git .cache/m0-3/yezz
# create the venv exactly as in section 1, then run the script from the gate plan
STRIPE_API_KEY=sk_test_x uv run python .cache/m0-3/run_gate.py
```

The script is reproduced in `docs/planning/m0-3-real-case/gate-evidence/plan_20261031.md` §Phase 2.

## 7. Verification

- Full Tenon suite: 611 passed.
- The pinned offline test (`tests/locate/test_real_stripe_template.py`) asserts the same two sites,
  the same two-hunk diff, and byte-stability without the vendor documents.
- `.cache/` deleted before the evidence commit; `git status` clean.
