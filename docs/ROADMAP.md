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
| M0.2 | Python call-site locator (T2) | Given a change, finds usages in a Python repo with file and line; ambiguity is reported, never guessed | **Built 2026-10-28** (`src/tenon/locate/`, 207 tests) |
| M0.3 | One end-to-end case | A real public SDK change applied to a real repo, with the repo's tests as proof | Not started |

## Phase 1: OSS core (weeks 4-8)

| # | Milestone | Done when |
|---|---|---|
| M1.1 | Patch proposer seam (T3) | Pluggable proposer (rule-based first, BYOK model optional); output is a diff, never applied unverified |
| M1.2 | Proof runner (T4) | Runs tests in an isolated working copy; records `TESTS_PASSED` or `UNVERIFIED` with a cause |
| M1.3 | PR writer (T5) | Opens a branch and PR stating the proof level; never touches `master` |
| M1.4 | `tenon check` / `tenon fix` CLI | Exit codes reflect proof; JSON output byte-stable |

## Phase 2: Breadth and proof depth (weeks 8-12)

| # | Milestone | Done when |
|---|---|---|
| M2.1 | TypeScript/JavaScript locator (T6) | Same contract as the Python locator |
| M2.2 | Weaker and stronger proofs (T7) | Types/build-only, characterization tests, recorded-call replay, each labelled |
| M2.3 | MCP schema diffs and `tenon probe` (T8) | Agent run against an MCP server or API; reports what worked |
| M2.4 | Benchmark of (change, patch, proof, outcome) | Public set of real changes with how often each proof level held |

## Phase 3: Provider layer (after the window)

GitHub App, provider-facing migration PRs, hosted. Go, Rust and C# locators on demand.

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
