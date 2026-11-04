# Spec: gate-run

## Problem slice

The Phase 0 gate was met during the dig on 2026-11-01/02: the Stripe rename
`payment_method_types` -> `allowed_payment_method_types` was located at three certain sites in
`fighthealthinsurance/fighthealthinsurance`, a three-edit diff was proposed, and the repo's focused
check passed before and after (`TESTS_PASSED`). Nothing about that run is committed yet.

This aspect turns the dig into durable artifacts: an evidence record a reviewer can reproduce, and
an offline regression fixture that pins the real Stripe call shape. It adds no production code.

## In scope

- The gate evidence file with repo, SHA, spec tags, sites, diff, command, environment, proof JSON,
  timings, and the coverage nuance.
- An offline fixture repo and test that pin the class-cased SDK chain and the explicit mapping.
- The roadmap and status updates that follow from a met gate.

## Out of scope

- Any change under `src/tenon/` (T2 inference, T3 rules, T4 behavior).
- T5, the CLI, pipeline glue, composition semantics.
- Committing the target repo, its tests, or the Stripe spec snapshots.
- A model proposer or any network call in `tests/`.

## Acceptance criteria

1. `docs/planning/m0-3-first-real-case/evidence.md` records:
   - target `fighthealthinsurance/fighthealthinsurance` @
     `56e69cfa4440aea0a42d016f84e6af336c5e0d3c`, Stripe `v2500` -> `v2596`;
   - 3 certain sites at `fhi_users/auth/rest_auth_views.py:754`,
     `fighthealthinsurance/views.py:3904` and `:4177`, all `keyword`, symbol
     `payment_method_types`;
   - the exact three-edit diff;
   - the proof command, external-venv setup, proof JSON, baseline/after timings, and the nuance that
     the check exercises but does not assert the renamed field.
2. `tests/locate/test_stripe_shape.py`:
   - without the operation mapping, `locate` returns `NO_SITES` (the inferred candidate is
     `checkout.sessions.create`);
   - with `POST /v1/checkout/sessions` = `checkout.Session.create`, exactly one certain
     `keyword` site is found at `shop/checkout.py` line 7, column 9;
   - `propose` yields one edit and the exact expected diff;
   - the test is offline and deterministic.
3. `uv run pytest` is green.
4. `docs/ROADMAP.md` M0.3 is Shipped; `CLAUDE.md` says T5 is next; the stale
   `docs/planning/stripe-real-case/prd.md` status points at the new evidence.
5. No file under `src/tenon/` changes.

## Dependencies and sequencing

- T1-T4 are shipped; no new dependency.
- Fixture test first (red), fixture repo second (green), then evidence, then state updates.

## Risks

- **R1 nuance.** The focused check is green before the patch; the evidence must say so and must not
  claim the patch was necessary. This aspect records the limit rather than changing the gate.
- **Regression-only test.** The fixture test passes as soon as the fixture exists; the red phase is
  the missing fixture, not a new production behavior. State that in the plan.
- **Exact diff stability.** The fixture must end with a newline and the expected diff is pinned
  byte-for-byte; a formatting change in the fixture should fail the test, which is intended.

## Open questions

None blocking. The T2 inference follow-on and the "red-before" gate standard remain PRD-level open
questions, deliberately out of this aspect.
