# Spec: real-case-pin

Parent: `docs/planning/m0-3-real-case/prd.md` (aspect 2 of 3).

## Problem slice

The gate run is one-shot evidence. Without a committed snapshot, nothing stops T2/T3 from losing the
two-site behavior later. This aspect pins the real repo's two relevant files and the exact diff in
an offline test.

## In scope

- `tests/fixtures/repos/real-stripe-template/` containing, verbatim from
  `yezz123/stripe-template` at `9d9178c47a191112b86a6ce6edd71962faee80d1`:
  - `app/router/v1/payment.py`
  - `tests/test_payment.py`
  - `LICENSE`
  - `PROVENANCE.md` (URL, SHA, files taken, MIT, date, retrieval command)
- `tests/locate/test_real_stripe_template.py`:
  - a minimal OpenAPI pair carrying the rename (not the 4.4 MB vendor documents);
  - T1 `parse` + `diff` → one `renamed`, `inferred`, on `post /v1/checkout/sessions`;
  - T2 `locate` with
    `LocateConfig(sdk_package="stripe", operations={"POST /v1/checkout/sessions": "checkout.Session.create"})`;
  - T3 `propose`;
  - assertions: two certain `keyword` sites (`app/router/v1/payment.py` line 41,
    `tests/test_payment.py` line 49), no ambiguity, two edits, a diff with exactly two hunks and
    both old/new names, byte-stable across two runs.

## Out of scope

- Running the repo's test suite in CI (needs Flask/FastAPI/pytest-mock and a venv). That is the
  evidence run, documented, not a Tenon test dependency.
- The rest of the upstream repo, its CI config, scripts, or secrets.
- Any network fetch at test time.

## Acceptance criteria

1. The snapshot files are byte-identical to upstream at the pinned SHA.
2. The pinning test passes offline and fails if the scan rule is reverted (one site instead of two).
3. The asserted diff contains exactly two hunks; no third file is touched.
4. `LICENSE` and `PROVENANCE.md` make the origin and terms auditable.
