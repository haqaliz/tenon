# PRD: Proof ladder (T7)

- **Slug:** `proof-ladder`
- **Capability:** T7 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M2.2 in `docs/ROADMAP.md` (Phase 2)
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T4 emits exactly two levels: `TESTS_PASSED` and `UNVERIFIED`, from one check command. The product's
proof contract has four usable levels (`TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`,
`TYPES_BUILD_ONLY`), and the CLI advertises a `--require` ladder it cannot honour. R1 — many repos
have no tests — is the biggest adoption blocker: those repos get `UNVERIFIED` and no PR even when a
build, a characterization run or a recorded-call replay would have proved something real.

T7 widens the runner and the contract without weakening the rule that execution decides. A
`ProofPlan` names the commands for each stage; the runner runs every configured stage baseline-first,
applies the patch once, runs every after-check, and records the strongest level that actually passed.
Weak proof is labelled weak; a red stronger stage is never disguised as a weaker green one.

The dangerous shortcuts are rejected here: running the after-checks without a baseline, calling a
build-only result "tests passed", promoting a weaker level because the required one failed, and
opening a normal PR below the level the user required.

**For whom:** the developer whose repo has no tests (R1), the reviewer reading the PR label, the CLI
`--require` contract, and T5's PR gate.

## Goals & Success Metrics

1. **Five honest levels.** `TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`,
   `UNVERIFIED`, each backed by a command that actually ran before and after.
2. **One plan, many stages.** `ProofPlan` names optional commands for `build`, `characterize`,
   `replay` and `tests`; `prove_plan` runs all baselines, applies once, runs all afters, and records
   every `CheckResult` with its stage.
3. **Any configured failure is UNVERIFIED.** A red build/test/characterize/replay after-check is
   `UNVERIFIED` with that stage's cause, even if another stage passed. The strongest level is only
   claimed when every configured stage is green.
4. **The ladder is ordered.** `TESTS_PASSED > CHARACTERIZED > REPLAYED > TYPES_BUILD_ONLY >
   UNVERIFIED`; a stronger level satisfies a weaker `--require`, never the reverse.
5. **The CLI honours `--require`.** `--build`, `--characterize`, `--replay` and `--check` feed the
   plan; `--require` accepts all five levels; exit 0 only when the result meets it.
6. **The PR states the level and gates below-required proof.** A normal PR at or above the required
   level; a draft only with `--allow-below-required`; a named refusal otherwise. `UNVERIFIED` is
   always a draft, even when explicitly required.
7. **Backward compatibility.** `prove(proposal, root, command)` keeps working as a tests-only plan;
   the existing T4 causes and baseline-first semantics are preserved.
8. **Offline and deterministic.** Fixture commands only; no network, model or real API call;
   byte-stable JSON and report text.

## User Personas & Scenarios

- **Developer with no tests.** Runs `tenon fix --build "python -m compileall ."`; the build passes
  before and after; the PR title is `[TYPES_BUILD_ONLY]`, and the body says no tests ran.
- **Developer with characterization tests.** `--characterize "pytest tests/characterization"` runs a
  user-supplied suite of current-behavior tests; the PR says `[CHARACTERIZED]`.
- **Developer with recorded traffic.** `--replay "pytest tests/replay"` runs a replay suite over
  user-supplied recordings; the PR says `[REPLAYED]`.
- **Team requiring tests.** `--require TESTS_PASSED` with only a build configured exits 1 and
  `--open-pr` refuses unless `--allow-below-required`, which opens a draft.
- **Reviewer.** The PR body quotes every command, the stage, and both exit codes; the label is the
  strongest level that ran, not the one the user hoped for.

Scenario: a rename on a repo with a build and a test suite. The plan has both commands. The build
baseline and test baseline pass; the diff applies; the build after passes; the test after fails.
Result: `UNVERIFIED / TESTS_FAILED_AFTER`, with the build pass recorded. The CLI exits 1; no PR
unless the user opted into a draft.

## Requirements

### Must have

- **M1 — Levels and rank.** `ProofLevel` gains `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`.
  `PROOF_RANK` (or `proof_rank`) orders `TESTS_PASSED > CHARACTERIZED > REPLAYED >
  TYPES_BUILD_ONLY > UNVERIFIED`. The enum order follows the docs (strongest first) and the rank is
  the single comparison point for CLI/PR.
- **M2 — Stages.** `ProofStage`: `BUILD`, `CHARACTERIZE`, `REPLAY`, `TESTS`. `CheckResult` gains
  `stage: ProofStage = TESTS` (backward compatible) and keeps `kind: baseline|after`. `to_dict()` adds
  `stage`.
- **M3 — Plan.** `ProofPlan(tests=(), characterize=(), replay=(), build=())`, each a command
  sequence. Frozen, slots. An empty plan is `NO_PROOF_COMMAND`. A string command is a `ValueError`
  (no shell), as in T4.
- **M4 — Runner.** `prove_plan(proposal, root, plan, timeout=300.0) -> ProofResult`:
  1. Preconditions as T4 (`NO_PATCH_PROPOSED`/`PATCH_DID_NOT_APPLY`); empty plan → `NO_PROOF_COMMAND`.
  2. Copy the repo once.
  3. Run every configured stage's baseline in stage order `BUILD`, `CHARACTERIZE`, `REPLAY`,
     `TESTS`. A red baseline or timeout stops before applying: `BUILD_FAILED_BEFORE`,
     `CHARACTERIZE_FAILED_BEFORE`, `REPLAY_FAILED_BEFORE`, `TESTS_FAILED_BEFORE`, or
     `CHECK_TIMED_OUT`; the failing check is recorded with its stage.
  4. Apply `proposal.diff` once (`PATCH_DID_NOT_APPLY` on failure).
  5. Run every configured stage's after-check in the same order. A red after or timeout →
     `BUILD_FAILED_AFTER` / `CHARACTERIZE_FAILED_AFTER` / `REPLAY_FAILED_AFTER` /
     `TESTS_FAILED_AFTER` / `CHECK_TIMED_OUT`.
  6. If every configured stage is green, the level is the strongest configured stage
     (`tests > characterize > replay > build`). `checks` holds every baseline/after `CheckResult`.
  7. `baseline`/`after` keep their T4 meaning: the tests check when tests are configured, otherwise
     the strongest stage's check. `patch_applied` is true only after a successful apply.
  8. Delete the copy on every path.
- **M5 — Backward-compatible shortcut.** `prove(proposal, root, command, timeout)` delegates to
  `prove_plan` with `ProofPlan(tests=tuple(command))`. The existing causes and results are
  unchanged; the new `checks` list and `stage` field are additive.
- **M6 — Result.** `ProofResult` gains `checks: tuple[CheckResult, ...] = ()`. Invariants:
  `TESTS_PASSED`/`CHARACTERIZED`/`REPLAYED`/`TYPES_BUILD_ONLY` require a green after-check for that
  stage (when `checks` is non-empty) and `patch_applied`; `UNVERIFIED` requires a cause. When
  `checks` is empty (old constructors), the T4 invariants apply. `to_dict()` adds `checks`.
- **M7 — Causes.** Add `BUILD_FAILED_BEFORE`, `BUILD_FAILED_AFTER`, `CHARACTERIZE_FAILED_BEFORE`,
  `CHARACTERIZE_FAILED_AFTER`, `REPLAY_FAILED_BEFORE`, `REPLAY_FAILED_AFTER`, `NO_PROOF_COMMAND`.
  Keep the existing seven. A timeout keeps `CHECK_TIMED_OUT`; the stage is on the check record.
- **M8 — CLI commands.** `tenon fix` accepts `--build CMD`, `--characterize CMD`, `--replay CMD` (each
  `shlex`-split, no shell) alongside `--check CMD` (tests). `[tenon]` gains `build`,
  `characterize`, `replay` arrays next to `command`. The plan is assembled from the flags/config;
  `--check` remains the tests command.
- **M9 — CLI ladder.** `--require` and `[tenon] require` accept all five levels. `fix_exit` uses
  `PROOF_RANK`. The summary counts `passed`, `characterized`, `replayed`, `build_only`, `unverified`,
  `prs_opened`, `prs_refused`. The text and JSON show every configured stage's command and both exit
  codes, plus the level and cause.
- **M10 — PR gate.** `write_pr` gains `required: ProofLevel = TESTS_PASSED` and
  `allow_below_required: bool = False` (the existing `allow_unverified` remains a deprecated alias).
  If `rank(proof.level) < rank(required)` and not allowed → `PrRefusal.BELOW_REQUIRED_LEVEL`; if
  allowed → a draft. A result at or above the requirement opens a normal PR, except `UNVERIFIED`,
  which is always a draft. The CLI `--allow-below-required` (alias `--allow-unverified`) supplies it.
- **M11 — PR text.** The title already uses the level. The body adds fixed sentences and
  "what this proves" paragraphs for `CHARACTERIZED`, `REPLAYED` and `TYPES_BUILD_ONLY`, each naming
  the command and the stage's limit. No level is called "verified" beyond what ran.
- **M12 — Determinism and offline.** Every new field is serialised canonically; the suite uses
  fixture commands only; no network, model or real API call.

### Should have

- **S1 — `ProofPlan.from_commands(...)`**? Skipped if it adds no clarity; the dataclass is enough.
- **S2 — Stage-ordered report.** The text groups by stage in `BUILD, CHARACTERIZE, REPLAY, TESTS`
  order, matching the runner.
- **S3 — Config validation.** A `[tenon]` command that is not an array of non-empty strings is a
  named config error; an empty stage is omitted from the plan.

### Nice to have

- **N1 — `--require` in `tenon check`?** No: check has no proof. Keep it on `fix` only.
- **N2 — Per-stage timeouts.** One timeout for all commands in this card; a later card can split.

## Data Model

```
ProofStage      BUILD | CHARACTERIZE | REPLAY | TESTS
ProofLevel      TESTS_PASSED | CHARACTERIZED | REPLAYED | TYPES_BUILD_ONLY | UNVERIFIED
PROOF_RANK      TESTS_PASSED:4, CHARACTERIZED:3, REPLAYED:2, TYPES_BUILD_ONLY:1, UNVERIFIED:0
ProofCause      NO_PATCH_PROPOSED | PATCH_DID_NOT_APPLY | NO_TESTS_FOUND | NO_PROOF_COMMAND
                TESTS_FAILED_BEFORE | TESTS_FAILED_AFTER
                BUILD_FAILED_BEFORE | BUILD_FAILED_AFTER
                CHARACTERIZE_FAILED_BEFORE | CHARACTERIZE_FAILED_AFTER
                REPLAY_FAILED_BEFORE | REPLAY_FAILED_AFTER
                CHECK_TIMED_OUT | COPY_FAILED

CheckResult     kind: baseline|after, stage: ProofStage, command, returncode, timed_out,
                stdout_tail, stderr_tail
ProofPlan       tests, characterize, replay, build: tuple[str, ...]
ProofResult     level, cause, baseline, after, patch_applied, checks: tuple[CheckResult, ...]
```

The five-level enum order follows the docs (strongest first); `PROOF_RANK` is the comparison.
`CheckResult.stage` defaults to `TESTS` so every shipped constructor keeps working.

## API Contract

```python
from tenon.prove import ProofPlan, prove_plan, prove

plan = ProofPlan(
    build=("python", "-m", "compileall", "-q", "."),
    tests=("python", "-m", "pytest", "-q"),
)
result = prove_plan(proposal, "path/to/repo", plan)
result.level      # TESTS_PASSED, CHARACTERIZED, REPLAYED, TYPES_BUILD_ONLY or UNVERIFIED
result.cause      # None or the failing stage's cause
result.checks     # every baseline/after CheckResult, with stage

# The old shortcut still means a tests-only plan:
result = prove(proposal, "path/to/repo", ["python", "-m", "pytest", "-q"])
```

CLI:

```sh
tenon fix repo --old old.json --new new.json \
  --build "python -m compileall -q ." \
  --check "python -m pytest -q" \
  --require TESTS_PASSED
```

## Technical Considerations

- **Why run all configured stages.** The level is an observation of what ran, not a choice. Running
  only the required stage would hide a red build when tests pass. Running all and failing closed is
  the honest shape.
- **Why any failure is UNVERIFIED.** A green build is not a weaker proof when the tests are red; the
  patch is not acceptable. The build result stays in `checks` so the report shows it, but the level
  does not promote it.
- **Why baseline-first across stages.** The patch is applied once, after every baseline. A red
  baseline is never blamed on the patch, and a build baseline failure avoids applying anything.
- **Why the primary `baseline`/`after` remain.** T4/T5/CLI consumers already read them. New
  consumers read `checks`; old constructors and the tests-only shortcut keep working.
- **Two configs, one plan.** The CLI turns `--check`/`--build`/`--characterize`/`--replay` and the
  `[tenon]` arrays into a `ProofPlan`; the runner never reads the config file.
- **The PR gate needs the requirement.** `write_pr` cannot know what the user required; the CLI
  passes it. The writer ranks and drafts/refuses. `allow_unverified` remains an alias so the T5
  callers and the old flag keep working.
- **UNVERIFIED is always a draft.** Even when `--require UNVERIFIED` makes the exit 0, the PR is a
  flagged suggestion. The label is honest; the draft is the product stance.
- **The `CHARACTERIZED`/`REPLAYED` commands are user-supplied in this card.** The label means "the
  command the user supplied for this stage exited 0 before and after"; the PR quotes it. Tenon does
  not generate the tests or record the traffic; those are separate cards. The docs' wording is
  softened to match what actually ran.

## Risks & Open Questions

- **R1 (repos without tests).** This is the mitigation: `TYPES_BUILD_ONLY`, `CHARACTERIZED` and
  `REPLAYED` give an honest label instead of `UNVERIFIED`. It does not make a weak check strong.
- **R2 (a verified PR still breaks production).** The PR quotes the stage command and the level; a
  build-only PR is visibly weak. No level is called verified beyond what ran.
- **User-supplied characterization/replay can be weak.** The label reflects the command, not its
  quality. The body says which command ran and that Tenon did not generate/record it. A future card
  can generate tests or record traffic.
- **Test churn.** The two-value enum, seven causes, `to_dict` keys, CLI `--require`, `fix` summary and
  PR sentences are all pinned by tests. The implementation updates them deliberately; a missed pin
  is a red test, not a silent drift.
- **Stage order.** A failure in `BUILD` is reported before a failure in `TESTS` because build runs
  first. The check records show which stages ran; the level is UNVERIFIED either way.
- **Timeout granularity.** One timeout for all stages; a slow test suite can time out the build if
  they share a short timeout. The default 300 s is per command in T4; T7 keeps it per command.
- **Open question — should a red weaker stage block a green stronger stage?** No: any configured red
  stage is UNVERIFIED, regardless of order. A user who only cares about tests should not configure a
  build. Documented.
- **Open question — `NO_TESTS_FOUND` vs `NO_PROOF_COMMAND`.** The shortcut `prove(..., [])` keeps
  `NO_TESTS_FOUND`; an empty `ProofPlan` is `NO_PROOF_COMMAND`. Both are named; the distinction is
  tests-only vs no stage at all.

## Out of Scope

- Generating characterization tests or recording/replaying real traffic (the commands are supplied).
- Per-stage timeouts, retries, dependency installation.
- T8 MCP/probe, T9 benchmark, T10 provider layer.
- New proposer rules; the patch is still T3's diff.
- A CLI `--require` on `check` (no proof there).

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `proof-result` | `ProofStage`, five `ProofLevel`s, rank, expanded `ProofCause`, `CheckResult.stage`, `ProofResult.checks`, invariants and JSON. No subprocess, no copy. |
| `proof-plan` | `ProofPlan`, `prove_plan`, stage order, baseline-first multi-stage run, apply once, strongest-level selection, backward-compatible `prove`. No CLI, no PR. |
| `proof-cli` | Stage flags/config, `--require` all levels, `fix_exit` rank, text/JSON stage reports, `--allow-below-required` (alias). No PR writer. |
| `proof-pr` | `write_pr` required/allow-below, `BELOW_REQUIRED_LEVEL`, draft rule, level sentences/paragraphs. No runner. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | R1 and the advertised-but-unimplemented ladder are concrete. |
| User understanding | 🟢 | No-tests, characterization, replay, required-level and reviewer personas. |
| Success metrics | 🟢 | Five levels, rank, any-failure-UNVERIFIED, CLI exit, PR gate; all testable. |
| Scope clarity | 🟢 | User-supplied commands; generators/recorders, T8/T9 and per-stage timeouts excluded. |
| Edge cases & risks | 🟡 | User-supplied commands can be weak; the PR text must say what they are, not oversell. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Extends T4's runner and result; no new dependency. |
| Go-to-market | 🟢 | Unlocks repos without tests, the largest adoption blocker (R1). |

**Areas to strengthen before sharing:** the label `CHARACTERIZED`/`REPLAYED` now means
"user-supplied command passed", not "Tenon generated/recorded it". The PR body must say that in the
same sentence as the label, or a reviewer will overread it.

**The question I would want answered before greenlighting this:** *If a user supplies a
characterization command that only checks a trivial import, the PR says `[CHARACTERIZED]` and a
reviewer may read "behavior verified". What stops that?* The answer this card records: the body
quotes the exact command, says Tenon did not generate it, and the level is only as strong as the
user's check. The alternative — refusing the label until Tenon generates the tests — is a larger card
and leaves R1 unsolved.
