# PRD: M0.3 — the first real end-to-end case

- **Slug:** `m0-3-real-case`
- **Capability:** Phase 0 gate **M0.3** (`docs/ROADMAP.md`) plus the smallest T2 follow-on it needs
- **Milestone:** closes the Phase 0 gate: one real API change, one real repo, one patch that passes a
  real check
- **Status:** draft, awaiting the review gate
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1, T2, T3 and T4 are shipped, but no run has ever taken a real vendor change through all four
against a repo someone else wrote. That is the Phase 0 gate. Until it passes, every later capability
(T5 PR, T6 TypeScript, T7 proof ladder) is built on a pipeline that has only seen fixtures.

The one analyzable change from the real Stripe pair is
`payment_method_types` → `allowed_payment_method_types` on `POST /v1/checkout/sessions`
(`docs/planning/lazy-ref-resolution/evidence.md` §4). T1 emits it as `renamed`, `inferred`.

The deep dig found the first real repo exposes a smaller gap than "T1 cannot read real specs". In
every offline-runnable repo inspected, the test that exercises the Stripe call encodes the old field
name in a **mock assertion**:

```python
stripe.checkout.Session.create.assert_called_with(
    payment_method_types=config.PAYMENT_METHOD_TYPES, ...
)
```

T2 misses that line: the keyword's chain is `checkout.Session.create.assert_called_with`, not
`checkout.Session.create`. T3 therefore proposes only the production edit, and the repo's own test
fails. Verified on `yezz123/stripe-template` at `9d9178c`: the one-line proposal makes
`tests/test_payment.py::test_session_url` fail with `AssertionError: expected call`.

The gate cannot be met without naming that line. The smallest complete fix is a T2 scan rule for the
two `unittest.mock` assertion methods. T3 needs no change: it already edits any certain site carrying
the old symbol, including a keyword in a test.

**For whom:** the developer whose integration Tenon repairs, and T5/T7, which need one honest
end-to-end result to build on.

## Goals & Success Metrics

1. **The gate runs.** T1 → T2 → T3 → T4 on the real Stripe pair and the real repo, with T4 returning
   `TESTS_PASSED` for the documented check.
2. **The test that encodes the old contract is fixed with the code.** T2 locates the production
   keyword and the mock-assertion keyword; the proposal contains exactly two edits, one per file.
3. **The proof is honest.** The evidence states the check command, the deselected tests, the mocked
   call, and what `TESTS_PASSED` does not establish.
4. **The real case stays reproducible.** A committed, MIT-attributed snapshot of the two relevant
   repo files pins the located sites and the exact diff in an offline test.
5. **No weakening of existing policy.** No new proof level, no change to the T4 contract, no new
   ambiguity suppression: an assertion keyword is *certain* only when the chain is rooted in the SDK.
6. **Deterministic, offline tests.** The full suite passes; no network in `tests/`.

Measured by assertions in `tests/locate/` and the evidence doc, not by prose.

## User Personas & Scenarios

- **Developer.** Gets a two-file diff: the call site and the test that pins the old field. Both must
  change together, or the PR is broken on arrival.
- **T4 proof runner.** Applies the diff to a copy and runs the chosen check; it never decides that a
  mocked call is semantically correct.
- **T5 PR writer (later).** Renders the diff and the proof level; needs the skipped/uncertain list
  and the `inferred` rename confidence to be intact.

Scenario: Stripe drops `payment_method_types` from the checkout-session request schema. T1 emits the
inferred rename. T2 finds `app/router/v1/payment.py:41` and `tests/test_payment.py` (the assertion).
T3 proposes both edits. T4 copies the repo, runs the offline subset before and after, and records
`TESTS_PASSED`. The evidence says the call is mocked, so the level means "the repo's offline tests
still pass", not "the new field behaves the same".

## Requirements

### Must have

- **M1 — Mock-assertion keyword re-attribution.** In `src/tenon/locate/scan.py`, when a rooted call's
  callee chain ends in `assert_called_with` or `assert_called_once_with`, its keyword hits are
  emitted with the chain minus that final segment, still `rooted=True`, shape `KEYWORD`.
- **M2 — No double counting.** The `CALL` hit for the assertion keeps its full chain. Only keywords
  are re-attributed, so one production call is still counted as one operation call and
  `MULTIPLE_CANDIDATES` is not triggered by a test assertion.
- **M3 — No policy change.** `resolve.py` is untouched. The re-attributed keyword is exactly what
  `_field_hits` already accepts (rooted, `KEYWORD`, the operation chain); no new certainty rule, no
  new ambiguity reason.
- **M4 — Closed set.** Only the two assertion method names. `call_args.kwargs["field"]`,
  `call_args[1]["field"]`, `mock.assert_has_calls`, and arbitrary mock methods are out of scope and
  stay unfound.
- **M5 — Pinned real case.** Commit a snapshot under
  `tests/fixtures/repos/real-stripe-template/` containing `app/router/v1/payment.py`,
  `tests/test_payment.py`, the upstream `LICENSE`, and a `PROVENANCE.md` with repo URL, commit SHA,
  the files taken, and the MIT licence. No `.github`, no scripts, no secrets.
- **M6 — Pinning test.** An offline test in `tests/locate/test_real_stripe_template.py` runs
  T1 (a minimal two-version spec pair carrying the rename) → T2 → T3 over the snapshot and asserts:
  two certain sites (one `keyword` in each file), no ambiguity groups, and a unified diff containing
  exactly those two edits, byte-stable.
- **M7 — The gate run.** With the full Stripe `v2500` / `v2596` documents and a clone of the repo at
  `9d9178c` in `.cache/` (never committed), run T1→T4 with
  `LocateConfig(sdk_package="stripe", operations={"POST /v1/checkout/sessions": "checkout.Session.create"})`
  and the check
  `[<repo-venv>/bin/python, "-m", "pytest", "-q", "-k", "not setup_new_method"]`
  with `STRIPE_API_KEY=sk_test_x` exported. Baseline must be green (5 passed, 2 deselected); the
  result must be `TESTS_PASSED`.
- **M8 — Evidence.** `docs/planning/m0-3-real-case/evidence.md` records: repo URL and SHA; base
  commit; the change record; the config; the exact check command and environment; baseline and
  after results; the proposal diff; the two deselected tests and why (they call the live Stripe API
  with a fake key and are red before any patch); the spec description showing the semantic change
  (the new field filters the dynamically computed set instead of listing methods explicitly); and an
  explicit statement of what the proof does **not** establish.
- **M9 — Honest failure path.** If the run cannot reach `TESTS_PASSED`, the evidence records the
  actual `UNVERIFIED` cause and the gate stays open. A plausible diff is not proof.

### Should have

- **S1 — Negative scan tests.** A keyword in an ordinary call whose chain merely *resembles* an
  assertion is unchanged; an assertion on an unrooted chain is not rooted.
- **S2 — `assert_called_once_with` covered** by the same rule and one test.
- **S3 — Roadmap truth.** After a passing run, mark M0.3 shipped in `docs/ROADMAP.md` and add the
  mock-assertion limit to T2's known-limits paragraph in
  `docs/technical/CAPABILITY_ROADMAP.md` (covering only the two assertion methods).

### Nice to have

- **N1 — Recorded venv pins** (Python and package versions) in the evidence so the proof run can be
  repeated months later.

## Data Model

No new public types. One module-private constant in `scan.py`:

```
_MOCK_ASSERTIONS = frozenset({"assert_called_with", "assert_called_once_with"})
```

Chain semantics after the rule, for `stripe.checkout.Session.create.assert_called_with(payment_method_types=...)`:

| Hit | Shape | Chain | Rooted |
|---|---|---|---|
| the assertion call itself | `call` | `(checkout, Session, create, assert_called_with)` | yes (unchanged) |
| `payment_method_types` keyword | `keyword` | `(checkout, Session, create)` | yes (re-attributed) |

Nothing else changes: `LocateResult`, `Site`, `Proposal` and the diff format are untouched.

## API Contract

Unchanged. `locate(change, root, config)` simply returns more certain sites for the same inputs, and
`propose(change, located, root)` edits them. No new argument, no new return type.

## Technical Considerations

- **Where the change lives.** `_Visitor.visit_Call` already computes `chain` and emits keywords with
  it. The rule is a local computation of an `attributed` chain before the keyword loop. No new pass,
  no dataflow, no inter-procedural analysis.
- **Why not resolve.** `resolve.py` is the single certainty policy and its rules are intentional. The
  assertion keyword is already exactly the evidence `_field_hits` expects once the chain is right;
  adding a second certainty path would duplicate the policy.
- **Why not `call_args`.** `call_args.kwargs.get("payment_method_types")` and
  `call_args[1]["payment_method_types"]` are string lookups with no rooted chain. Associating them
  needs file-level heuristics or dataflow, and guessing there violates "ambiguity reported, never
  guessed". They stay out, named in T2's limits.
- **Test-first.** The scan test fails before the rule and passes after; the pinning test fails until
  the rule exists; the negative tests guard the boundary.
- **No new dependencies.** The scanner is stdlib `ast`.
- **Third-party snapshot.** MIT permits redistribution with the licence; `PROVENANCE.md` makes the
  origin and pin auditable.

## Risks & Open Questions

- **R1 (repos lack tests, so proof is weak).** The repo's test mocks `Session.create`; it proves the
  call shape and that nothing else broke, not that the new field behaves the same. Mitigation: the
  evidence states the limit; the level is not upgraded; T7 (proof ladder) is the long-term answer.
- **R2 (a verified PR still breaks production).** The rename changes semantics: the `v2596`
  description says the new field filters the dynamically computed set rather than listing methods
  explicitly. The mechanical edit is valid syntax and wrong behavior for a caller that relied on an
  explicit list. Mitigation: the evidence records the semantic difference; no PR is opened (T5 does
  not exist yet).
- **R4 (wrong call-site location).** Over-matching a mock assertion as an operation keyword would
  rename an unrelated string. Mitigation: only two assertion names, only rooted chains, only
  keyword arguments; negative tests pin the boundary.
- **The repo is a 2024 template, not a production service.** The gate is met literally (a real,
  public, MIT repo with tests), not strongly. Mitigation: say so; a production case remains a later
  card.
- **Two tests are deselected.** The full suite is red before any patch because it calls the live
  Stripe API. Mitigation: name them, record why, and keep the check green only for the offline
  subset; never call the subset "the full suite".
- **Open question — fixture drift.** The committed snapshot is two files, not the repo. If the
  upstream repo changes, the snapshot still pins Tenon's behavior at a known SHA. That is the point;
  re-snapshotting is a deliberate act.
- **Open question — SDK version.** The repo does not pin `stripe`; the Python SDK forwards arbitrary
  kwargs. The card proves a code-level rename, not an SDK upgrade. Version bumping is not Tenon's job.

## Out of Scope

- T5 PR writer, branches, commits, merges.
- T6 TypeScript locator, T7 proof ladder, T8 probe, T9 corpus.
- `call_args`/`assert_has_calls` shapes and any mocked-call inspection beyond the two assertion
  keywords.
- Semantic verification that the new field is the right replacement; that is a human or model
  judgement, not an execution proof.
- CLI (`src/tenon/cli`, M1.4), exit codes, JSON report.
- Changes to the T4 proof contract or `UNVERIFIED` causes.
- Other repos, other vendors, other change kinds.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `mock-assertion-scan` | The `_MOCK_ASSERTIONS` set, chain re-attribution in `visit_Call`, call-hit preservation, scan and resolve tests, negative cases. No file I/O beyond the scanner. |
| `real-case-pin` | The MIT snapshot, `PROVENANCE.md`, the minimal spec pair, the offline T1→T3 pinning test, byte-stable diff assertion. |
| `gate-evidence` | The one-shot T1→T4 run against the real clone and full specs, the check command, the honest limits, the roadmap update after success. Manual, documented. |

## Areas to strengthen before sharing (self-critique)

- **Feasibility signal is strong but narrow.** The scan gap and its fix are verified; the T4 result
  itself is not yet observed. The card is honest about that: M9 keeps the gate open if the run fails.
- **"Real repo" is the weakest claim.** A template with two live-API failures is a real repo but not
  a representative one. A production case should follow before the gate is treated as durable
  evidence.
- **The T2 rule is test-double-specific.** It improves one common mock idiom and names the rest as
  out of scope; it is not a general "tests are code too" feature.
