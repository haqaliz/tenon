# Spec: `webhook-trigger-config` (T10f)

- **Feature:** `webhook-runs`
- **PRD:** `docs/planning/webhook-runs/prd.md` (§ M1, M3)
- **Boundary:** the `Trigger` type, parsing/validation and the `--trigger` CLI/startup wiring. No
  webhook match/queue behavior.

## In-scope requirements

- `src/tenon/service/triggers.py`:
  - `Trigger(event: str, action: str | None, bundle: str)` frozen/slots.
  - `parse_trigger(value: str, bundles: Path) -> Trigger`: split the first `=`, then the first `.`;
    event/action/bundle are non-empty strings with no whitespace; `bundle` resolves under `bundles`
    via the existing `resolve_bundle` (a `.json` file, no escape); a bad value is a named `ValueError`.
  - `parse_triggers(values: Sequence[str], bundles: Path) -> dict[tuple[str, str | None], str]`:
    exact-key duplicates are a named `ValueError`; an actionless and an action-specific trigger for
    the same event may coexist.
- `provider serve`: a repeatable `--trigger EVENT[.ACTION]=BUNDLE`; `_serve` parses after the bundle
  directory is validated; a trigger without `--webhook-secret` is a named usage error (exit 2); the
  mapping is passed to the `Api` (the API behavior is the other aspect).
- Tests: parse/precedence/duplicates/traversal/absolute/missing/non-json/whitespace; the CLI flag and
  the no-secret usage error; `--help`.

## Out-of-scope

- The webhook match/queue/response; bundle-level triggers; per-repo filters.
- A trigger admin API/UI.

## Acceptance criteria

- **AC1 — Parse.** `event.action=bundle` and `event=bundle` parse to the right `Trigger`; the first
  `=`/`.` split is used.
- **AC2 — Validate.** A blank/whitespace event/action/bundle, a missing `=`, an absolute/`..`/missing/
  non-`.json` bundle, and a duplicate exact key are named `ValueError`s.
- **AC3 — Precedence.** An actionless and an action-specific trigger for the same event coexist.
- **AC4 — CLI.** `--trigger` is repeatable and reaches the parsed map; a trigger without a secret is
  exit 2 with a named message; `--help` lists it.
- **AC5 — Regression.** All prior tests green.
