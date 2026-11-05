# Spec: `proof-pr` (T7)

- **Feature:** `proof-ladder`
- **PRD:** `docs/planning/proof-ladder/prd.md` (§ M10–M11)
- **Boundary:** `write_pr`'s required-level gate and the new level sentences. No runner, no CLI.

## Problem slice

T5 opens a normal PR for any non-`UNVERIFIED` result, so a `TYPES_BUILD_ONLY` patch would look as
confident as a tests-passed one even when the user required tests. T7 makes the requirement explicit:
at/above the required level is a normal PR; below is a refusal or an opted-in draft; `UNVERIFIED` is
always a draft. The body says what each new level actually proved.

## In-scope requirements

- `write_pr(..., required: ProofLevel = ProofLevel.TESTS_PASSED,
  allow_below_required: bool = False, allow_unverified: bool = False, ...)`.
  `allow_unverified` remains a deprecated alias: `allowed = allow_below_required or allow_unverified`.
- Gate after the existing preconditions and before the base/branch work:
  - `below = proof_rank(proof.level) < proof_rank(required)`.
  - If `below` and not allowed: `UNVERIFIED` → `PrRefusal.UNVERIFIED_NOT_ALLOWED` (the shipped
    cause); any other weak level → `PrRefusal.BELOW_REQUIRED_LEVEL`, with a detail naming both.
  - If not below, or allowed: continue. `draft = proof.level is ProofLevel.UNVERIFIED or below`.
- `PrRefusal` gains `BELOW_REQUIRED_LEVEL`; the existing values stay.
- `create_pr(..., draft=draft)`; a normal PR only for a non-`UNVERIFIED` level at/above the
  requirement.
- `pr/render.py` adds the level sentences and proof paragraphs:
  - `TYPES_BUILD_ONLY`: the build/type-check returned 0 before and after; no tests ran; weak.
  - `CHARACTERIZED`: the user-supplied characterization command returned 0 before and after; it
    checks current behavior, not the vendor's new API.
  - `REPLAYED`: the user-supplied recorded-call replay returned 0 before and after; the recording was
    supplied, not made by Tenon.
  - The title already uses `proof.level.value`.
- The `[LEVEL]` title and the body's per-stage check section are unchanged in shape; the body uses
  the primary checks for now (the CLI/PRD can add the full `checks` table in `proof-cli`).

## Out-of-scope

- The runner and the CLI.
- Generating characterization tests or recordings.
- Changing the T5 clone/push/PR guardrails or the dirty-tree rules.

## Acceptance criteria

- **AC1 — At required.** `TESTS_PASSED` with `required=TESTS_PASSED` → normal PR (`draft=False`);
  `TYPES_BUILD_ONLY` with `required=TYPES_BUILD_ONLY` → normal PR.
- **AC2 — Above required.** `TESTS_PASSED` with `required=TYPES_BUILD_ONLY` → normal PR.
- **AC3 — Below required.** `TYPES_BUILD_ONLY` with `required=TESTS_PASSED` and no opt-in →
  `BELOW_REQUIRED_LEVEL`, no push/PR; the detail names both levels.
- **AC4 — UNVERIFIED.** `UNVERIFIED` with `required=TESTS_PASSED` and no opt-in →
  `UNVERIFIED_NOT_ALLOWED`; with `allow_below_required=True` → draft; with
  `required=UNVERIFIED` and no opt-in → draft (never a normal PR).
- **AC5 — Alias.** `allow_unverified=True` behaves like `allow_below_required=True`.
- **AC6 — Sentences.** The title contains `[CHARACTERIZED]`, `[REPLAYED]`, `[TYPES_BUILD_ONLY]`; the
  body contains the fixed sentence, the command, and the "what this proves" paragraph for each; no
  weak level is called verified.
- **AC7 — Existing contract.** The T5 dirty-tree/default-branch/existing-branch/push/PR tests still
  pass with the new default `required=TESTS_PASSED`; `TESTS_PASSED` results are unchanged.

## Dependencies and sequencing

- Depends on `proof-result`; before or alongside `proof-cli` (the CLI passes the new args).
- Update the T5 tests that expect `UNVERIFIED_NOT_ALLOWED` and the `allow_unverified` name.

## Open questions / risks

- `UNVERIFIED` with `required=UNVERIFIED` is an explicit "I accept no proof" request; the PR is still
  a draft, preserving the T5 stance. The exit code is the CLI's concern.
- The body currently renders the primary checks, not every stage; `proof-cli` adds the full table.
