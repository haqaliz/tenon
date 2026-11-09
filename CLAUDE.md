# Tenon: Project Context for Claude Code

This file orients a coding agent working in this repository. Read it first. Deeper context
lives in the `docs/` folder.

---

## What this project is

**Tenon** keeps your code fitted to the APIs it depends on. When a vendor ships a breaking
change (a renamed field, a removed endpoint, a new required parameter), Tenon finds the affected
calls in your repository, proposes the fix as a pull request, and **proves the fix against your
own checks** before it asks you to merge. A second mode checks whether an API or MCP server is
usable by AI agents, by running an agent against it.

The name: a *tenon* is the tongue cut on a timber to fit its mortise exactly. The joint holds
only if the two sides still match. Tenon asks of an integration: *does your side still fit theirs?*

Status: **T1, T2, T3, T4, T5, T6, T7, T8a, T8b, T8c, T9, T10a, T10b, T10c, T10d and M1.4 shipped.**
`src/tenon/detect/` turns two OpenAPI 3.x documents — and, for T8a, two MCP `tools/list` documents —
into typed `Change` records; `src/tenon/locate/` turns a record into call sites with file, line and
column, keeping anything unprovable in named ambiguity groups — Python via `ast`,
TypeScript/JavaScript via tree-sitter, and MCP `call_tool` sites via `locate_mcp`, no Node analysis
runtime; `src/tenon/propose/` turns certain sites into a candidate diff and never applies it;
`src/tenon/prove/` applies that diff to a copy, runs every configured proof stage before and after,
and records the strongest level that actually passed (`TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`,
`TYPES_BUILD_ONLY`) or `UNVERIFIED` with a stage-specific cause; `src/tenon/pr/` renders a
deterministic PR whose title and body state that level, then clones a clean checkout, commits the
exact diff to a new branch and opens the PR through the user's own `git` and `gh` or a GitHub App
installation (`--remote app`); `src/tenon/cli/` exposes `tenon check`, `tenon fix`,
`tenon provider migrate`, `tenon probe` and `tenon corpus` with `--language python|ts`,
`--source openapi|mcp`, `--build`/`--characterize`/`--replay`/`--check`, the five-level `--require`,
text or byte-stable JSON, honest exit codes, `tenon.toml` config, and `fix --open-pr` delegating to
T5 with the required level and a draft gate; `src/tenon/provider/` loads a portable migration bundle
and runs the same pipeline for one target repo; `src/tenon/probe/` connects to an MCP server over
stdio, runs probe tasks through a user-supplied agent and reports what worked, with no model or
network; `src/tenon/corpus/` records `(change, patch, proof, outcome)` runs and reports by
level/outcome, with a merge rate only where real outcomes exist (`docs/benchmark/`). `fix` never
writes the checkout; the PR writer refuses a dirty tree, the default branch, an existing branch, a
failed remote check, and a proof below the required level unless the user opts into a draft; it has
no merge path. Tests live in `tests/`. The Phase 0 gate (M0.3) is met on two real cases:
`fighthealthinsurance/fighthealthinsurance` @ `56e69cf` (three certain sites, a three-edit diff,
`TESTS_PASSED` on the focused checkout test) and `yezz123/stripe-template` @ `9d9178c` (a
mock-assertion site, `TESTS_PASSED` on the offline subset; the case that forced T2's mock-assertion
keyword attribution). Phase 2 is complete; Phase 3's T10a (GitHub App remote), T10b (provider
migration bundle), T10c (local provider fan-out) and T10d (installed provider fan-out) shipped,
while the hosted/webhook-driven service and T11 are not started — do not describe capability that
isn't there yet.

Lineage: one of three siblings scaffolded together on 2026-10-22 (with Assay and Pry) from a
market-demand pass (`~/dev/at/ideas/market-demand-2026-10.md`). It answers the YC Fall 2026
request "Self-Maintaining APIs". Standalone: no code dependency on Belay or Plumb, though the
"model proposes, execution decides" discipline is shared.

---

## The wedge (read this before proposing any feature)

- **Letting an LLM rewrite code against a changelog and opening the PR.** Easy to build, crowded
  (Dependabot-style bots, coding agents), and unsafe: the PR looks plausible and may be wrong.
  **We do NOT build this as the product.**
- **Proving the change.** Detect the change from a machine-readable source, locate the affected
  usages, apply a candidate fix, and show it passes a check the user trusts. **This IS the
  product.** A fix with no proof is a flagged suggestion, never a confident PR.

---

## Key strategic constraints (do not violate)

1. **Execution decides, never the model.** A model may *propose* a patch. Only running the
   user's checks (tests, build, type-check, recorded-call replay) decides whether the PR is
   labelled verified.
2. **Honest proof levels.** Every PR carries the strongest proof that actually ran:
   `TESTS_PASSED`, `CHARACTERIZED` (generated characterization tests held), `TYPES_BUILD_ONLY`,
   `REPLAYED`, or `UNVERIFIED`. The user chooses which levels they require. `UNVERIFIED` is never
   presented as verified. Weak proof is labelled weak.
3. **Machine-readable change sources first.** OpenAPI diffs, SDK release metadata and typed
   signatures are trusted. A changelog paragraph is a hint, not a source of truth.
4. **No code egress by default.** Repository code is analyzed locally. Any model assist is BYOK or
   local, opt-in, and disclosed. Never send a customer's code to a service the user did not
   authorize.
5. **Never touch the default branch.** Tenon opens a branch and a PR. It never pushes to `master`
   and never merges.
6. **Build the part that improves as models improve.** A better model proposes better patches; the
   proof step stays the arbiter.
7. **Test-first.** Every capability lands with its failing test written first.

---

## Proof contract

| Level | Meaning | When it may be used |
|---|---|---|
| **TESTS_PASSED** | The repo's own tests pass after the patch (and failed or were affected before) | Tests exist and exercise the changed call sites |
| **CHARACTERIZED** | Your characterization command passes before and after | You supplied the command and opted in; Tenon does not generate it |
| **REPLAYED** | Your recorded-call replay passes before and after | You supplied the recording |
| **TYPES_BUILD_ONLY** | Type-check and build pass, nothing more | No tests; labelled as weak |
| **UNVERIFIED** | No acceptable proof ran | Default when nothing the user required could run |

All configured stages run. Any red stage is `UNVERIFIED` with a stage-specific cause; the strongest
green stage is the level. The current characterization and replay commands are user-supplied.
The PR title and body state the level. A required level the run could not reach means no
"verified" PR, only a flagged one.

---

## Tech direction

- **Python core** (via `uv`), CLI-first (`tenon`), self-hostable OSS; a GitHub App and hosted
  layer come later. Details in `docs/technical/ARCHITECTURE.md`. A TypeScript component may be
  needed for TS/JS analysis; decide when that capability is planned, not before.
- Language targets in order: Python, TypeScript/JavaScript, then Go, Rust, C# as demand shows.
- Change sources: OpenAPI diffs first; MCP server schema diffs; SDK release metadata.
- Two users: **consumer first** (keep my integrations current), **provider later** (let me push
  migrations to my customers).

---

## Founder profile

Solo / small team. Full-stack developer + ML engineer. The moat is engineering (detection plus
proof), not vendor relationships.

---

## Folder / docs structure

```
README.md
VISION.md
CLAUDE.md                          # This file
LICENSE                            # Apache-2.0
docs/
  ROADMAP.md                       # Phases + risk register
  technical/CAPABILITY_ROADMAP.md  # T1..T11 capabilities in build order
  technical/ARCHITECTURE.md        # detect -> locate -> patch -> prove -> PR
  planning/{slug}/                 # In-flight PRDs, specs, plans
```

---

## Quick facts for grounding (do not fabricate beyond these)

- YC Fall 2026 "Self-Maintaining APIs" (Harsha Gaddipati, Slashy): at AWS, "over 30%" of service
  downtime came from unnoticed external API or package changes (YC's claim).
- A study of 251 API versions with breaking changes found 87.3% gave no deprecation information in
  the previous version; 81-97% of breaking changes were refactorings (renames, moved methods,
  changed signatures).
- The official MCP registry listed 43,298 servers on 2026-10-14 (+36% in 30 days); one crawler
  found only 12,579 of 204,020 indexed endpoints responding.
- MuleSoft 2026 (1,050 IT leaders): 36% of time goes to building and testing integrations.
- No rigorous survey was found measuring time lost specifically to deprecations. Do not claim one.

If you need a statistic that isn't here, say it's unverified.
