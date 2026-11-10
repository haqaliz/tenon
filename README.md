# Tenon

**Keeps your code fitted to the APIs it depends on.** Detects breaking API changes, patches the
affected calls, and proves the fix against your own checks before it opens a pull request.

[![Status](https://img.shields.io/badge/status-T1%20%2B%20T2%20%2B%20T3%20%2B%20T4%20%2B%20T5%20%2B%20T6%20%2B%20T7%20%2B%20MCP%20%2B%20probe%20%2B%20benchmark%20%2B%20GitHub%20App%20%2B%20provider%20%2B%20fan-out%20%2B%20installed%20fan-out%20%2B%20Rust%20%2B%20CLI%20shipped-yellow)](docs/ROADMAP.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[Vision](VISION.md) · [Roadmap](docs/ROADMAP.md) · [Architecture](docs/technical/ARCHITECTURE.md) · [Capabilities](docs/technical/CAPABILITY_ROADMAP.md)

---

## Status

**T1 (change detection), T2 (Python call-site location), T3 (patch proposal), T4 (proof runner),
T5 (PR writer), T6 (TypeScript/JavaScript call-site location), T7 (proof ladder), T8 (MCP
tool-schema diffs, Python tool-call location and `tenon probe`), T9 (benchmark corpus), T10a (GitHub
App remote), T10b (provider migration bundle), T10c (local provider fan-out), T10d (installed
provider fan-out), T11a (Rust call-site location) and the `tenon check` / `tenon fix` /
`tenon provider migrate` / `tenon probe` / `tenon corpus` CLI are shipped.**
`src/tenon/detect/` diffs two OpenAPI 3.x documents — and two MCP `tools/list` documents — into typed
`Change` records; `src/tenon/locate/` turns one of those records into call sites with file, line and
column, and keeps anything it cannot prove in a separate ambiguity list — Python via `ast`,
TypeScript/JavaScript and Rust via tree-sitter, and MCP `call_tool` sites via `locate_mcp`; no Node
or Rust analysis runtime; `src/tenon/propose/` turns the certain sites into a candidate diff and
never applies it;
`src/tenon/prove/` applies that diff to a copy and runs every configured proof stage before and
after, recording the strongest level that actually passed (`TESTS_PASSED`, `CHARACTERIZED`,
`REPLAYED`, `TYPES_BUILD_ONLY`) or `UNVERIFIED` with a reason; `src/tenon/pr/` renders a
deterministic PR whose title and body state that level, then clones a clean checkout, commits the
exact diff to a new branch and opens the PR through your own `git` and `gh` or a GitHub App
installation (`--remote app`); `src/tenon/provider/` loads a portable migration bundle and
`src/tenon/cli/` runs it through the same pipeline; `src/tenon/probe/` connects to an MCP server
over stdio, runs tasks through a user-supplied agent and reports what worked; `src/tenon/corpus/`
records `(change, patch, proof, outcome)` runs and reports by level/outcome. The analysis and proof
run fully offline; only the final push and PR call touch a remote. Read `CLAUDE.md` before writing
any code here.

## CLI

```sh
uv run tenon check path/to/repo --old v1.yaml --new v2.yaml
uv run tenon check path/to/ts-repo --old v1.yaml --new v2.yaml --language ts
uv run tenon check path/to/rust-repo --old v1.yaml --new v2.yaml --language rust
uv run tenon fix path/to/repo --old v1.yaml --new v2.yaml \
    --check "python -m pytest -q"
uv run tenon fix path/to/no-test-repo --old v1.yaml --new v2.yaml \
    --build "python -m compileall -q ." --require TYPES_BUILD_ONLY
uv run tenon check path/to/mcp-repo --source mcp \
    --old tools-v1.json --new tools-v2.json
uv run tenon provider migrate path/to/customer-repo \
    --bundle stripe-v2500-v2596.json --open-pr --remote app
uv run tenon provider migrate --repos repos.txt \
    --bundle stripe-v2500-v2596.json --open-pr --remote app
uv run tenon provider migrate --installed \
    --bundle stripe-v2500-v2596.json --open-pr --remote app
uv run tenon probe \
    --server-cmd "python server.py" --tasks tasks.json --agent "python agent.py"
uv run tenon corpus report --corpus docs/benchmark/corpus.jsonl
```

`check` exits 0 when no affected site exists and 1 when one does; `fix` prints the diff and the proof,
and `--open-pr` opens a PR whose title states the level. `--require` chooses the level a run must
reach; `--build`/`--characterize`/`--replay` add the weaker stages; `--source mcp` selects the MCP
loader/differ/locator. `provider migrate` runs the same pipeline from a portable JSON bundle and
prints a provider report; `--repos FILE` runs it once per listed checkout, and `--installed`
discovers and runs it over the app installation's non-archived repositories. `probe` starts a local MCP
server over stdio, runs the task file through your agent command and reports what worked (exit 0 all
tasks, 1 a failed task, 2 usage/connection).
`corpus` records a `fix --json` run, updates a human outcome and reports by level/outcome. `--json`
is byte-stable. Repeated inputs can live in `tenon.toml` under `[locate]` (`source`, `language`,
`sdk_package`, mappings) and `[tenon]`; probe/corpus use flags only. `language` is `python`, `ts` or
`rust`; `source = "mcp"` remains Python-only.

`--language rust` scans `.rs` files with tree-sitter and needs no Rust toolchain. In `tenon.toml`,
`[locate] sdk_package` is the crate name as written in `use` (for example `stripe`), and the shared
`[locate.operations]`/`[locate.fields]` tables map the spec to Rust chains, e.g.
`"POST /v1/charges" = "Charge.create"` and `"Charge.amount" = "amount_cents"`. Supported shapes are
associated calls (`Charge::create(&params)`), struct literals (`CreateCharge { amount_cents: amount }`),
field access through a tracked binding (`params.amount_cents`), and `use` aliases
(`use stripe::Charge as StripeCharge`). Limits: method chains (`client.charges().create(...)`), macros,
re-exported crates, and multi-hop struct data flow are not followed; they report no site rather than
a guessed one. A `fields` mapping that changes the spelling locates the site, but `fix` proposes a
rename only when the located spelling equals the spec's old name (the shipped proposer rule);
otherwise it reports `NO_EDITABLE_SITES` and the customer renames manually.

```python
from tenon.detect import diff, load
from tenon.locate import LocateConfig, locate
from tenon.pr import GitGhRemote, write_pr
from tenon.propose import propose
from tenon.prove import prove

changes = diff(load("v1.yaml"), load("v2.yaml")).changes
for change in changes:
    located = locate(change, "path/to/repo", LocateConfig(sdk_package="stripe"))
    proposal = propose(change, located, "path/to/repo")
    result = prove(proposal, "path/to/repo", ["python", "-m", "pytest", "-q"])
    result.level      # TESTS_PASSED, or UNVERIFIED with a cause
    proposal.skipped  # what Tenon refused to touch, and why
    pr = write_pr(proposal, result, "path/to/repo", remote=GitGhRemote())
    pr.url            # the PR, when OPENED
    pr.refusal        # DIRTY_CHECKOUT, DEFAULT_BRANCH, ... when REFUSED
```

### GitHub App remote

`tenon fix ... --open-pr --remote app` opens the PR as a GitHub App instead of through `gh`. The app
needs `contents:write` and `pull_requests:write` permissions and must be installed on the repository.
The inputs are flags or environment variables; a flag wins:

| Flag | Environment |
|---|---|
| `--app-id` | `TENON_GITHUB_APP_ID` |
| `--app-installation-id` | `TENON_GITHUB_APP_INSTALLATION_ID` |
| `--app-private-key PATH` | `TENON_GITHUB_APP_PRIVATE_KEY` (a path) |
| `--api-url URL` | `TENON_GITHUB_API_URL` |

The private key is read from a path; key content is never read from the environment. `--remote`
requires `--open-pr`, and `--remote gh` (the default) keeps the existing `gh` path. The app remote is
self-hosted: webhooks and a hosted service are deferred, while `--installed` uses the same app
identity for discovery and cloning. `--api-url` also targets a self-hosted GitHub Enterprise endpoint.

### Provider migration bundle

A provider can package one migration as a JSON bundle and run it against one local checkout, a list
of checkouts or the app installation with
`tenon provider migrate [<repo>|--repos FILE|--installed] --bundle PATH`. The bundle names the
provider and migration, the source and language (`python`, `ts` or `rust`), the two spec files
(resolved relative to the bundle), the locate config, the required proof level and the optional stage
commands:

```json
{
  "provider": "stripe",
  "migration": "v2500-v2596-payment-method-types",
  "source": "openapi",
  "language": "python",
  "old": "v2500.yaml",
  "new": "v2596.yaml",
  "locate": {
    "sdk_package": "stripe",
    "operations": {"POST /v1/checkout/sessions": "checkout.Session.create"},
    "fields": {"amount": "amount_total"}
  },
  "require": "TESTS_PASSED",
  "check": ["python", "-m", "pytest", "-q", "tests/test_checkout.py"],
  "build": [],
  "characterize": [],
  "replay": [],
  "breaking_only": false
}
```

`tenon provider migrate <repo> --bundle PATH [--open-pr] [--remote gh|app] [--app-id ID]
[--app-installation-id ID] [--app-private-key PATH] [--api-url URL] [--check CMD]
[--require LEVEL] [--allow-below-required] [--allow-unverified] [--json]` builds the same
`CliConfig` as `fix`, applies `--check`/`--require` over the bundle and runs the same detect →
locate → propose → prove pipeline. The text report is a `provider`/`migration` header followed by
the fix report; `--json` wraps the fix results and summary in a provider envelope (`command`,
`provider`, `migration`, `repo`, `results`, `summary`). The exit code is `fix_exit`, and `--open-pr`
uses the same T5 guardrails and gh/app remote. A bundle never upgrades the proof level: `require`
is the bar and `fix_exit` decides whether it was met.

`<repo>`, `--repos FILE` and `--installed` are mutually exclusive and exactly one is required. The
repos file is UTF-8 text with one local path per line; blank lines and lines whose stripped form
starts with `#` are ignored, `~` is expanded and relative paths resolve against the file's parent. A
missing or unreadable file, a non-file, or an empty list exits 2.

`tenon provider migrate --repos FILE --bundle PATH` runs the bundle once per listed checkout. The
bundle and its `CliConfig` are loaded once, so `--check`/`--require` apply to every repo; when
`--open-pr` is set the selected gh/app remote is constructed once and reused for one PR per repo.
Repos run sequentially in file order. A listed path that is not a directory is a per-repo
`error: not a directory` and the remaining repos still run. The text report is the
`provider`/`migration` header, one `repo:` block per repo (the fix report, or `error: ...`) and a
`repos: N, passed: X, failed: Y` summary; `--json` is a fan-out envelope (`command`, `provider`,
`migration`, `repos: [{repo, results, summary, exit, error}]`, `summary`). The exit code is 0 only
when every repo meets the requirement and every requested PR opened, 1 when any repo failed, and 2
on usage/bundle/repos-file/global spec/config errors (a shared spec refusal aborts the whole run).

`tenon provider migrate --installed --bundle PATH` discovers the app installation's non-archived
repositories through `GET /installation/repositories` (paginated, API order) and runs the bundle
over them. It uses the app identity above from flags or `TENON_GITHUB_APP_*`/`TENON_GITHUB_API_URL`;
missing inputs or an unreadable key exit 2. `--remote gh` is rejected (`--installed requires
--remote app`), and `--remote` is otherwise only meaningful with `--open-pr`. The installation token
is minted once and shared by discovery, every clone and, under `--open-pr`, one `GitHubAppRemote`
built from that same token; without `--open-pr` the run is a dry run with no PR call. Each repo is
cloned with the app credential helper into a temp checkout (the token is in the git child's
environment, never argv or the URL) and the temp dir is removed even when the clone fails; the
pipeline runs in that checkout, so no local path is written. A repo whose clone fails is a per-repo
`error: ...` and the remaining repos still run; a token or discovery failure aborts with exit 2. The
report, summary and exits are the `--repos` fan-out's, with `repo` = `owner/name`.

The fan-out has no rollback: earlier repos may already have branches or PRs when a later repo fails,
and the report names every repo. It is sequential and mints one app token per run; parallelism,
retries, repo filtering, webhooks/a hosted service and a provider note in the PR body are deferred.
The bundle and repos file are trusted operator input, not a sandbox: their stage commands run as
given.

`uv run pytest` — no network, no model calls.

MCP `tools/list` documents use the same records:

```python
from tenon.detect import diff_mcp, load_mcp
from tenon.locate import McpLocateConfig, locate_mcp

changes = diff_mcp(
    load_mcp("tools-v1.json"),
    load_mcp("tools-v2.json"),
).changes
changes[0].kind     # endpoint_removed, property_required_added, enum_narrowed, ...
changes[0].location # method="tool", path=<tool name>, pointer="#/tools/<tool>/..."
site = locate_mcp(changes[0], "path/to/repo", McpLocateConfig(client_package="mcp"))
site.certain        # call_tool("name", {"amount": ...}) keys, rooted in ClientSession
```

`tenon check --source mcp` and `tenon fix --source mcp` use the same MCP diff and locator. The
Python locator covers the high-level `ClientSession.call_tool` pattern; TypeScript and low-level
`send_request` calls are follow-ups.

## Benchmark

`docs/benchmark/corpus.jsonl` records `(change, patch, proof, outcome)` runs. The two public M0.3
cases are `local_only`/`TESTS_PASSED`; no merge outcome exists yet, so the report shows no merge
rate.

```sh
uv run tenon corpus report --corpus docs/benchmark/corpus.jsonl
```

A run enters with `tenon corpus record --from fix.json ...`; a human outcome is added with
`tenon corpus outcome <id> merged --outcome-url <pr>`. The corpus is local and opt-in; nothing is
uploaded.

## What Tenon is

Two modes sharing one run-and-verify core:

- **Upgrade (lead):** a vendor changes an API. Tenon reads the change from a machine-readable
  source (OpenAPI diff first), finds the affected calls in your repo, proposes a patch, and runs
  your checks. The PR says which proof level it reached.
- **Probe (second):** point Tenon at an MCP server (`tenon probe`), run tasks through your own agent
  command, and see which tools an agent could actually use. No model ships; the report is an
  observation, not a proof level.

## Proof levels

| Level | Meaning |
|---|---|
| `TESTS_PASSED` | Your tests pass after the patch |
| `CHARACTERIZED` | Your characterization command passes before and after (Tenon does not generate it) |
| `REPLAYED` | Your recorded-call replay passes before and after (you supply the recording) |
| `TYPES_BUILD_ONLY` | Your build/type-check passes before and after, nothing more (weak, labelled) |
| `UNVERIFIED` | No acceptable proof ran |

You choose the level you require. A model may propose the patch; running the checks decides the label.
Every configured stage runs; any red stage is `UNVERIFIED`, and the strongest green stage is the
label.

## Scope

Languages: Python, TypeScript/JavaScript and Rust shipped; Go and C# follow. Change sources: OpenAPI
and MCP tools/list diffs, with the Python MCP tool-call locator; SDK metadata later. Consumer side
first; the provider bundle (T10b) packages that run for one repo, local fan-out over a repos file
(T10c) and installed fan-out through the app (T10d) run it across checkouts; a hosted/webhook-driven
service is later.

## Docs

- [`VISION.md`](VISION.md)
- [`CLAUDE.md`](CLAUDE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md)
- [`docs/technical/ARCHITECTURE.md`](docs/technical/ARCHITECTURE.md)

## Lineage

One of three siblings scaffolded on 2026-10-22 with [Assay](../assay) and [Pry](../pry), sharing
house DNA with [Belay](../belay) and [Plumb](../plumb). Standalone by design.
