# Tenon

**Keeps your code fitted to the APIs it depends on.** Detects breaking API changes, patches the
affected calls, and proves the fix against your own checks before it opens a pull request.

[![Status](https://img.shields.io/badge/status-T1%20%2B%20T2%20%2B%20T3%20%2B%20T4%20%2B%20T5%20%2B%20T6%20%2B%20T7%20%2B%20MCP%20%2B%20probe%20%2B%20CLI%20shipped-yellow)](docs/ROADMAP.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[Vision](VISION.md) · [Roadmap](docs/ROADMAP.md) · [Architecture](docs/technical/ARCHITECTURE.md) · [Capabilities](docs/technical/CAPABILITY_ROADMAP.md)

---

## Status

**T1 (change detection), T2 (Python call-site location), T3 (patch proposal), T4 (proof runner),
T5 (PR writer), T6 (TypeScript/JavaScript call-site location), T7 (proof ladder), T8 (MCP
tool-schema diffs, Python tool-call location and `tenon probe`) and the `tenon check` / `tenon fix` /
`tenon probe` CLI are shipped.** `src/tenon/detect/` diffs two OpenAPI 3.x documents — and two MCP
`tools/list` documents — into typed `Change` records; `src/tenon/locate/` turns one of those records
into call sites with file, line and column, and keeps anything it cannot prove in a separate
ambiguity list — Python via `ast`, TypeScript/JavaScript via tree-sitter, and MCP `call_tool` sites
via `locate_mcp`; no Node analysis runtime; `src/tenon/propose/` turns the certain sites into a
candidate diff and never applies it; `src/tenon/prove/` applies that diff to a copy and runs every
configured proof stage before and after, recording the strongest level that actually passed
(`TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`) or `UNVERIFIED` with a reason;
`src/tenon/pr/` renders a deterministic PR whose title and body state that level, then clones a clean
checkout, commits the exact diff to a new branch and opens the PR through your own `git` and `gh`;
`src/tenon/probe/` connects to an MCP server over stdio, runs tasks through a user-supplied agent and
reports what worked; `src/tenon/cli/` exposes the whole pipeline. The analysis and proof run fully
offline; only the final push and PR call touch a remote. Read `CLAUDE.md` before writing any code
here.

## CLI

```sh
uv run tenon check path/to/repo --old v1.yaml --new v2.yaml
uv run tenon check path/to/ts-repo --old v1.yaml --new v2.yaml --language ts
uv run tenon fix path/to/repo --old v1.yaml --new v2.yaml \
    --check "python -m pytest -q"
uv run tenon fix path/to/no-test-repo --old v1.yaml --new v2.yaml \
    --build "python -m compileall -q ." --require TYPES_BUILD_ONLY
uv run tenon check path/to/mcp-repo --source mcp \
    --old tools-v1.json --new tools-v2.json
uv run tenon probe \
    --server-cmd "python server.py" --tasks tasks.json --agent "python agent.py"
```

`check` exits 0 when no affected site exists and 1 when one does; `fix` prints the diff and the proof,
and `--open-pr` opens a PR whose title states the level. `--require` chooses the level a run must
reach; `--build`/`--characterize`/`--replay` add the weaker stages; `--source mcp` selects the MCP
loader/differ/locator. `probe` starts a local MCP server over stdio, runs the task file through your
agent command and reports what worked (exit 0 all tasks, 1 a failed task, 2 usage/connection).
`--json` is byte-stable. Repeated inputs can live in `tenon.toml` under `[locate]` (`source`,
`language`, `sdk_package`, mappings) and `[tenon]`; probe uses flags only.

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

Languages in order: Python, TypeScript/JavaScript, then Go, Rust, C#. Change sources: OpenAPI and MCP
tools/list diffs, with the Python MCP tool-call locator; SDK metadata later. Consumer side first,
provider side later.

## Docs

- [`VISION.md`](VISION.md)
- [`CLAUDE.md`](CLAUDE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md)
- [`docs/technical/ARCHITECTURE.md`](docs/technical/ARCHITECTURE.md)

## Lineage

One of three siblings scaffolded on 2026-10-22 with [Assay](../assay) and [Pry](../pry), sharing
house DNA with [Belay](../belay) and [Plumb](../plumb). Standalone by design.
