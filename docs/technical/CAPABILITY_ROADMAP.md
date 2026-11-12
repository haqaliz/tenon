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
| **T8** | **MCP diffs and probe mode.** Diff MCP tool schemas; run an agent against an API or server. | T1, T4 | | **Shipped 2026-11-07** |
| **T9** | **Benchmark and history.** Labelled (change, patch, proof, outcome) corpus. | T4, T5 | Measure against human outcomes | **Shipped 2026-11-07** |
| **T10** | **Provider layer and GitHub App (hosted).** Vendor-pushed migrations. | T4-T9 | Opt-in, BYOK | **Shipped 2026-11-11 (MVP)** — GitHub App remote, provider bundle, local/installed fan-out and a self-hosted service; a hardened cloud deployment is later |
| **T11** | **More languages.** Go, Rust, C#. | T2 pattern | One at a time | **Shipped 2026-11-11** — Rust, Go and C# locators |
| **T12** | **Receiver tracking.** Method/fluent chains through an explicitly typed client. | T11 | Explicit evidence only | **Shipped 2026-11-12** — Rust, Go, C#, Python and TypeScript |
| **T13** | **Hardened deployment.** Container, TLS proxy, backups, resilience. | T10e | Operator-owned secrets | **Partial 2026-11-12** — deployable Compose + Caddy + readiness shipped; resilience (T13b) not started |

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

### T8a as built (2026-11-07)

`src/tenon/detect/mcp_ingest.py` loads a saved `tools/list` result (envelope or bare array),
normalizes it to a name-keyed mapping, validates tool names/schemas, resolves local `$ref`s and
refuses bad input by name. `mcp_diff.py` emits the shipped `Change`/`DiffResult` records: tool
added/removed as synthetic `method="tool"` operations; input/output schema property
add/remove/required/type/enum; `ADDITIONAL_PROPERTIES_CHANGED` (the 14th kind); nested objects/arrays;
cautious property rename inference; `oneOf`/`anyOf`/cycles recorded in `unanalyzed`. 1,253 tests,
offline. No probe, locator or CLI source switch yet.

Known limits: engine-only at this level (T8b adds the Python `call_tool` locator); no
probe/transport/network; real schemas that lean on `oneOf`/`$ref` will be largely `unanalyzed`;
`ADDITIONAL_PROPERTIES_CHANGED` is `UNSUPPORTED_CHANGE_KIND` downstream; pagination (`nextCursor`)
is ignored; output-schema required semantics are simplified.

### T8b as built (2026-11-07)

`src/tenon/locate/mcp_*.py`: a Python `ast` scanner and `locate_mcp` for the high-level MCP SDK
`call_tool` pattern. A site is certain only when the receiver is an MCP `ClientSession`
import/alias/`with` binding and the tool name is a literal matching the change; argument keys use
the shipped `dict_key`/`keyword` spans; dynamic tool names/payloads and unrooted receivers are named
ambiguity groups. `tenon check` / `tenon fix` accept `--source mcp` and `[locate] source = "mcp"`;
the MCP diff/locator feed the existing propose/prove/PR stages. 1,342 tests, offline.

Known limits: Python only; high-level `call_tool` only (no `send_request`, framework wrappers, or a
session passed through a parameter); no TypeScript MCP locator; output-schema changes locate the tool
call only, not result-field dataflow; a second-hop receiver alias is `ALIAS_CHAIN`.

### T8c as built (2026-11-07)

`src/tenon/probe/`: a stdlib newline-JSON-RPC stdio client (`initialize`, paginated `tools/list`,
`tools/call`, timeouts, named errors), `tasks.json` with optional `tools`/`result_contains`
expectations, and a user-supplied agent command (`--agent`) that receives `{"task","tools"}` and
returns `{"calls":[...]}`. The probe executes the plan, records each call's result/error, evaluates
expectations, and prints a text or byte-stable JSON report. `tenon probe` exits 0 when every task
worked, 1 when one failed, 2 on usage/connection. No model, key, network or new dependency; offline
fake server/agent tests. 1,436 tests.

Known limits: stdio/tools only (no HTTP/SSE, resources/prompts, sampling/roots/elicitation); the
agent is the user's command, so a weak agent yields a weak readiness report (the report shows the
plan/calls); a server logging to stdout corrupts the JSON-RPC stream; no `--stop-on-error`, no
`tenon.toml` probe defaults; the probe runs arbitrary local server/agent code and is not a sandbox.

### T9 as built (2026-11-07)

`src/tenon/corpus/`: a `CorpusRecord` (deterministic id over repo/commit/change/diff; change,
proposal, proof and PR snapshots; six outcomes; user-supplied date/evidence/notes), an append-only
JSONL store with atomic outcome updates, and a report grouping by proof level and outcome. The merge
rate is `merged / (merged + rejected + closed + incident)` and is null until a real outcome exists;
`local_only`/`pending` never count as success. The CLI adds `tenon corpus record --from fix.json`,
`outcome` and `report`. `docs/benchmark/corpus.jsonl` seeds the two public M0.3 cases as
`local_only`/`TESTS_PASSED`; `docs/benchmark/README.md` states the method and the absence of merge
outcomes. 1,571 tests, offline.

Known limits: the corpus is local/opt-in (no upload, no GitHub outcome detection); a `merged` outcome
is a user claim with a URL/evidence, not a Tenon-verified fact; the seed has no merge outcomes, so
every rate is n/a; the records are snapshots and a schema change is a migration; no `fix --corpus`
auto-record.

### T10a as built (2026-11-08)

`src/tenon/pr/`: `GitHubAppToken` mints an RS256 app JWT and exchanges it for an installation token;
`GitHubApi` is a small stdlib REST client with an injectable transport; `GitHubAppRemote` implements
the T5 `Remote` protocol (origin parse, default branch, branch existence, token-safe `git push` via a
credential helper, PR creation). `tenon fix --open-pr --remote app` constructs it from flags/env; the
default remains the user's `gh`. `PyJWT`/`cryptography` are an optional `[app]` extra and dev
dependency; the core install is unchanged. 1,635 tests, offline (test RSA key, fake transport/runner).

Known limits: self-hosted only; the provider bundle, local fan-out and installed discovery shipped
in T10b/T10c/T10d, while webhook events and a hosted service remain later; the private key is the
operator's secret; a malicious git hook or `GIT_TRACE` can still expose the token; Windows is not a
target; no token-expiry refresh beyond one mint per remote.

### T10b as built (2026-11-08)

`src/tenon/provider/`: a `MigrationBundle` (provider/migration identity, source/language, old/new
spec paths relative to the bundle, locate config, `check`/`build`/`characterize`/`replay`, require,
breaking_only) and `load_bundle` with named validation. `tenon provider migrate <repo> --bundle PATH`
runs the shipped detect → locate → propose → prove pipeline (the same `_fix_results`), prints a
provider/migration header plus the fix report or a provider JSON envelope, and with `--open-pr` uses
`gh`/the T10a app remote. `--check`/`--require` override the bundle. 1,738 tests, offline.

Known limits: one repo per run (local multi-repo fan-out shipped in T10c and installed fan-out in
T10d); no webhooks, database or hosted service; no provider note in the PR body; the bundle is
trusted local input (paths/commands), not a sandbox; `command` is accepted as a `tenon.toml` alias
for the documented `check` key.

### T10c as built (2026-11-09)

`src/tenon/provider/repos.py`: `load_repos` parses a UTF-8 repos file (one local path per line,
blank lines and `#` comments ignored, `~` expanded, relative paths resolved against the file's
parent) with named errors for a missing/non-file/non-UTF-8/empty list. `tenon provider migrate
[<repo>|--repos FILE] --bundle PATH` loads the bundle and `CliConfig` once and runs the shipped
`_fix_results` sequentially per listed checkout, constructing the gh/app remote once; a missing
path is a per-repo `not a directory` failure that does not stop the rest. Text is one `repo:` block
per repo plus a `repos/passed/failed` summary; `--json` is a fan-out envelope
(`command`, `provider`, `migration`, `repos:[{repo, results, summary, exit, error}]`, `summary`).
Exit 0 iff every repo passes, 1 if any failed, 2 on usage/bundle/list/global spec errors. 1,774
tests, offline.

Known limits: sequential, no rollback or retries, one app token per run; a listed repo must already
be a local checkout; no provider note in the PR body. Installed fan-out (app discovery and temp
clones) shipped in T10d; a hosted/webhook-driven service remains a later milestone.

### T10d as built (2026-11-10)

`src/tenon/pr/installed.py`: `InstalledRepo` plus `list_installation_repos` (paginated
`GET /installation/repositories` with the installation token, archived repos skipped, named errors
for malformed pages and a 100-page cap) and `clone_repo` (a `tenon-installed-*` temp dir, a shallow
`git clone` with the T10a credential helper and `TENON_GITHUB_TOKEN` in the child env, token scrubbed
from errors, the dir always removed). `tenon provider migrate --installed --bundle PATH` resolves the
T10a app identity, mints one token, discovers the installation's repos, clones each, runs the shipped
`_fix_results` and reuses T10c's text/JSON fan-out report with `repo` = `owner/name`; `--open-pr`
constructs one `GitHubAppRemote` from the same token, while a dry run makes no PR call. A clone
failure is per-repo (exit 1); a token/list failure or a shared bad spec exits 2. 1,843 tests, offline.

Known limits: sequential clones with no retries/rate-limit handling and no rollback; one token per
run; a malicious git hook can read the token from the child env; archived repos are not counted; the
hosted/webhook-driven service is not built.

### T11a as built (2026-11-10)

`src/tenon/locate/rust_{config,scan,locate}.py`: `RustLocateConfig` (one crate identifier plus the
shared `operations`/`fields` mappings), `scan_rust` (tree-sitter-rust over `.rs` files; `use` rooting
with grouped/nested imports and `as` aliases, bare crate paths, associated calls, struct-literal
fields, per-function `let` bindings and field access), and `locate_rust` applying the shipped
`derive`/`resolve` policy unchanged. `--language rust`, `tenon.toml` and provider bundles accept
`rust`; MCP stays Python-only; no Cargo/rustc subprocess or proof preset. A mapping locates the
repo's spelling, but `fix` proposes a rename only when that spelling equals the spec's old name
(the shipped proposer rule); otherwise it reports `NO_EDITABLE_SITES` and the customer renames
manually. 1,925 tests, offline.

Known limits: method chains on an untracked receiver, macros, re-exported crates and multi-hop struct
data flow are not followed (no site, not a guess); a local module named like the crate is a
documented false positive; Go and C# are T11b/T11c. T12a adds explicit receiver tracking for a
client built with `Client::new`/`default`, an annotation or a `receivers` factory.

### T11b as built (2026-11-10)

`src/tenon/locate/go_{config,scan,locate}.py`: `GoLocateConfig` (an import root, an optional
`package_name` and the shared `operations`/`fields` mappings), `scan_go` (tree-sitter-go over `.go`
files; root/subpackage imports with aliases and package-name inference, package-qualified calls,
composite-literal keys, per-function `var`/`:=` bindings and field access), and `locate_go` applying
the shipped `derive`/`resolve` policy unchanged. `--language go`, `--package-name`,
`tenon.toml`/bundle `locate.package_name` and provider bundles accept `go`; MCP stays Python-only;
no Go toolchain or proof preset. 2,013 tests, offline.

Known limits: method chains on an untracked value, dot imports, reflection, generics inference,
`go.mod` parsing and multi-hop composite data flow are not followed (no site, not a guess); a local
variable named like the package alias is a documented false positive; a mapped spelling locates but
is not auto-edited unless it equals the spec's old name; C# is T11c. T12a adds explicit receiver
tracking for an annotation, a composite literal or a `receivers` factory.

### T11c as built (2026-11-11)

`src/tenon/locate/csharp_{config,scan,locate}.py`: `CSharpLocateConfig` (a dotted namespace root
plus the shared `operations`/`fields` mappings), `scan_csharp` (tree-sitter-c-sharp over `.cs` files;
`using`/`global using`/alias roots, simple and qualified type names, static and tracked-`new`
instance calls, object-initializer properties, per-member property access), and `locate_csharp`
applying the shipped `derive`/`resolve` policy unchanged. `--language csharp`, `tenon.toml` and
provider bundles accept `csharp`; MCP stays Python-only; no .NET toolchain or proof preset. 2,099
tests, offline. T11 is complete.

Known limits: method chains on an untracked receiver, `using static`, `dynamic`, reflection,
generics inference, `csproj` parsing and multi-hop initializer flow are not followed (no site, not a
guess); a local type sharing an SDK simple name is a documented false positive; a mapped spelling
locates but is not auto-edited unless it equals the spec's old name. T12b adds explicit receiver
tracking (`new`, an annotation or a `receivers` factory).

### T12a as built (2026-11-12)

`RustLocateConfig`/`GoLocateConfig` gain a read-only `receivers` mapping from a factory/constructor
expression to a type chain, fed by `[locate.receivers]`, a bundle `locate.receivers` and a
repeatable `--receiver KEY=VALUE`. The Rust scanner binds a receiver from `Client::new`/`default`, a
type annotation or a configured factory; the Go scanner from a pointer/simple annotation, a
composite literal or a configured factory. A method/selector chain on a bound receiver emits rooted
`CALL`/`ATTRIBUTE` hits with the stable `Type.member...` chain, so `client.charges().create(...)`
locates as `Client.charges.create` and `client.Charges.New(...)` as `Client.Charges.New`; an
untracked receiver keeps the old no-site/unrooted behavior. The shared `derive`/`resolve` policy is
unchanged. 2,338 tests, offline.

Known limits: a factory not in `receivers` and not annotated is not evidence; a local type named like
a mapped/rooted type is a documented false positive; rebinding clears; no return-type or
interprocedural inference. T12b covers C#, Python and TypeScript.

### T12b as built (2026-11-12)

`LocateConfig`/`TsLocateConfig`/`CSharpLocateConfig` gain the same read-only `receivers` mapping, and
`[locate.receivers]`, a bundle `locate.receivers` and `--receiver KEY=VALUE` now serve every
language. The C# scanner binds a receiver from `new`, an explicit declared type or a configured
factory and emits `client.Charges.Create(...)` as `StripeClient.Charges.Create`; Python from a rooted
constructor call (`client = stripe.Client(...)`), an annotation or a configured factory, emitting
`Client.charges.create`; TypeScript from `new`, an annotation or a configured factory, emitting
`StripeClient.charges.create`. The shared `derive`/`resolve` policy is unchanged; an untracked
receiver keeps the old no-site/unrooted behavior. 2,453 tests, offline. T12 is complete.

Known limits: a dynamic/Python reassignment is not branch-sensitive; a factory not in `receivers` and
not annotated/constructed is not evidence; computed access/`getattr`/`dynamic`, `using static`,
reflection and return-type/interprocedural inference are not followed (no site, not a guess); a local
type sharing a rooted/mapped name is a documented false positive. Operation inference from a URL no
longer matches a type-prefixed receiver chain; map the operation to the full chain.

### T13a as built (2026-11-12)

`Dockerfile` (multi-stage `uv` build, `--extra app`, git/CA, non-root `tenon` uid 10001, owned
`/data`, stdlib healthcheck), `docker-compose.yml` (the service plus Caddy, a named DB volume,
read-only bundles/secrets, tmpfs `/tmp`, read-only root, dropped caps, no service host port),
`Caddyfile` (automatic HTTPS via `TENON_DOMAIN`), `.env.example`, the bundle/secret layout and
`docs/technical/DEPLOYMENT.md` (secrets, key permissions, TLS/local CA, backups/restore, rotation,
upgrades, security checklist). `GET /ready` (with `RunStore.ping`) is the readiness signal; `/health`
stays liveness. 2,473 tests, offline (static artifact checks; no Docker daemon in pytest).

Known limits: the image/stack are not exercised by tests (the first operator run is the integration
test); the service is only safe behind Caddy TLS; host secrets/backups/permissions are the operator's
responsibility; one worker, no retries/cancel/metrics and no WAL until T13b.

### T10e as built (2026-11-11)

`src/tenon/service/`: a SQLite `RunStore` (queued/running/succeeded/failed, timestamps, exit, the
fan-out report JSON, errors, idempotency keys, and a deduplicated webhook-event log), a
`CommandRunner` that invokes the shipped installed fan-out as one CLI subprocess, one `Worker`
thread, a pure `Api.handle` with bearer auth, confined bundle names, `POST /runs`,
`GET /runs/{id}`, `GET /runs`, `GET /health` and a HMAC-verified `POST /webhooks/github`, and a
stdlib HTTP wrapper. `tenon provider serve --bundles DIR --db PATH --api-token TOKEN ...` starts the
worker and server; `--dry-run` omits `--open-pr`. 2,235 tests, offline.

Known limits: self-hosted and local-only; no TLS, rate limiting or a reverse proxy (the token and
webhook secret are the only guards); one sequential worker, no retries/cancel/parallelism; SQLite is
the store; a run can outlive the HTTP request; a hardened cloud deployment is a later card.




## Open questions

- Which vendor and SDK is the first real case? Pick one that publishes OpenAPI and has a public
  changelog of breaking changes.
- How to handle changes with no machine-readable source (changelog only)? Likely flag, not patch.
