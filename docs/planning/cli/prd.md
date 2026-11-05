# PRD: `tenon check` / `tenon fix` CLI (M1.4)

- **Slug:** `cli`
- **Capability:** M1.4 in `docs/ROADMAP.md` (exposes T1–T5; no new T-id)
- **Milestone:** M1.4 (Phase 1)
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1–T5 are shipped as a Python library. A developer cannot run Tenon without writing a script; the
OSS on-ramp in `VISION.md` (`tenon check`, `tenon fix`) does not exist, and neither do the exit codes
or the byte-stable JSON that CI needs. `uv run tenon --help` currently fails.

Without M1.4, the Phase 1 work has no user-facing surface: the proof runner decides a level, the PR
writer can ship it, but nothing connects the stages or reports the result to a human or a pipeline.
The CLI is deliberately thin — it composes the shipped contracts and adds no detection, location,
proposal, proof or PR logic.

**For whom:** the developer running Tenon locally, a CI job that gates on affected call sites, and
the next capabilities (T6–T8) that need one entry point to plug into.

## Goals & Success Metrics

1. **Two commands, one entry point.** `tenon check` reports affected sites; `tenon fix` proposes,
   proves, prints the diff and optionally opens a PR. `tenon --help`, `check --help` and `fix --help`
   exit 0.
2. **Exit codes are the contract.** `check`: 0 clean, 1 affected or unanalyzable, 2 usage/bad input.
   `fix`: 0 required proof reached, 1 not, 2 usage/bad input.
3. **Machine output.** `--json` writes exactly one byte-stable JSON object to stdout; no prose, no
   timestamps, no absolute paths.
4. **Config plus flags.** `tenon.toml` `[locate]` and `[tenon]` provide defaults; CLI flags override.
   The in-memory API stays the real contract.
5. **No surprise writes.** `fix` without `--open-pr` prints; it never applies the patch or touches the
   checkout. `--open-pr` delegates to T5's guardrails.
6. **Never a traceback.** A spec refusal, a bad config, a missing file and a usage error are named,
   mapped to exit 2, and rendered as JSON when `--json` is on.
7. **Offline and deterministic.** Tests use fixture repos and never call `gh`, a model or the network.

## User Personas & Scenarios

- **Developer.** `tenon check . --old v2500.json --new v2596.json` sees the affected Stripe calls;
  `tenon fix` prints the two-file diff and `TESTS_PASSED`.
- **CI job.** `tenon check . --old old.yaml --new new.yaml --json` exits 1 when a call site exists;
  the JSON is parsed for file/line.
- **Developer shipping.** `tenon fix ... --open-pr --check "python -m pytest -q"` opens a PR whose
  title starts with `[TESTS_PASSED]`; a dirty checkout is refused and nothing is pushed.
- **Developer with no tests.** `tenon fix` prints the diff and `UNVERIFIED (NO_TESTS_FOUND)`; the exit
  is 1. `--require UNVERIFIED` turns the exit to 0 for a local dry run, but `--open-pr` still needs
  `--allow-unverified` and opens a draft.

Scenario (the M0.3 case): `check` finds three certain sites; `fix` proposes three edits, `prove` runs
the focused test (12 passed before and after), prints `TESTS_PASSED`, and `--open-pr` opens the
branch. The CLI adds no new claim beyond what each stage returned.

## Requirements

### Must have

- **M1 — Entry point.** Add `[project.scripts] tenon = "tenon.cli:main"` to `pyproject.toml` and
  `src/tenon/cli/` with `main(argv: Sequence[str] | None = None, *, remote: Remote | None = None) ->
  int`. The console script uses the return value as the exit code. `python -m tenon` works through
  `src/tenon/__main__.py`. `main` never calls `sys.exit`; it returns an int.
- **M2 — `check`.** `tenon check <repo> --old SPEC --new SPEC [--config PATH] [--sdk-package NAME]
  [--operation KEY=VALUE ...] [--field KEY=VALUE ...] [--breaking-only|--no-breaking-only] [--json]`.
  Loads both specs, diffs them, optionally filters to `breaking` changes, runs `locate` per change,
  and reports certain sites, ambiguity groups and the locate reason.
- **M3 — `check` exit codes.** 0 when no change yields a certain site or an ambiguity group, and no
  result carries `NO_SDK_IMPORT` or `OPERATION_NOT_MAPPED`; 1 when at least one site/ambiguity exists
  or one of those two reasons occurs (the analysis could not run); 2 on usage, spec refusal or config
  error. `NO_SITES` and `UNSUPPORTED_CHANGE_KIND` are clean.
- **M4 — `fix`.** `tenon fix <repo> --old SPEC --new SPEC [--config PATH] [--sdk-package NAME]
  [--operation ...] [--field ...] [--check CMD] [--require LEVEL] [--breaking-only|--no-breaking-only]
  [--json] [--open-pr] [--allow-unverified]`. Per change: `locate`, `propose`, `prove`. Without
  `--open-pr`, print the diff and proof and write nothing. With `--open-pr`, call `write_pr` for each
  proposal, passing `DiffResult.unanalyzed` so the PR body surfaces the skipped subtrees, and report
  the URL or refusal.
- **M5 — `fix` exit codes.** 0 when every processed proposal reached `--require` (default
  `TESTS_PASSED`) and every requested PR opened; 1 otherwise, including no proposal for a non-empty
  change set, `UNVERIFIED`, a refused PR, or no check command; 2 on usage, spec refusal or config
  error. Zero changes after filtering is 0 (nothing to fix).
- **M6 — `--require`.** Accept `TESTS_PASSED` and `UNVERIFIED` in this card. The other proof levels
  are a usage error naming T7. `--require` changes the exit code only; `--open-pr` with `UNVERIFIED`
  still needs `--allow-unverified` and produces a draft.
- **M7 — Config.** Default `<repo>/tenon.toml`; `--config` overrides. `[locate]` is the existing
  `LocateConfig` table (`sdk_package`, `operations`, `fields`). `[tenon]` adds `command` (an array of
  strings), `require` (`TESTS_PASSED` or `UNVERIFIED`) and `breaking_only` (bool). Flags override
  config; `--operation`/`--field` merge over the table. A missing config with `--sdk-package` is
  valid; a missing `sdk_package` from both is a usage error. `--check` takes one shell-like string
  parsed with `shlex.split` (no shell, no interpolation).
- **M8 — JSON.** `--json` writes exactly one JSON object to stdout and nothing else, with
  `sort_keys=True`, `ensure_ascii=False`, compact separators and one trailing newline. `check`:
  `{"command": "check", "results": [<LocateResult.to_dict()>...], "summary": {...}}`. `fix`:
  `{"command": "fix", "results": [{"change": ..., "locate": ..., "proposal": ..., "proof": ...,
  "pr": <PrResult.to_dict()|null>}...], "summary": {...}}`. Summaries carry counts only, no clock.
- **M9 — Text output.** Deterministic plain text, no colour. `check`: the change summary, then one
  line per certain site (`path:line:column  shape  symbol`), ambiguity groups with their reason, or
  the locate reason. `fix`: the change summary, the unified diff, the proposal reason when there is
  no diff, `Proof: <LEVEL>` with the cause and the command/exit codes, then skipped sites, then
  `PR: <url>` or `PR refused: <CAUSE>` when requested. A final summary line per command.
- **M10 — Errors.** Catch `SpecRefusal` (code, pointer, message), config `ValueError`/`TOMLDecodeError`,
  `FileNotFoundError` and `OSError` at the top; no traceback. Exit 2 for bad input, 1 for an internal
  failure. With `--json`, the error is
  `{"error": {"kind": "spec"|"config"|"usage"|"internal", "code": str|null, "pointer": str|null,
  "message": str}}` on stdout; without it, the same message goes to stderr.
- **M11 — Offline seam.** `main` accepts an optional `remote`; it constructs `GitGhRemote` only when
  `--open-pr` is used. Tests pass a fake and never touch `gh` or the network. The pipeline functions
  (`diff`, `locate`, `propose`, `prove`, `write_pr`) are called directly, not reimplemented.
- **M12 — Determinism.** The same inputs produce byte-identical JSON and text across hash seeds and
  runs. Ordering comes from `DiffResult.changes` and the shipped contract ordering.

### Should have

- **S1 — Summary counts.** `check`: changes, certain sites, ambiguity groups. `fix`: changes,
  proposals, passed, unverified, PRs opened, PRs refused.
- **S2 — `--breaking-only`.** Defaults from `[tenon].breaking_only`; `BooleanOptionalAction` provides
  `--no-breaking-only` to override a true config.
- **S3 — `python -m tenon`.** A `__main__.py` that calls `main()`; tested as a subprocess.
- **S4 — `--version`.** Print the package version from `importlib.metadata`; no network.

### Nice to have

- **N1 — Colour.** Disabled by default, opt-in via `--color`; skipped if it complicates byte-stable
  text.
- **N2 — `tenon.toml` discovery upward.** Walk to the repo root only; no global config.

## Data Model

```
CliConfig
  locate: LocateConfig          # the shipped table
  command: tuple[str, ...]      # [] when not configured
  require: ProofLevel           # TESTS_PASSED | UNVERIFIED
  breaking_only: bool
  to_dict() / to_json()         # not required in output

CheckReport
  results: tuple[LocateResult, ...]
  summary: {changes, certain, ambiguous, unanalyzable?}
  to_dict() / to_json()

FixReport
  results: tuple[FixResult, ...]
  summary: {changes, proposals, passed, unverified, prs_opened, prs_refused}
  to_dict() / to_json()

FixResult
  change: Change
  locate: LocateResult
  proposal: Proposal
  proof: ProofResult
  pr: PrResult | None
```

The CLI types are report envelopes; they do not change the shipped contracts. The JSON composes the
existing `to_dict()` outputs, so a change record has one spelling everywhere.

## API Contract

```python
from tenon.cli import main

raise SystemExit(main(["check", "path/to/repo", "--old", "v1.yaml", "--new", "v2.yaml"]))
raise SystemExit(main(["fix", "path/to/repo", "--old", "v1.yaml", "--new", "v2.yaml",
                       "--check", "python -m pytest -q", "--open-pr"]))
```

No change to `detect`, `locate`, `propose`, `prove` or `pr`.

## Technical Considerations

- **Why thin.** Every stage already has a tested contract. The CLI parses, configures, composes,
  renders and maps exit codes; a new pipeline function would duplicate orchestration the CLI owns.
- **Why `argparse`.** Standard library, no dependency, deterministic help and exit 2 on usage.
- **Why one JSON object.** A machine consumer reads stdout once; warnings and errors never share it.
  With `--json`, the error envelope is the one object.
- **Why `<repo>/tenon.toml`.** The config is repo-specific (SDK package, endpoint mapping, check
  command) and travels with the repository. The M0.3 case already used a `tenon.toml` mapping.
- **Why `--check` is shlex-split.** Users type a command; `prove` needs an argument list. Splitting
  once, with no shell, gives a list without `shell=True`. A TOML array avoids the parse for config
  users.
- **Performance.** `locate` scans the repository per change. A 289-change diff can be slow;
  `--breaking-only` and the report ordering keep it usable. Batching scans is a later optimization,
  not a contract change.
- **Exit code nuance.** `check` treats `NO_SDK_IMPORT` and `OPERATION_NOT_MAPPED` as 1, because the
  tool could not analyze the repository, not because it found nothing. The text/JSON says which
  reason fired. A CI job that wants "only sites matter" can inspect the JSON.
- **No checkout writes.** `fix` renders in memory; `--open-pr` delegates to T5, which clones, refuses
  a dirty tree and never merges.

## Risks & Open Questions

- **R1 (no tests).** `fix` without a check command is `UNVERIFIED / NO_TESTS_FOUND` and exits 1. The
  user sees the diff; `--require UNVERIFIED` only changes the exit, never the label.
- **R2 (overclaim).** The CLI prints exactly the `ProofResult`; `--open-pr` uses T5's title/body.
  There is no "verified" word outside the level.
- **Performance.** Per-change scans can be slow on a large diff. Mitigation: `--breaking-only`; a
  later batching card.
- **Config drift.** `[locate]` is shared with the existing loader; `[tenon]` is new. A malformed file
  is a named config error, not a traceback.
- **Exit code ambiguity for `check`.** A `NO_SDK_IMPORT` is 1, not 0, so a misconfigured repo fails
  loudly. A user who wants only found sites must read the JSON. Documented.
- **`--open-pr` with multiple proposals.** One PR per proposal; a refusal after some PRs opened is
  possible. The report names each PR/refusal; the exit is 1 if any step failed. No rollback.
- **Open question — should `fix` stop at the first refused PR?** This card processes all proposals
  and reports each; a global refusal (dirty tree) will repeat. A later card can stop early.
- **Open question — `tenon probe`.** T8; not this card.

## Out of Scope

- `tenon probe` (T8), T6 TS/JS, T7 proof levels and `--require CHARACTERIZED|REPLAYED|
  TYPES_BUILD_ONLY`.
- New detect/locate/propose/prove/pr logic or rules.
- Applying the diff to the working tree; merging; force-pushing.
- A hosted app, auth, telemetry, colour, global config.
- Releases, version bumping, PyPI publishing (the entry point only).

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `cli-config` | `CliConfig`, `tenon.toml` `[tenon]` + `[locate]`, flag overrides, `shlex` command, named config errors. No pipeline. |
| `cli-report` | Exit-code mapping, text renderers, JSON envelopes, summaries, error envelopes. Pure; no pipeline calls. |
| `cli-run` | `argparse` surface, `check`/`fix` orchestration, optional `remote`, `python -m tenon`, console script, subprocess smoke tests. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The library has no user surface; M1.4 is explicit. |
| User understanding | 🟡 | The developer and CI personas are stated; no external user has run the CLI yet. |
| Success metrics | 🟢 | Exit codes and JSON are testable; commands are named. |
| Scope clarity | 🟢 | Thin composition; probe/T6/T7 and writes excluded. |
| Edge cases & risks | 🟡 | Performance on large diffs and multi-PR partial failure are documented, not solved. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | All stages shipped; argparse and stdlib only. |
| Go-to-market | 🟢 | This is the OSS on-ramp; no hosted dependency. |

**Areas to strengthen before sharing:** the `check` exit code for `NO_SDK_IMPORT` is a policy choice
that will surprise someone; the multi-PR partial failure has no rollback.

**The question I would want answered before greenlighting this:** *If `check` exits 1 because the SDK
package was never imported, will a CI job treat a misconfiguration as a real finding?* The answer
this card records: yes, deliberately — the JSON carries the reason, and the alternative (exit 0 on a
repo the tool could not analyze) is the dishonest one.
