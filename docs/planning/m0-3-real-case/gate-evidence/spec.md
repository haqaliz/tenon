# Spec: gate-evidence

Parent: `docs/planning/m0-3-real-case/prd.md` (aspect 3 of 3).

## Problem slice

The Phase 0 gate is a claim about what actually ran. This aspect performs the one real run and
records it with enough detail that a reader can reproduce it and see exactly what the proof level
does and does not mean.

## In scope

- `.cache/m0-3/` (untracked, deleted before commit): Stripe `v2500` and `v2596` documents, the
  `yezz123/stripe-template` clone at `9d9178c`, and a Python 3.12 venv with the repo's deps pinned.
- One scripted T1→T4 run with the operation mapping and the check
  `[venv/bin/python, "-m", "pytest", "-q", "-k", "not setup_new_method"]`, `STRIPE_API_KEY=sk_test_x`.
- `docs/planning/m0-3-real-case/evidence.md` with: URL/SHA, base commit, change record, config,
  command and environment, baseline tail, after tail, `ProofResult`, the diff, the deselected tests
  and why, the semantic difference between the old and new fields, and the limits of the label.
- After a passing run: mark M0.3 shipped in `docs/ROADMAP.md`; add the mock-assertion limit to T2's
  known-limits paragraph in `docs/technical/CAPABILITY_ROADMAP.md`.

## Out of scope

- Committing the vendor documents, the clone, the venv, or any `.cache` content.
- A PR, a branch, or a merge (T5).
- Claiming the full suite passes, or that the rename is semantically equivalent.
- Tuning T4, the timeout, or the proof contract.

## Acceptance criteria

1. Baseline is green for the chosen check: 5 passed, 2 deselected; the two deselected tests are
   named.
2. `ProofResult.level == TESTS_PASSED`, `patch_applied is True`, both return codes 0.
3. The applied diff is the two-edit proposal from the pinning aspect.
4. The evidence states: the call is mocked; the suite does not exercise live Stripe; the new field
   filters the dynamic set rather than listing methods; `TESTS_PASSED` means the offline suite still
   passes.
5. If any of 1–2 fails, the evidence records the `UNVERIFIED` cause and the gate stays open.
6. No `.cache` path is committed; `git status` is clean after the commit.
