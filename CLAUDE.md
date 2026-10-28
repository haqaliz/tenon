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

Status: **T1 and T2 shipped.** `src/tenon/detect/` turns two OpenAPI 3.x documents into typed
`Change` records; `src/tenon/locate/` turns a record into call sites with file, line and column,
keeping anything unprovable in named ambiguity groups. Tests live in `tests/`. T3 (propose) is next.
Nothing else in the pipeline exists — do not describe capability that isn't there yet.

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
| **CHARACTERIZED** | Generated tests of current behavior pass before and after | The user opted in to characterization tests |
| **REPLAYED** | Recorded real calls replay against the new API shape | The user supplied or recorded traffic |
| **TYPES_BUILD_ONLY** | Type-check and build pass, nothing more | No tests; labelled as weak |
| **UNVERIFIED** | No acceptable proof ran | Default when nothing the user required could run |

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
