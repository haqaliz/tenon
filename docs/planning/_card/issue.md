# Card: feat/m0-3-real-case

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Capability:** Phase 0 gate **M0.3** (`docs/ROADMAP.md`) plus the smallest T2 follow-on it needs
- **Milestone:** closes the Phase 0 gate: one real API change, one real repo, one patch that passes a
  real check
- **Branch:** `feat/m0-3-real-case/aliz`
- **Worktree:** `.claude/worktrees/feat-m0-3-real-case`

## Brief

Run T1 → T2 → T3 → T4 on the one analyzable Stripe rename and a real public repo, and record the
proof level honestly. The change is T1's record
`payment_method_types` → `allowed_payment_method_types` on `POST /v1/checkout/sessions`
(`docs/planning/lazy-ref-resolution/evidence.md` §4).

The deep dig found the gate is blocked by a smaller capability gap than expected. In every
offline-runnable repo inspected, the test that exercises the Stripe call **encodes the old field
name in a mock assertion**:

```python
stripe.checkout.Session.create.assert_called_with(payment_method_types=..., ...)
```

T2 does not see that line: the keyword's chain is
`checkout.Session.create.assert_called_with`, not `checkout.Session.create`. So T3 proposes only the
production edit, and the repo's own test then fails. Verified on `yezz123/stripe-template` at
`9d9178c`: the proposed one-line patch makes `tests/test_payment.py::test_session_url` fail with
`AssertionError: expected call`.

The smallest complete fix is a T2 scan rule: when a rooted call's final segment is a mock assertion
(`assert_called_with`, `assert_called_once_with`), attribute its keyword arguments to the operation
chain without that segment. T3 needs no change; it already edits any certain site carrying the old
symbol.

## Target repo (proposed)

`https://github.com/yezz123/stripe-template` at `9d9178c47a191112b86a6ce6edd71962faee80d1`
(MIT, 25 KB, Python, FastAPI). Call site:
`app/router/v1/payment.py:41`, `checkout.Session.create(payment_method_types=...)`.
Test: `tests/test_payment.py::test_session_url`, which mocks the call and asserts its kwargs.

Known limits of this repo as a proof target:

- Two tests (`test_setup_new_method_by_email`, `..._by_id`) call the live Stripe API with a fake key
  and fail before any patch. The check command must deselect them and the evidence must say so.
- The repo is a 2024 template, not a production service.
- The rename changes semantics: the new field is a filter on the dynamically computed set, not an
  explicit list (Stripe spec `v2596` description). The mocked test cannot see that difference.

Alternative target: `MoigeMatino/flask-stripe-one-time-payments` at `9dd24e4` (MIT). Direct
keyword, one site, its test does not pin the call kwargs, so no T2 change is needed — but its
TestingConfig requires PostgreSQL (`docker compose`, as its own CI does), and its test is
insensitive to the rename.

## Constraints carried in from the repo

- `CLAUDE.md` §1: execution decides. The patch is labelled only by what T4 ran.
- `CLAUDE.md` §2: honest levels. If the check is a subset, the evidence says subset and names the
  deselected tests.
- `CLAUDE.md` §5: no branch or merge; T5 does not exist yet.
- `docs/ROADMAP.md` R1: a mocked suite makes `TESTS_PASSED` weak; say so in the evidence.
- `docs/technical/ARCHITECTURE.md`: change record is the unit; no new change source.
- Determinism: no network in `tests/`; the real clone and the Stripe snapshots stay in `.cache`.

## Scope fence

Not this card: T5 PR writer, T3 rules beyond rename, semantic analysis of the new field, test-double
shapes other than `assert_called_with` / `assert_called_once_with` (notably
`call_args.kwargs["field"]` and `call_args[1]["field"]`), CLI (`src/tenon/cli`), and any change to
the T4 proof contract.
