# Spec: `parameters-csharp` (T12d)

- **Feature:** `parameter-inference`
- **PRD:** `docs/planning/parameter-inference/prd.md` (§ M5, M6)
- **Boundary:** the C# parameter seeding and receiver-chain tests.

## In-scope requirements

- `scan_csharp(...)`: each method/local-function `parameter` type resolving through the namespace
  usings/aliases (`StripeClient client`) seeds the body; a missing/`object`/`dynamic`/generic/
  non-SDK parameter is not evidence; a local assignment rebinds/clears.
- No config change; `receivers` still applies.
- Tests: a typed parameter with a receiver chain, an unannotated/`object`/wrong type, a nested
  function, a rebinding, a policy case; the existing suite green.

## Out-of-scope

- Cross-file indexes, generics, `dynamic`.

## Acceptance criteria

- **AC1 — C#.** `static void Create(StripeClient client) { client.Charges.Create(...) }` is rooted;
  an `object`/`dynamic`/generic/nested/rebound parameter is not.
- **AC2 — Policy/regression.** The shared policy decides; no new vocabulary; the existing C# tests
  stay green.
