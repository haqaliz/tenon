# PRD: First real case (M0.3)

- **Slug:** `stripe-real-case`
- **Milestone:** M0.3 in `docs/ROADMAP.md` — the Phase 0 gate
- **Capabilities exercised:** T1-T4 (shipped)
- **Status:** evidence complete; **gate not met**; decision required on the follow-on
- **Card:** `docs/planning/_card/issue.md`
- **Evidence:** `docs/planning/stripe-real-case/evidence.md`

## Problem Statement

The Phase 0 gate is *one real API change, one real repo, one patch that passes a real check*. T1-T4
exist and are green against fixtures we wrote. The gate asks whether they work on a vendor's actual
spec and a real codebase, which is the only test that matters before building T5 and the rest of the
roadmap on top of them.

This card ran that test far enough to find out where it breaks. It breaks at the first step, before
a repository is even chosen.

## Findings

1. **Stripe, the richest source, is refused by T1.** Both spec variants at `v2590` raise
   `UNRESOLVED_REF` on a `file -> file_link -> file` cycle. Beyond cycles, the document contains
   2,124 `anyOf` and 354 `oneOf`, which T1 refuses by policy. Resolving the cycle would not make it
   readable.
2. **Twilio, readable, has nothing to fix.** Three product specs load and diff cleanly across tags
   `2.0.0` (2024-06) to `2.10.0` (2026-10). `api_v2010` yields 113 changes and 79 breaking records,
   but **zero renames, zero endpoint removals and zero parameter removals**. The breaking records are
   `int32 -> int64` format noise, ten removed enum schemas, one format change, and seven response
   pagination properties. T3's only rule is a field rename; T2 cannot turn a response attribute into
   a certain site.
3. **No repository was chosen, deliberately.** A repo would not change either blocker. Picking one
   now would produce a `NO_SITES` or `NO_RULE` result and imply the pipeline had been exercised when
   only its first stage had.

## Goals & Success Metrics

1. **Make the blocker reproducible.** The Twilio pair is committed as the first real vendor spec
   fixture, with a test pinning its 37-change, 3-breaking, 0-rename diff.
2. **Record the Stripe refusal exactly**, including the cycle trail and composition counts, so the
   follow-on does not have to rediscover it.
3. **Do not claim the gate.** The card ends with `UNVERIFIED` in the only sense that matters: no
   real repo, no patch, no check.
4. **Leave one decision, not a backlog.** The next card is chosen from a short table with a
   recommendation.

Success is the evidence being sufficient to choose the next card without re-running the dig.

## Requirements (delivered)

- **M1 — Real fixture.** `tests/fixtures/specs/twilio-lookups-2.0.0.json` and `-2.10.0.json`,
  committed, offline.
- **M2 — Real regression test.** `tests/detect/test_real_twilio_specs.py`: 37 changes, the three
  breaking schema removals, and zero renames.
- **M3 — Evidence record.** `docs/planning/stripe-real-case/evidence.md`: tags, URLs, refusal text,
  composition counts, per-product diff tables, and the consequence.
- **M4 — Honest state.** `docs/ROADMAP.md` M0.3 stays **Not started** (it is not "built" and not
  "shipped"); the gate is open.
- **M5 — Follow-on options.** The evidence record's table: T1 real-spec policy (recommended),
  T3 rule coverage (blocked on T1), another vendor (unbounded search).

## Decision required

**Which follow-on ships next?**

| Option | Recommendation | Why |
|---|---|---|
| **A. `real-spec-readability` (T1)** | **Recommended** | The first blocker. Until T1 can read a rich spec, no real case can be located, proposed or proven. |
| B. T3 rule coverage | No | Useless until A lands; the readable vendor has no such change today. |
| C. Another vendor | Only if A is rejected | Two vendors tried; the search cost is unbounded and the finding would likely repeat. |

If A is chosen, its acceptance tests should use the committed Twilio pair plus a small committed
Stripe excerpt that reproduces the cycle, not the 4.4 MB original. The policy question is explicit:
refuse the whole document (today), refuse only the affected subtree with a recorded `unanalyzed`
list, or support `oneOf`/`anyOf` semantically. The guardrail "never silently skip a subtree" must
survive whichever is chosen.

## Risks & Open Questions

- **R3 (machine-readable changes are rare).** Confirmed in the readable vendor: 2.3 years, no
  renames. Even after T1 readability, the first green case may need a vendor with more churn
  (Stripe) or a different change class.
- **T1 accuracy.** `int32 -> int64` is reported as breaking because the type basis includes
  `format`. That is a false positive for the gate and inflates the breaking count. A follow-on T1
  quality slice may be needed after readability.
- **R1 (repos without tests).** Not reached; no repo chosen.
- **Open question — is composition support the right first move, or is per-subtree refusal enough?**
  Per-subtree refusal is much cheaper and would let a real case proceed on the parts of the spec T1
  understands; full `oneOf`/`anyOf` support is a semantic differ of its own. The card should decide
  this before implementation.
- **Open question — commit size.** The Stripe spec is 4.4 MB; the follow-on should use a minimal
  excerpt, not the whole document.

## Out of Scope

- Implementing composition or cycle support (follow-on A).
- Adding T3 rules (follow-on B).
- Choosing a different vendor or repo (follow-on C).
- T5, the CLI, releases.
- Weakening the gate's definition to "a fixture case".

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The gate is explicit and the blocker is reproducible. |
| User understanding | 🟢 | The user is the next card and the roadmap; both need the decision table. |
| Success metrics | 🟢 | Evidence reproducible, test pinned, gate not claimed. |
| Scope clarity | 🟢 | No production code; the follow-on is explicitly not this card. |
| Edge cases & risks | 🟡 | The T1 format false positive is noted but not quantified beyond the Twilio counts. |
| Stakeholder alignment | 🟡 | Solo project; the reviewer decides A/B/C at the gate. |
| Feasibility | 🟢 | The dig is done; the next card's cost is estimated only qualitatively. |
| Go-to-market | — | Internal milestone. |

**The question I would want answered before greenlighting A:** *If T1 refuses only the subtrees it
cannot analyze, a real case can proceed on the rest, but a change hidden inside an `anyOf` is
invisible. Is a recorded `unanalyzed` list enough honesty for the product, or does every unanalyzed
subtree have to block the run?* That choice decides whether A is a small policy change or a semantic
differ.
