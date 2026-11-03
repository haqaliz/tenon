# Evidence: M0.3 — the first real case

Date: 2026-11-02. Tenon code: `71fef09` (T1-T4 shipped; this card adds no `src/tenon/` change).
The run was executed once; times are one run on a busy machine, not a benchmark.

## 1. The change

Stripe OpenAPI snapshots at tags `v2500` and `v2596`, both from the immutable `latest/` path inside
the tag:

| Tag | URL | Bytes | SHA-256 |
|---|---|---|---|
| `v2500` | `https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json` | 4,518,735 | `2c31317cdff103e4495b5b3501004d9ddc0af61f43b0ab819e2db392eef008f6` |
| `v2596` | `https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json` | 4,663,536 | `9119e72c7ff8ad142e94f7efa9cf49d8e6eec69df3592e17e8fba15099726ed7` |

`diff` produced 289 changes, 52 breaking, and exactly one rename:

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

## 2. The repository

| | |
|---|---|
| Repository | `https://github.com/fighthealthinsurance/fighthealthinsurance` |
| Default branch | `main` |
| Pinned commit | `56e69cfa4440aea0a42d016f84e6af336c5e0d3c` (pushed 2026-10-31) |
| Size | ~69 MB |
| Check | `tests/sync/test_pwyw_checkout.py` (12 tests, Django + SQLite in memory) |

The repo is a real Django application. It calls `stripe.checkout.Session.create(...)` directly with
`payment_method_types=["card"]` in three places. Its focused test file mocks the SDK call and runs
offline.

## 3. Locate

Configuration:

```python
LocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
)
```

Without the `operations` entry, `derive` infers `checkout.sessions.create` from the path (lowercase,
plural resource segment). The SDK chain is `checkout.Session.create` (capitalized class, singular),
so the inferred candidate matches nothing: `locate` returns `NO_SITES`. The explicit mapping is the
supported escape hatch from T2 and was required for this endpoint.

With the mapping, `locate` found three certain sites, no ambiguity groups, no reason:

| Path | Line | Column | Shape | Symbol |
|---|---|---|---|---|
| `fhi_users/auth/rest_auth_views.py` | 754 | 13 | `keyword` | `payment_method_types` |
| `fighthealthinsurance/views.py` | 3904 | 17 | `keyword` | `payment_method_types` |
| `fighthealthinsurance/views.py` | 4177 | 13 | `keyword` | `payment_method_types` |

## 4. Propose

`propose` verified all three spans and rendered one diff with three edits. The diff applies with
`git apply -p1` in the isolated copy:

```diff
--- a/fhi_users/auth/rest_auth_views.py
+++ b/fhi_users/auth/rest_auth_views.py
@@ -751,7 +751,7 @@
 
         subscription_metadata.update(tracking_metadata_for_request(request))
         checkout_session = stripe.checkout.Session.create(
-            payment_method_types=["card"],
+            allowed_payment_method_types=["card"],
             line_items=line_items,  # type: ignore
             mode="subscription",
             success_url=continue_url,
--- a/fighthealthinsurance/views.py
+++ b/fighthealthinsurance/views.py
@@ -3901,7 +3901,7 @@
             else:
                 line_items = StripeRecoveryInfo.objects.get(id=recovery_info_id).items
             checkout_session = stripe.checkout.Session.create(
-                payment_method_types=["card"],
+                allowed_payment_method_types=["card"],
                 line_items=line_items,  # type: ignore
                 mode="payment",
                 success_url=continue_url or "https://www.fighthealthinsurance.com",
@@ -4174,7 +4174,7 @@
 
         # Create a checkout session with the specified amount
         checkout_session = stripe.checkout.Session.create(
-            payment_method_types=["card"],
+            allowed_payment_method_types=["card"],
             line_items=line_items,  # type: ignore
             mode="payment",
             success_url=success_url,
```

## 5. Prove

T4 copied the repo, ran the baseline, applied the diff, and ran the check again. The copy drops
`.venv`, so the check used an interpreter outside the copy:

```sh
.cache/venv-fhi/bin/python -m pytest tests/sync/test_pwyw_checkout.py -q
```

Environment: Python 3.13.15, `stripe==12.2.0`, `Django==5.2.18`, `pytest==9.2.0`,
`setuptools==79.0.1`, `TESTING=True`. The venv was built with
`uv pip install -r requirements.txt` from the target repo.

| Field | Value |
|---|---|
| Level | **`TESTS_PASSED`** |
| Cause | — |
| Patch applied | `true` |
| Baseline | 12 passed, exit 0, 125.25 s |
| After | 12 passed, exit 0, 72.05 s |
| Total `prove` | 229.5 s (timeout 900 s) |

The proof JSON, with the machine-specific interpreter path and the warning tail abbreviated:

```json
{
  "level": "TESTS_PASSED",
  "cause": null,
  "patch_applied": true,
  "baseline": {
    "kind": "baseline",
    "command": ["<worktree>/.cache/venv-fhi/bin/python", "-m", "pytest", "tests/sync/test_pwyw_checkout.py", "-q"],
    "returncode": 0,
    "timed_out": false,
    "stdout_tail": "............ [100%]\n... 12 passed, 2 warnings in 125.25s (0:02:05)"
  },
  "after": {
    "kind": "after",
    "command": ["<worktree>/.cache/venv-fhi/bin/python", "-m", "pytest", "tests/sync/test_pwyw_checkout.py", "-q"],
    "returncode": 0,
    "timed_out": false,
    "stdout_tail": "............ [100%]\n... 12 passed, 2 warnings in 72.05s (0:01:12)"
  }
}
```

## 6. What the check did and did not establish

The selected test file exercises the PWYW checkout path. Those tests mock
`stripe.checkout.Session.create`, assert it was called once, and read `call_args[1]` to check
`mode`, `success_url`, `cancel_url` and `metadata`. They do **not** assert
`payment_method_types` (or the renamed field). Consequences:

- The baseline is green, and the after check is green. `TESTS_PASSED` is the honest label for the
  check that ran.
- The check was *affected*: it invokes the changed call and receives the renamed keyword. It would
  fail if the call were removed (`assert_called_once`), but it would not fail if the keyword were
  misspelled, because it never asserts that name. It does not prove the rename was **necessary**.
- The diff also patches `CompletePaymentView` (`fighthealthinsurance/views.py:3904`) and the
  subscription checkout in `fhi_users/auth/rest_auth_views.py:754`. This focused check does not
  exercise those two paths.

The gate's wording — *one real API change, one real repo, one patch that passes a real check* — is
met. The stronger claim — *the patch was necessary and the check caught the old behavior* — is not
made and is not supported by this run.

## 7. Reproduction

```sh
mkdir -p .cache && cd .cache
curl -sSL --fail -o v2500.json \
  https://raw.githubusercontent.com/stripe/openapi/v2500/latest/openapi.spec3.json
curl -sSL --fail -o v2596.json \
  https://raw.githubusercontent.com/stripe/openapi/v2596/latest/openapi.spec3.json

git clone https://github.com/fighthealthinsurance/fighthealthinsurance.git targets/fhi
git -C targets/fhi checkout 56e69cfa4440aea0a42d016f84e6af336c5e0d3c

uv venv --python 3.13 venv-fhi
uv pip install --python venv-fhi/bin/python -r targets/fhi/requirements.txt
```

Then, from the Tenon worktree, with `TESTING=True` in the environment:

```python
import os

from tenon.detect import diff, load
from tenon.locate import LocateConfig, locate
from tenon.propose import propose
from tenon.prove import prove

os.environ["TESTING"] = "True"
old, new = load(".cache/v2500.json"), load(".cache/v2596.json")
change = next(c for c in diff(old, new).changes if c.kind.value == "renamed")
root = ".cache/targets/fhi"
config = LocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
)
located = locate(change, root, config)
proposal = propose(change, located, root)
command = [
    os.path.abspath(".cache/venv-fhi/bin/python"),
    "-m", "pytest", "tests/sync/test_pwyw_checkout.py", "-q",
]
print(prove(proposal, root, command, timeout=900).to_json())
```

The `.cache` directory is local-only and was not committed. The committed regression fixture
(`tests/locate/test_stripe_shape.py` and `tests/fixtures/repos/sdk-stripe-checkout/`) pins the same
call shape offline; it is not a substitute for the gate run.

## 8. Known limits

1. **External interpreter.** T4's isolated copy drops `.venv`; the check ran with an interpreter
   outside the copy. This is the known T4 limit (`docs/technical/CAPABILITY_ROADMAP.md:75-78`), not
   a new behavior.
2. **Operation mapping required.** Inference produced `checkout.sessions.create`; the SDK chain is
   `checkout.Session.create`. The mapping is the supported workaround. Whether T2 should infer the
   PascalCase class from a plural snake_case segment is a follow-on question, not part of this
   card.
3. **One rename.** The readable pair offers exactly one change T3's rename rule can act on. The
   other 288 changes are outside the rule. The gate proves the pipeline, not breadth.
4. **Point in time.** The target repo is pinned by SHA; it may move after this record.
5. **Proof scope.** The focused check covers the PWYW call, not the other two patched sites.

## 9. What this does not do

- No PR, no branch on the target repo (T5).
- No model proposer and no code egress.
- No T2 inference change, no T3 rule coverage, no composition semantics.
- No claim that the patch was necessary beyond the check described in §6.
