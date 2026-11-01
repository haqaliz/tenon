# Card: feat/m0-3-first-real-case

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Capability:** **M0.3** — the Phase 0 gate (`docs/ROADMAP.md`), exercising T1-T4 end to end.
- **Milestone:** M0.3 (`docs/ROADMAP.md`), Phase 0.
- **Branch:** `feat/m0-3-first-real-case/aliz`
- **Worktree:** `.claude/worktrees/feat-m0-3-first-real-case`

## Brief

Run the Phase 0 gate on real input: take the one real rename from the Stripe `v2500` -> `v2596`
diff (`payment_method_types` -> `allowed_payment_method_types` on `POST /v1/checkout/sessions`),
apply it to a real public repo, and prove the result with that repo's own check. Record the proof
level honestly. The gate is met when the patch applies and the chosen check passes after the patch,
with the evidence naming what the check did and did not establish.

## Dig result

- **Target:** `fighthealthinsurance/fighthealthinsurance` @
  `56e69cfa4440aea0a42d016f84e6af336c5e0d3c` (default branch `main`, pushed 2026-10-31).
- **Detect:** 289 changes, 52 breaking, 1 rename.
- **Locate:** 3 certain keyword sites, 0 ambiguous. Required the explicit mapping
  `POST /v1/checkout/sessions` = `checkout.Session.create`; inference yields
  `checkout.sessions.create` and matches nothing.
- **Propose:** 3 edits; the diff applies cleanly.
- **Prove:** `TESTS_PASSED`; `tests/sync/test_pwyw_checkout.py` 12 passed before and after; total
  229.5 s, timeout 900 s.
- **Environment:** Python 3.13.15; external venv `.cache/venv-fhi`;
  `uv pip install -r requirements.txt`; `TESTING=True`; stripe 12.2.0, Django 5.2.18,
  pytest 9.2.0, setuptools 79.0.1.
- **Nuance:** the check exercises the PWYW call through a mocked `Session.create` and reads
  `call_args[1]`, but it does not assert `payment_method_types`; it passes before and after. The
  other two patched sites are not covered by this check.

## Constraints carried in from the repo

- `CLAUDE.md` §1: execution decides. The label is whatever the check produced, not what the diff
  looks like.
- `CLAUDE.md` §2: honest proof levels. `TESTS_PASSED` with the coverage nuance stated in the
  evidence.
- `CLAUDE.md` §3: machine-readable source first. The Stripe OpenAPI pair is the source.
- `CLAUDE.md` §5: never touch the default branch. This card does not open a PR against the target
  repo.
- `VISION.md`: no model proposer, no code egress; the rule proposer is deterministic.
- `ROADMAP.md`: the gate is one real change, one real repo, one patch that passes a real check; do
  not weaken it to a fixture.

## Scope fence

Not this card: T2 inference (plural/PascalCase resource names), composition semantics, T3 rule
coverage, T5 PR writer, CLI/pipeline glue, committing the target repo or the Stripe specs, and any
model proposer.
