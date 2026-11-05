# Tenon: Capability Roadmap

Engine capabilities in build order. Each lands test-first.

| ID | Capability | Depends on | Guardrail tie-in | State |
|---|---|---|---|---|
| **T1** | **Change detection.** Diff two OpenAPI versions into typed change records. | none | Machine-readable sources first | **Shipped 2026-10-26** |
| **T2** | **Call-site location (Python).** Find usages of a changed symbol or endpoint with file and line. | T1 | Ambiguity reported, never guessed | **Shipped 2026-10-29** |
| **T3** | **Patch proposer seam.** Rule-based proposer for mechanical changes; optional BYOK model proposer. | T1, T2 | A model proposes only | **Shipped 2026-10-29** |
| **T4** | **Proof runner.** Apply the patch in an isolated working copy, run the user's tests, record the proof level. | T3 | Execution decides the label | **Shipped 2026-10-29** |
| **T5** | **PR writer.** Branch and PR stating the proof level; never pushes to the default branch. | T4 | No merging | **Shipped 2026-11-05** |
| **T6** | **TypeScript/JavaScript locator.** Same contract as T2. | T1 | | **Shipped 2026-11-05** |
| **T7** | **Proof ladder.** Types/build-only, characterization tests, recorded-call replay. | T4 | Weak proof labelled weak | **Shipped 2026-11-06** |
| **T8** | **MCP diffs and probe mode.** Diff MCP tool schemas; run an agent against an API or server. | T1, T4 | | Not started |
| **T9** | **Benchmark and history.** Labelled (change, patch, proof, outcome) corpus. | T4, T5 | Measure against human outcomes | Not started |
| **T10** | **Provider layer and GitHub App (hosted).** Vendor-pushed migrations. | T4-T9 | Opt-in, BYOK | Not started |
| **T11** | **More languages.** Go, Rust, C#. | T2 pattern | One at a time | Not started |

### T1 as shipped (2026-10-26)

`src/tenon/detect/`: `load`/`parse` (OpenAPI 3.0.x/3.1.x, YAML or JSON, local `$ref` resolution),
`diff` producing 13 typed record kinds with `breaking` and `confidence`, and rename inference that
pairs only unambiguous removed/added records. Bad input is a named refusal with a JSON pointer.
136 tests, offline and deterministic.

Known limits at this level: a subtree carrying an unsupported composition keyword, or a cyclic
`$ref`, is skipped and recorded in `DiffResult.unanalyzed` rather than refusing the document; added
optional *parameters* produce no record (no `parameter_added` kind); request-body/media-type/response
add-remove and `additionalProperties` are not walked. Resolution is memoised per raw node, so a
shared-ref DAG stays linear: the real Stripe `v2500` -> `v2596` pair loads in 3.8/4.2 s and diffs in
0.23 s into 289 changes, 52 breaking and one real rename
(`docs/planning/lazy-ref-resolution/evidence.md`). Composition subtrees are still skipped and
recorded: 1,867 of the run's 1,873 `unanalyzed` entries are `UNSUPPORTED_COMPOSITION`, the other 6
are cycle markers. A real Twilio pair remains committed as the offline guard.

## Sequencing

T1 and T2 first, then T3-T5 give the first end-to-end PR. T6-T8 widen reach and proof depth. T9
makes the result publishable. T10 is the business and is deferred.

### T2 as built (2026-10-28)

`src/tenon/locate/`: `change → query` (explicit `METHOD /path` and `Schema.field` mappings, then
inference from path segments and HTTP verb), an `ast` scan of modules that reach the configured SDK
package (one-hop aliases, character-precise file/line/column), and a single certainty policy that
returns `certain` sites plus ambiguity groups with named reasons (`DYNAMIC_KWARGS`,
`DYNAMIC_GETATTR`, `ALIAS_CHAIN`, `UNROOTED_RECEIVER`, `MULTIPLE_CANDIDATES`, `UNMAPPED_SYMBOL`).
207 tests, offline and deterministic.

Known limits at this level: an SDK-shaped repo is assumed (a raw `requests`/`httpx` client yields
`NO_SDK_IMPORT`); aliases resolve one hop past an assignment-created alias; operation-scoped field
changes report only the resolved call's arguments; `AMBIGUOUS_CALL_SITE` is the aggregate cause T4
will report, not a T2 output. Mocked-operation assertion keywords are located for
`assert_called_with` / `assert_called_once_with`; `call_args.kwargs["field"]`, `call_args[1]["field"]`
and `assert_has_calls` are not.

### T3 as built (2026-10-29)

`src/tenon/propose/`: a `Proposal` contract, a deterministic `RuleProposer` for field renames, and
an assembly that verifies every candidate span against the current source before applying it in
memory and rendering a unified diff. Ambiguous sites, uneditable call sites and stale spans become
skipped suggestions with named reasons; a proposal carries `NO_RULE`, `NO_CERTAIN_SITES`,
`NO_EDITABLE_SITES` or `STALE_SITE` when nothing survives. 114 tests, offline and deterministic.

Known limits at this level: one rule only (field rename, `keyword`/`dict_key`/`attribute` shapes);
removals, required additions, type changes and endpoint renames have no mechanical fix; a
proposer seam exists but no model ships; nothing is applied, so every proposal is unverified until
T4; a file without a final newline produces a diff `git apply` will reject (documented shortcut).

### T4 as built (2026-10-29)

`src/tenon/prove/`: a proof-result contract (`TESTS_PASSED` / `UNVERIFIED` with a closed cause set),
an isolated copy that drops VCS and cache state, `git apply` of the exact diff T5 will ship, and a
baseline-first runner with a timeout and capped output tails. A red baseline is
`TESTS_FAILED_BEFORE` and never applies the patch. 105 tests, offline.

Known limits at this level: only `TESTS_PASSED` and `UNVERIFIED` exist (`CHARACTERIZED`, `REPLAYED`
and `TYPES_BUILD_ONLY` are T7); one command, no retries, no dependency installation; the copy is not
a sandbox and the user's command is arbitrary code the user chose to run; a repo that depends on a
venv or generated state inside the tree may not be runnable in the copy.

### T5 as built (2026-11-05)

`src/tenon/pr/`: a deterministic `PrDraft` (title, body, branch, commit message), `PrResult` with a
closed refusal set, `render_pr` (the level in the title; change, check command and exit codes, files,
skipped sites and optional unanalyzed subtrees in the body; no duplicated diff), and `write_pr`
(clean checkout and origin required; an isolated `git clone`; `git apply` of the exact proven diff;
commit with the source repository's identity; `git push --set-upstream`; `gh pr create`). The
`Remote` protocol is the host seam; `GitGhRemote` is the real `git`+`gh` adapter, replaced by a fake
in tests. `UNVERIFIED` refuses by default and opens a draft only with `allow_unverified=True`. The
writer never force-pushes, never pushes the base branch and has no merge path. 131 tests in
`tests/pr/`; 745 total, offline.

Known limits at this level: the clone starts from the checkout's HEAD, so run from the branch the
PR should be based on (normally the default branch); a feature-branch HEAD would put its extra
commits in the PR. One PR per proposal; a dirty checkout is refused, not stashed; same-repository
branches only (no forks); an existing branch is `BRANCH_EXISTS`, never updated or forced; a push that
succeeds followed by a failed PR leaves the branch on the remote; the real `gh` call is not exercised
in CI (the adapter argv and URL parsing are unit-tested; the offline end-to-end uses a local bare
remote with `create_pr` replaced); submodules and LFS content are not fetched into the clone; the
caller chooses the check command, so T5 cannot know it was a subset.

### T6 as built (2026-11-05)

`src/tenon/locate/`: `ts_scan.py` (tree-sitter 0.26, TypeScript 0.23, JavaScript 0.25) discovers
`.ts/.mts/.cts/.tsx/.js/.jsx/.mjs/.cjs`, resolves ESM/CommonJS imports, relative-import reachability
and one-hop aliases, and emits the shipped `Hit`/`Dynamic`/`ScanResult` evidence. `ts_config.py` is
`TsLocateConfig` (npm package name); `ts_locate.py` is `locate_ts`, which reuses `query.derive` and
the one `resolve` certainty policy. No new `SiteShape`, `AmbiguityReason` or `LocateReason` values;
`keyword`/`dict_key`/`attribute`/`call` mean the same spans. The CLI accepts `--language ts` and
`[locate] language = "ts"`. 1,006 tests, offline; no Node or `tsc` for analysis.

Known limits at this level: relative imports only (`tsconfig` paths and workspace/package `exports`
are not resolved); JSX attribute names are parsed but not sites; no type inference, so a
factory-returned client is unrooted; a parse-error file is skipped; static string subscripts are
`DYNAMIC_GETATTR`; T4's isolated copy still drops `node_modules`, so a real TS `npm test` may be
`TESTS_FAILED_BEFORE` in the proof copy while `tenon check` works; the grammar versions are pinned.

### T7 as built (2026-11-06)

`src/tenon/prove/`: `ProofStage` (build/characterize/replay/tests), the five-level `ProofLevel`
(`TESTS_PASSED > CHARACTERIZED > REPLAYED > TYPES_BUILD_ONLY > UNVERIFIED`), `PROOF_RANK`,
stage-specific causes, `CheckResult.stage` and `ProofResult.checks`. `ProofPlan` + `prove_plan` run
every configured stage's baseline, apply the diff once, run every after-check, and fail closed: any
configured red stage is `UNVERIFIED` with its cause; the level is the strongest stage only when every
configured stage is green. `prove` remains a tests-only shortcut. The CLI adds `--build`,
`--characterize`, `--replay`, the five-level `--require`, and `--allow-below-required`. T5's
`write_pr` takes `required`/`allow_below_required`: a normal PR at or above the requirement, a draft
below with opt-in, `UNVERIFIED` always a draft, and `BELOW_REQUIRED_LEVEL` otherwise. 1,178 tests,
offline.

Known limits at this level: the characterization and replay commands are user-supplied; Tenon does
not generate the tests or record the traffic, so the label is only as strong as the command (the body
says so). All stages share one timeout; a red weaker stage fails the whole result even when a stronger
stage is green; per-stage timeouts and generators/recorders are later cards. A `TYPES_BUILD_ONLY` PR
is a normal PR only when the user requires that level; otherwise it is a refusal or an opted-in draft.




## Open questions

- Which vendor and SDK is the first real case? Pick one that publishes OpenAPI and has a public
  changelog of breaking changes.
- How to handle changes with no machine-readable source (changelog only)? Likely flag, not patch.
