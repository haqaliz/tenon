# Tenon: Vision

> A dependency you do not maintain is a promise someone else can break.

---

## The bet in one sentence

Updating code when an API changes is a solved *typing* problem and an unsolved *trust* problem.
Any model can draft the patch; nobody trusts it. Tenon wins by being the system that **detects
the change from machine-readable sources, patches the affected calls, and proves the result
against checks you trust** before asking you to merge.

---

## Why now

- **Agents multiply integrations.** Software increasingly calls many APIs and MCP servers; each is
  a place to break. The official MCP registry grew 36% in 30 days to 43,298 servers.
- **Breakage is silent.** 87.3% of breaking API versions in one study gave no deprecation notice
  in the previous version. Most breaks are refactorings, which are mechanical to find.
- **YC asked for it.** Fall 2026 lists "Self-Maintaining APIs", with a claim that over 30% of
  downtime at AWS came from unnoticed external changes. That is direction, not proof of demand.
- **Drafting code is cheap; trusting it is not.** Plausible-looking PRs are everywhere. A PR with
  a stated proof level is rare.

---

## The founder's unfair advantage

Detection plus proof is an execution problem: diff schemas, locate call sites, run checks, and
report honestly. It is the same discipline as Plumb and Belay: a model may propose, execution
decides. No vendor partnership or proprietary dataset is required to start.

---

## Why it's defensible ("gets better as models improve")

The durable core is the change detector, the call-site locator, the proof runner and the labelled
history of (change, patch, proof, outcome). A stronger model writes better patches and fewer
rejected PRs, which makes the proof step pass more often. The proof step stays the arbiter, so a
better model never makes it redundant.

---

## Positioning

- **Not a dependency bumper.** Dependabot updates versions; Tenon repairs the code that a version
  or an API change breaks.
- **Not a coding agent with a PR button.** The PR states the proof level it actually reached.
- **Honest labels:** `TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`, `UNVERIFIED`.

---

## The wedge to the company

1. **OSS on-ramp:** `tenon check` finds affected call sites for a given API change; `tenon fix`
   opens a PR with a proof level. Python first, OpenAPI as the change source.
2. **Readiness mode:** `tenon probe` runs an agent against an API or MCP server and reports what
   works. Reuses the run-and-verify core and doubles as a lead generator for providers.
3. **Provider layer (hosted):** vendors push verified migration PRs to their customers. This is
   where vendors may pay. It needs the consumer side to exist first.

---

## Non-goals

- Merging anything. Tenon proposes; humans merge.
- Rewriting code from a changelog alone with no machine-readable source and no proof.
- Sending customer code to a model the user did not authorize.
- A general-purpose coding agent.

---

## The one-line mantra

**Find what broke. Fix it. Prove the fix before asking for the merge.**
