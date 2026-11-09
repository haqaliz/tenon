# Tenon: Architecture

Design intent. **T1 (detect), T2 (locate, Python), T3 (propose), T4 (prove), T5 (PR), T6
(locate, TypeScript/JavaScript), T7 (proof ladder), T8a (MCP tool-schema diffs), T8b (Python MCP
tool-call locator), T8c (`tenon probe`), T9 (benchmark corpus), T10a (GitHub App remote), T10b
(provider migration bundle), T10c (local provider fan-out), T10d (installed provider fan-out) and
the `tenon check` / `tenon fix` / `tenon provider migrate` / `tenon probe` / `tenon corpus` CLI are
implemented** under
`src/tenon/detect/`, `src/tenon/locate/`, `src/tenon/propose/`, `src/tenon/prove/`, `src/tenon/pr/`,
`src/tenon/provider/`, `src/tenon/probe/`, `src/tenon/corpus/` and `src/tenon/cli/`. The later
stages are not.

## Pipeline

```
API change source (OpenAPI v1 -> v2 | MCP schema | SDK metadata)
        |
        v
  T1 detect   ---->  typed Change records
        |
        v
  T2 locate   ---->  call sites in the user's repo (file, line, confidence)
        |
        v
  T3 propose  ---->  candidate diff (rules first; BYOK model optional)
        |
        v
  T4 prove    ---->  apply in isolated copy, run user's checks -> proof level
        |
        v
  T5 PR       ---->  branch + PR that states the proof level
```

## Layout

```text
src/tenon/
  detect/     T1/T8a: spec parsers, differ, Change records <- built (OpenAPI + MCP)
  locate/     T2/T6/T8b: per-language call-site finders   <- built (Python + TS/JS + MCP)
  propose/    T3: proposer seam, rule-based mechanical fixes  <- built (rename only)
  prove/      T4/T7: working-copy runner, proof ladder  <- built (all five levels)
  pr/         T5/T10a/T10d: branch/PR writer + installed discovery <- built (gh + GitHub App)
  provider/   T10b/T10c: bundle and repos-file loaders    <- built (JSON + text)
  probe/      T8c: MCP stdio probe, agent plan, report  <- built (tools only)
  corpus/     T9: benchmark records                         <- built (JSONL + report)
  cli/        tenon check | fix | provider migrate | probe | corpus <- built
tests/        offline; fixture repos and specs; no network, no model calls
```

## Key decisions

- **Change record is the unit.** Everything downstream consumes typed Change records, so adding a
  source (MCP, SDK metadata) does not touch locate or prove. T8a reuses the record for MCP tools with
  a synthetic `method="tool"` operation; the only taxonomy extension is
  `ADDITIONAL_PROPERTIES_CHANGED`. T8b adds `locate_mcp` for the high-level Python `call_tool`
  pattern behind the same `LocateResult`.
- **One certainty policy, per-language scanners.** T2 and T6 both emit `Hit`/`Dynamic`/`ScanResult`
  evidence and call the same `resolve` rule table. Python parses with `ast`, TypeScript/JavaScript
  with tree-sitter; neither runs the scanned code, needs Node, or infers types.
- **Proof is a ladder, chosen by the user.** `--require
  TESTS_PASSED|CHARACTERIZED|REPLAYED|TYPES_BUILD_ONLY|UNVERIFIED`. The runner configures up to four
  stage commands (`build`, `characterize`, `replay`, `tests`), runs every baseline, applies the patch
  once, runs every after-check, and fails closed: any red configured stage is `UNVERIFIED` with that
  stage's cause; the level is the strongest stage only when every configured stage is green. A
  stronger level satisfies a weaker requirement. If the required level cannot be reached, the result
  is a flagged suggestion or an opted-in draft, not a verified PR.
- **Isolated working copy and clone.** T4 patches a copy; T5 clones the clean checkout to a temporary
  directory and commits there. The user's checkout is never modified or given a Tenon branch.
- **The PR is a seam, not a merge.** T5 renders a deterministic draft, pushes only the new branch and
  opens the PR through `GitGhRemote` (`git` + `gh`). It never force-pushes, never pushes the base
  branch and has no merge path. A result at or above the required level opens a normal PR; below it
  is `BELOW_REQUIRED_LEVEL` or, with explicit opt-in, a draft; `UNVERIFIED` is always a draft.
- **Probe is a readiness observation, not proof.** T8c starts a local MCP server over stdio, lists
  its tools, runs user tasks through a user-supplied `--agent` command (JSON request in, JSON plan
  out), executes the plan itself and reports what worked. No model ships; Tenon makes no network
  call; the report says "worked in this run", never "verified".
- **The GitHub App is a host adapter, not a new pipeline.** T10a implements the same `Remote` protocol
  with an installation token; T5's clone/commit/push/PR guardrails and no-merge stance are unchanged.
  The token is kept out of argv, the remote URL and error details; the app is self-hosted.
- **The bundle is config, not a new pipeline.** T10b serializes the provider-side `CliConfig`
  (identity, spec paths, locate, require, stage commands) and `tenon provider migrate` loads it into
  the same detect → locate → propose → prove → optional PR flow. T10c adds a local repos file
  and runs that flow sequentially once per listed checkout, reusing one bundle/config and one PR
  remote; a bad path is a per-repo failure, a shared spec refusal aborts, and there is no rollback.
  The bundle never upgrades a proof level and adds no PR branding. Installed/hosted fan-out and a
  service are T10d.
- **The benchmark is descriptive, not a claim.** T9 records `(change, patch, proof, outcome)` in a
  local JSONL corpus. A merge rate uses only real outcomes (`merged`, `rejected`, `closed`,
  `incident`); `local_only`/`pending` never count as success. The public seed has no merge outcomes,
  so its rate is `n/a`.
- **Determinism.** Detection, location and PR text are deterministic for the same inputs. The
  model proposer is the only non-deterministic piece, behind an injectable seam; tests use
  recorded proposals.
- **BYOK / local only** for any model use. Keys come from the environment and are never committed.
- **UNVERIFIED causes** (shipped): `NO_PATCH_PROPOSED`, `PATCH_DID_NOT_APPLY`, `NO_PROOF_COMMAND`,
  `NO_TESTS_FOUND`, `TESTS_FAILED_BEFORE`, `TESTS_FAILED_AFTER`, `BUILD_FAILED_BEFORE`,
  `BUILD_FAILED_AFTER`, `CHARACTERIZE_FAILED_BEFORE`, `CHARACTERIZE_FAILED_AFTER`,
  `REPLAY_FAILED_BEFORE`, `REPLAY_FAILED_AFTER`, `CHECK_TIMED_OUT`, `COPY_FAILED`.
- **A thin CLI with honest exit codes.** `tenon check`, `tenon fix` and `tenon provider migrate`
  parse, configure, compose and render; they add no detection or proof logic. `check` exits 0 clean /
  1 affected or unanalyzable / 2 usage; `fix` exits 0 required proof / 1 not / 2 usage.
  `provider migrate` exits 0 every repo passed / 1 any repo failed / 2 usage, bundle, repos-file,
  app-identity, discovery or shared spec/config errors. `--json` is one byte-stable object; `fix`
  prints unless `--open-pr`, which delegates to T5. No traceback.
- **Baseline first.** Run the user's checks before patching, so a red baseline is reported as such
  and not blamed on the patch.

## CLI

`tenon check <repo> --old SPEC --new SPEC [--source openapi|mcp] [--language python|ts] [--json]`
lists affected call sites and exits 0 when clean, 1 when a site or an unanalyzable repository is
found.
`tenon fix <repo> --old SPEC --new SPEC [--source openapi|mcp] [--language python|ts] [--build CMD]
[--characterize CMD] [--replay CMD] [--check CMD] [--require LEVEL] [--allow-below-required]
[--open-pr] [--remote gh|app] [--app-id ID] [--app-installation-id ID] [--app-private-key PATH]
[--api-url URL] [--json]` proposes, proves and prints the diff; `--open-pr` delegates to T5. `LEVEL`
is one of the five proof levels; the strongest configured stage that is green is the result.
`--open-pr --remote app` builds `GitHubAppRemote`/`GitHubAppToken` instead of `GitGhRemote`; the app
needs `contents:write` and `pull_requests:write`. Its inputs come from those flags or
`TENON_GITHUB_APP_ID`, `TENON_GITHUB_APP_INSTALLATION_ID`, `TENON_GITHUB_APP_PRIVATE_KEY` (a path)
and `TENON_GITHUB_API_URL`; a flag wins. An explicit `--remote` requires `--open-pr`; missing inputs
or an unreadable key exit 2. The app remote is self-hosted: webhooks and a hosted service are
deferred; `--installed` reuses the same app identity for discovery and cloning.
`tenon provider migrate [<repo>|--repos FILE|--installed] --bundle PATH [--open-pr] [--remote gh|app]
[--app-id ID] [--app-installation-id ID] [--app-private-key PATH] [--api-url URL] [--check CMD]
[--require LEVEL] [--allow-below-required] [--allow-unverified] [--json]` builds the `CliConfig`
from a JSON migration bundle (provider/migration, source/language, relative spec paths, locate
config, required proof, stage commands, `breaking_only`), applies `--check`/`--require` over it and
runs the same fix pipeline and exit code. The text is a `provider`/`migration` header plus the fix
report; `--json` is the provider envelope (`command`, `provider`, `migration`, `repo`, `results`,
`summary`). The bundle never upgrades the proof level; `--open-pr` uses the same T5 gate and gh/app
remote. `<repo>`, `--repos` and `--installed` are mutually exclusive and exactly one is required.
`--repos FILE` reads a UTF-8 list (one local path per line; blanks and `#` comments ignored, `~`
expanded, relative paths resolved against the file) and runs the bundle sequentially once per
checkout with one config and, under `--open-pr`, one remote and one PR per repo. A non-directory
path is a per-repo `error: not a directory` and the others still run; text adds one `repo:` block
per repo and `repos: N, passed: X, failed: Y`, and `--json` is the fan-out envelope
(`command`, `provider`, `migration`, `repos: [{repo, results, summary, exit, error}]`, `summary`).
Exit 0 only when every repo passed and every requested PR opened, 1 when any repo failed, 2 on
usage/bundle/repos-file/app-identity/discovery/global spec/config errors; a shared spec refusal
aborts.
`--installed` discovers the app installation's non-archived repositories through
`GET /installation/repositories` (paginated, API order), mints the installation token once, shares it
across discovery, every clone and the one `GitHubAppRemote` (built from a `StaticToken` with that
value) under `--open-pr`, and runs the same per-repo loop. It requires the app identity above; a
missing input or unreadable key exits 2, and `--remote gh` is rejected (`--installed requires
--remote app`). Each repo is cloned by the app credential helper into a temp dir (token in the git
child env, never argv/URL) that is removed even on failure; without `--open-pr` no PR call is made
(dry run). A clone failure is a per-repo `error` and the others still run; a token/list failure
exits 2. The report keys are `owner/name`. There is no rollback, parallelism or retry; webhooks, a
database and a hosted runner are deferred.
`tenon probe --server-cmd CMD --tasks FILE --agent CMD [--timeout SEC] [--json]` starts an MCP
server over stdio, lists its tools, runs every task through the agent command and reports what
worked. Exit 0 when every task passed, 1 when one failed, 2 on usage/connection. The task file and
agent contract are documented in `docs/planning/mcp-probe/prd.md`.

`tenon corpus record --from FIX_JSON --repo URL --commit SHA --outcome STATUS --date YYYY-MM-DD
--corpus PATH` appends records; `tenon corpus outcome` updates a human outcome; `tenon corpus
report` prints the level/outcome table and merge rate. `docs/benchmark/` holds the public seed.

`tenon.toml` provides `[locate]` (`source`, `language`, `sdk_package`, mappings) and `[tenon]`
defaults; flags override. Exit 2 on usage or bad input. Never a traceback.

`--source mcp` selects `load_mcp` / `diff_mcp` / `locate_mcp`; the Python high-level `call_tool`
pattern is the only locator in this slice. `language=ts` + `source=mcp` is a named error.

## Open questions

- T6 follow-ups: `tsconfig`/workspace path aliases, JSX attribute sites, and a T4 copy policy for
  `node_modules` so a real TS `npm test` can run in the proof copy.
- T7 follow-ups: generation of characterization tests, recording/replaying real traffic, and
  per-stage timeouts. The current commands are user-supplied and share one timeout.
- T8 probe follow-ups: HTTP/SSE transport, an OpenAPI/API probe, resources/prompts,
  sampling/roots/elicitation, and `--stop-on-error`. The shipped probe is stdio/tools only and runs
  the user's local server/agent without a sandbox.
- T9 follow-ups: GitHub merge/incident detection, `tenon fix --corpus` auto-record, and a hosted
  public benchmark (T10). The shipped corpus is local/opt-in and its public seed has no merge
  outcomes yet.
- T5 follow-ups: fork remotes, cleanup of a branch left by a failed PR call, and submodule/LFS
  content in the clone. The current writer refuses a dirty tree and never force-pushes.
- PyPI distribution name: `tenon` is taken; `tenonhq` was free when checked.
- Phase 3: T10a (GitHub App remote), T10b (provider migration bundle), T10c (local provider
  fan-out) and T10d (installed provider fan-out) shipped; a hosted/webhook-driven service and T11
  (Go/Rust/C#) are not started.
