# PRD: M0.3 — First real case (Phase 0 gate)

- **Slug:** `m0-3-first-real-case`
- **Milestone:** M0.3 in `docs/ROADMAP.md` — the Phase 0 gate
- **Capabilities exercised:** T1 detect, T2 locate (Python), T3 propose, T4 prove (all shipped)
- **Status:** dig complete; **gate met in the dig**; deliverables and evidence not yet committed
- **Card:** `docs/planning/_card/issue.md`
- **Prior dig:** `docs/planning/stripe-real-case/` (gate was blocked, then unblocked by
  `docs/planning/lazy-ref-resolution/`)

## Problem Statement

The Phase 0 gate is *one real API change, one real repo, one patch that passes a real check*.
T1-T4 are green against fixtures we wrote. Until the pipeline runs once on a vendor's actual spec
and a real codebase, every roadmap item after it — T5 first — rests on an untested assumption.

The prior card (`stripe-real-case`) ran the dig far enough to find the blockers: T1 refused rich
Stripe specs and T3 had nothing to fix in the readable Twilio pair. `real-spec-readability` and
`lazy-ref-resolution` fixed the first. The remaining step is the one this card takes: choose a real
repo and run detect -> locate -> propose -> prove end to end.

**For whom:** the roadmap reviewer (this is the gate) and the next card (T5), which needs a
pipeline that has produced at least one honest proof on real input. There is no external user yet.

## Dig result (already run)

The gate was met during the dig on 2026-11-01/02. This card records and pins it; it does not
re-discover it.

| Step | Input | Result |
|---|---|---|
| Detect | Stripe `v2500` -> `v2596` (`latest/openapi.spec3.json`) | 289 changes, 52 breaking, 1 rename |
| Change | `POST /v1/checkout/sessions` request body | `payment_method_types` -> `allowed_payment_method_types`, breaking, inferred |
| Locate | `fighthealthinsurance/fighthealthinsurance` @ `56e69cfa4440aea0a42d016f84e6af336c5e0d3c` | 3 certain keyword sites, 0 ambiguous |
| Propose | the 3 certain sites | 3 edits; unified diff applies with `git apply -p1` |
| Prove | `tests/sync/test_pwyw_checkout.py`, 12 tests | **`TESTS_PASSED`**: 12 passed before, 12 passed after, patch applied |

Sites: `fhi_users/auth/rest_auth_views.py:754`, `fighthealthinsurance/views.py:3904` and `:4177`.

The locate step required the explicit mapping
`POST /v1/checkout/sessions` = `checkout.Session.create`. Without it, inference produces
`checkout.sessions.create` (lowercase, plural resource segment) and matches nothing: the SDK class
is `Session`, the path segment is `sessions`.

## Goals & Success Metrics

1. **Record the gate honestly.** The evidence names the repo and commit, the spec tags, the
   command, the environment, the diff, the proof JSON, and the coverage nuance below.
2. **Pin the real call shape.** A committed, offline fixture test reproduces the Stripe chain
   (`checkout.Session.create`) and the explicit mapping, so a future refactor of T2/T3 cannot
   silently regress the one real case.
3. **Update the roadmap only because the gate was met.** `M0.3` moves to Shipped; if the evidence
   cannot support a claim, the claim is reduced, not the gate.
4. **Keep the suite green and deterministic.** No network in `tests/`; the fixture run stays
   offline.
5. **Do not build the next capability.** T2 inference, T5, the CLI and composition semantics are
   out of scope; the gate is the deliverable.

## Requirements

### Must-have

- **M1 — Gate evidence.** `docs/planning/m0-3-first-real-case/evidence.md`:
  - target repo URL and pinned SHA; Stripe tag pair and the rename record;
  - the three located sites with file/line/column/shape;
  - the proposed unified diff (3 edits);
  - the exact proof command, the external-venv setup, and the proof JSON;
  - baseline and after results with timings;
  - the **coverage nuance**: the focused test exercises the PWYW call through a mocked
    `Session.create` and reads `call_args[1]`, but does not assert `payment_method_types`; it
    passes before and after. The other two patched sites are not exercised by this check.
- **M2 — Regression fixture.** `tests/fixtures/repos/sdk-stripe-checkout/` with a module that calls
  `stripe.checkout.Session.create(payment_method_types=["card"], ...)`, plus
  `tests/locate/test_stripe_shape.py`:
  - without the mapping, the derived candidate is `checkout.sessions.create` and the locate result
    is `NO_SITES` (documenting why the mapping is required);
  - with the mapping, exactly one certain `keyword` site at the expected path/line/column;
  - `propose` yields one edit and a diff that changes only that keyword.
  - Offline and deterministic; no model, no network.
- **M3 — State updates.** `docs/ROADMAP.md` M0.3 -> Shipped with the repo, SHA and proof level;
  `CLAUDE.md` status line; the stale `docs/planning/stripe-real-case/prd.md` status points at this
  evidence.
- **M4 — Honest limits.** The evidence also records: (a) T4's isolated copy drops `.venv`, so the
  proof used an interpreter outside the copy; (b) the `tenon.toml` mapping was required for this
  endpoint; (c) the one rename is the only change T3's rule can act on in this pair.

### Should-have

- Record the exact package versions (stripe 12.2.0, Django 5.2.18, pytest 9.2.0,
  setuptools 79.0.1) and the Python version, so the proof can be reproduced.
- Record the proof timeout (900 s) and the observed duration (229.5 s), since T4's default is 300 s.

### Nice-to-have

- None. Anything beyond the gate belongs to the next card.

## Technical Considerations

- **No production code change is required.** The dig ran the shipped APIs as a library. The
  deliverable is evidence plus a regression fixture; adding a CLI or a composed pipeline function
  would be M1.4 scope and is deliberately excluded.
- **The fixture is not the gate.** The gate evidence is the real repo run; the fixture only pins
  the shape. Committing the target repo, its tests or the 4.4 MB Stripe specs is out of scope.
- **Test-first for a regression fixture.** The test is written first against a fixture path that
  does not exist (red: no certain site), then the fixture repo is added (green). Production code is
  untouched.
- **Determinism.** The change record is constructed from the real T1 output; the fixture uses the
  same names and chain. No network, no model, no clock.

## Risks & Open Questions

- **R1 — the check was not red before.** The focused test exercises the call but does not assert
  the old field, so it passes before and after. `TESTS_PASSED` is the honest level ("the repo's
  own tests pass after the patch, and were affected before"), but it does not prove the patch was
  *necessary*. Mitigation: state the nuance in the evidence; do not call the patch "verified"
  beyond the check that ran. A future card may require a pre-patch failure for the gate.
- **R3 — one rename, one endpoint.** The readable Stripe pair offers exactly one change T3 can
  patch. The gate proves the pipeline, not breadth. T3 rule coverage and more vendors remain open.
- **T4 environment limitation.** The isolated copy drops `.venv`; a repo that needs its own
  environment must name an external interpreter. This is a known T4 limit, not a new one; the
  evidence records the workaround rather than hiding it.
- **Repo drift.** The target is pinned by SHA; the evidence is a point-in-time record. The repo may
  change after this card.
- **Open question — T2 inference.** Should a follow-on infer `checkout.Session.create` from
  `/v1/checkout/sessions` (plural -> PascalCase) so users do not need a mapping per endpoint? The
  gate shows the mapping is required for this endpoint; it does not settle whether inference is
  worth changing. Recommended follow-on after T5, if real repos keep needing mappings.
- **Open question — gate standard.** Is a focused, affected-but-green check enough for future
  Phase 0-style gates, or must the check fail before the patch? This card accepts the former and
  says so.

## Out of Scope

- T2 inference changes (singular/PascalCase resource names), raw-HTTP call sites.
- T3 rule coverage (removals, required additions, type changes, endpoint renames).
- T5 PR writer, T6 TS/JS, T7 proof ladder, T8 MCP/probe, T9 corpus, T10 provider layer.
- CLI/pipeline glue, `tenon check` / `tenon fix`, exit codes.
- Composition semantics for `oneOf`/`anyOf` and the `format` false positive.
- Committing the target repo, its test suite, or the Stripe spec snapshots.
- Any model proposer or code egress.
- Weakening the gate to "a fixture case".

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The gate is explicit and the prior blockers are cited. |
| User understanding | 🟡 | Internal milestone; the "user" is the next card and the roadmap reviewer. |
| Success metrics | 🟢 | Gate met, evidence reproducible, fixture pinned, suite green. |
| Scope clarity | 🟢 | No production change; T2/T5/CLI explicitly excluded. |
| Edge cases & risks | 🟡 | The check is green before the patch; the external-venv workaround is a T4 limit. |
| Stakeholder alignment | 🟡 | Solo project; the reviewer is the gate. |
| Feasibility | 🟢 | Already run end to end; 229.5 s proof, deps installed in an external venv. |
| Go-to-market | — | Internal milestone. |

**Areas to strengthen before sharing:** the R1 nuance is the one a reviewer should challenge. If
"affected but green before" is not enough for the gate, the card must find a check that fails before
the rename, and the search is open-ended.

**The question I would want answered before greenlighting this:** *If the chosen check passes before
the patch and never asserts the renamed field, what did the gate prove that `git apply` plus a green
suite would not?* The answer this card records: it proved the pipeline located the real call sites,
produced the exact diff, and the repo's selected check still passes — not that the patch was
necessary. That distinction is the honest limit of this evidence.
