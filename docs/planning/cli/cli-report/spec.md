# Spec: `cli-report` (M1.4 CLI)

- **Feature:** `cli`
- **PRD:** `docs/planning/cli/prd.md` (§ M3, M5, M8, M9, M10)
- **Boundary:** exit-code mapping and rendering. Pure functions over the shipped result contracts.
  No pipeline calls, no subprocess, no file reads.

## Problem slice

A CLI is only as honest as its exit code and its output. The mapping must distinguish "clean",
"affected", "could not analyze", "required proof reached" and "usage error"; the output must be one
deterministic shape a human and a machine can both read.

## In-scope requirements

- `check_exit(results: Sequence[LocateResult]) -> int`:
  - `0` when every result has no certain sites, no ambiguity groups, and a reason in
    `{None, NO_SITES, UNSUPPORTED_CHANGE_KIND}`.
  - `1` when any result has a site/ambiguity or a reason in `{NO_SDK_IMPORT, OPERATION_NOT_MAPPED}`.
  - Zero results → `0`.
- `fix_exit(changes: int, results: Sequence[FixResult], require: ProofLevel) -> int`:
  - `0` when `changes == 0`; otherwise `0` only if every `FixResult.proof` meets `require` and every
    requested PR (a `pr` field that is not `None`) has `status is OPENED`.
  - `1` otherwise, including a non-empty change set with no proposals, `UNVERIFIED` under
    `TESTS_PASSED`, or a refused PR.
  - `UNVERIFIED` meets `UNVERIFIED`; `TESTS_PASSED` meets both.
- `render_check_text(results) -> str`:
  - One block per change: a deterministic change line, then one line per certain site
    (`path:line:column  shape  symbol`), one line per ambiguity group (`ambiguous REASON: ...`), or
    `no affected sites (REASON)`.
  - A final summary line: `N changes, M certain sites, K ambiguity groups`.
  - One trailing newline; no colour.
- `render_fix_text(results) -> str`:
  - Per change: the change line, then the diff (if any), then the proposal reason when there is no
    diff, then `Proof: <LEVEL>` with the cause, the command, baseline/after exits, skipped sites, and
    `PR: <url>` or `PR refused: <CAUSE>` when a PR result exists.
  - A final summary line with changes, proposals, passed, unverified, PRs opened, PRs refused.
  - One trailing newline.
- `render_check_json(results) -> str` and `render_fix_json(results) -> str`:
  - One line: `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"`.
  - `check`: `{"command":"check","results":[...],"summary":{...}}`.
  - `fix`: `{"command":"fix","results":[{"change":..., "locate":..., "proposal":..., "proof":...,
    "pr":...}], "summary":{...}}`.
  - Every nested value comes from the shipped `to_dict()`; no dataclass/enum reprs.
- `render_error(kind, message, *, code=None, pointer=None, json_mode) -> str`:
  - JSON: `{"error":{"kind":..., "code":..., "pointer":..., "message":...}}` + `\n`.
  - Text: `tenon: <kind>: <message>` with the code/pointer when present, + `\n`.
- `FixResult`: `change`, `locate`, `proposal`, `proof`, `pr` (`PrResult | None`); frozen, slots.
- Summary builders: pure count functions; no clock, no environment.

## Out-of-scope

- Deciding which changes to process (`cli-run`).
- Running anything or writing files.
- Colour, tables, terminal width detection.
- A new JSON schema for `Change`, `LocateResult`, `Proposal`, `ProofResult` or `PrResult`.

## Acceptance criteria

- **AC1 — Check exit.** Certain → 1; ambiguous → 1; `NO_SITES` → 0; `UNSUPPORTED_CHANGE_KIND` → 0;
  `NO_SDK_IMPORT` → 1; `OPERATION_NOT_MAPPED` → 1; empty → 0.
- **AC2 — Fix exit.** Zero changes → 0; a passed proof with no PR request → 0; `UNVERIFIED` under
  `TESTS_PASSED` → 1; `UNVERIFIED` under `UNVERIFIED` → 0; any refused PR → 1.
- **AC3 — Check text.** Deterministic order, one line per site, reasons named, one trailing newline.
- **AC4 — Fix text.** Diff and proof present; `UNVERIFIED` names the cause; skipped sites listed; PR
  URL/refusal shown; one trailing newline.
- **AC5 — JSON shape.** The check/fix envelopes have exactly the stated keys; nested values equal
  the shipped `to_dict()` outputs; only JSON primitives.
- **AC6 — Byte stability.** `render_check_json`/`render_fix_json` are identical across
  `PYTHONHASHSEED` values and repeated calls.
- **AC7 — Error envelope.** JSON mode is one object with `kind`, `code`, `pointer`, `message`; text
  mode is one stderr-ready line; neither contains a traceback.
- **AC8 — No leakage.** No absolute fixture path, timestamp, `ProofResult(`, `PrResult(` or enum
  repr in the output.

## Dependencies and sequencing

- Depends on `tenon.locate`, `tenon.propose`, `tenon.prove`, `tenon.pr` contracts (shipped).
- Land after `cli-config`, before `cli-run`.
- `cli-run` calls these functions; no duplicated formatting.

## Open questions / risks

- The change line grammar is shared with `pr-render` in spirit but not imported; a later refactor can
  factor it if the two drift.
- Text output is not a stable machine contract; JSON is. The spec pins both anyway.
- A failed PR after a successful push is rendered as `PR refused: <CAUSE>` with the detail available
  in JSON.
