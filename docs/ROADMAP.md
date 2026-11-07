# Tenon: Roadmap

Goal: **reputation and moat** in about 3 months, in parallel with Assay and Pry, so each project
moves at a fraction of full speed. Form: OSS CLI first, GitHub App and hosted later. Stack:
Python via `uv` first; TypeScript analysis decided when planned.

Milestone order is my proposal; reorder freely.

---

## Phase 0: Prove the wedge (weeks 1-3)

**Gate: one real API change, one real repo, one patch that passes a real check.**

| # | Milestone | Done when | State |
|---|---|---|---|
| M0.1 | OpenAPI differ (T1) | Two spec versions diff into typed change records (removed, renamed, required-added, type-changed); unparseable input is a named refusal | **Shipped 2026-10-26** (`src/tenon/detect/`, 136 tests) |
| M0.2 | Python call-site locator (T2) | Given a change, finds usages in a Python repo with file and line; ambiguity is reported, never guessed | **Shipped 2026-10-29** (`src/tenon/locate/`, 207 tests) |
| M0.3 | One end-to-end case | A real public SDK change applied to a real repo, with the repo's tests as proof | **Shipped 2026-11-05:** two real cases: `fighthealthinsurance/fighthealthinsurance` @ `56e69cf` (3 certain sites, 3-edit diff, `TESTS_PASSED` on `tests/sync/test_pwyw_checkout.py`) and `yezz123/stripe-template` @ `9d9178c` (mock-assertion site, `TESTS_PASSED` on the offline subset); see `docs/planning/m0-3-first-real-case/evidence.md` and `docs/planning/m0-3-real-case/evidence.md` |

## Phase 1: OSS core (weeks 4-8)

| # | Milestone | Done when | State |
|---|---|---|---|
| M1.1 | Patch proposer seam (T3) | Pluggable proposer (rule-based first, BYOK model optional); output is a diff, never applied unverified | **Shipped 2026-10-29** (`src/tenon/propose/`, 114 tests) |
| M1.2 | Proof runner (T4) | Runs tests in an isolated working copy; records `TESTS_PASSED` or `UNVERIFIED` with a cause | **Shipped 2026-10-29** (`src/tenon/prove/`, 105 tests) |
| M1.3 | PR writer (T5) | Opens a branch and PR stating the proof level; never touches `master` | **Shipped 2026-11-05** (`src/tenon/pr/`, 745 tests; local bare-remote end-to-end, no live GitHub call) |
| M1.4 | `tenon check` / `tenon fix` CLI | Exit codes reflect proof; JSON output byte-stable | **Shipped 2026-11-05** (`src/tenon/cli/`, 870 tests; text + byte-stable JSON) |

## Phase 2: Breadth and proof depth (weeks 8-12)

| # | Milestone | Done when | State |
|---|---|---|---|
| M2.1 | TypeScript/JavaScript locator (T6) | Same contract as the Python locator | **Shipped 2026-11-05** (`src/tenon/locate/ts_*.py`, 1,006 tests) |
| M2.2 | Weaker and stronger proofs (T7) | Types/build-only, characterization tests, recorded-call replay, each labelled | **Shipped 2026-11-06** (`src/tenon/prove/`, CLI/PR integration, 1,178 tests) |
| M2.3 | MCP schema diffs and `tenon probe` (T8) | Agent run against an MCP server or API; reports what worked | **Shipped 2026-11-07** (MCP tool-schema diffs + tool-call locator + `tenon probe`, `src/tenon/detect/mcp_*.py`, `src/tenon/locate/mcp_*.py`, `src/tenon/probe/`, 1,436 tests) |
| M2.4 | Benchmark of (change, patch, proof, outcome) | Public set of real changes with how often each proof level held | **Shipped 2026-11-07** (`src/tenon/corpus/`, `docs/benchmark/corpus.jsonl`, 1,571 tests; two public local-only seeds, no merge rate yet) |

## Phase 3: Provider layer (after the window)

GitHub App, provider-facing migration PRs, hosted. Go, Rust and C# locators on demand.

**T10a (GitHub App remote) and T10b (provider migration bundle) shipped 2026-11-08**
(`src/tenon/pr/{app,api,github_app}.py`, `src/tenon/provider/`, CLI; 1,738 tests). T10c (hosted
service/fan-out) and T11 are not started.

---

## Risk register

| ID | Risk | L/I | Mitigation |
|---|---|---|---|
| R1 | Many repos lack tests, so proof is weak | High/High | Proof levels are explicit; `UNVERIFIED` is a first-class output; offer characterization tests |
| R2 | A verified PR still breaks production | Med/High | Say what was proven, no more; never auto-merge |
| R3 | Machine-readable changes are rare for many vendors | High/Med | Start with vendors that publish OpenAPI; changelog text is a hint only |
| R4 | Call-site location is wrong in dynamic code | Med/Med | Report ambiguity; refuse to guess |
| R5 | Coding agents and bots crowd the space | High/Med | Differentiate on the stated proof level and benchmark |
| R6 | Customer code egress concerns | Med/High | Local analysis; BYOK or local models; opt-in |
| R7 | Vendors will not pay until the consumer side has users | High/Med | Consumer first; probe mode as the vendor-facing hook |
| R8 | Language sprawl | High/Med | Python first; each language behind its own fixtures |
