# Spec: `inference-csharp` (T12c)

- **Feature:** `receiver-inference`
- **PRD:** `docs/planning/receiver-inference/prd.md` (§ M5, M6)
- **Boundary:** the C# scanner signature map and assignment evidence.

## In-scope requirements

- `scan_csharp(...)`: build a same-file `method/local function name -> return type chain` map from
  `method_declaration`/`local_function_statement` return types resolving via the namespace
  usings/aliases (`StripeClient`, `Stripe.ChargeClient`); a `var`/explicit declaration whose value is
  an invocation of a mapped name binds the receiver.
- A missing/`void`/non-SDK/cross-file return is not evidence; a rebinding without evidence clears.
- No new config; `receivers` still applies/overrides.
- Tests: a typed helper with a receiver chain, an unannotated/`void` helper, a wrong-return helper,
  a cross-file helper, a rebinding, and a `locate_csharp` operation/component case; the existing
  suite green.

## Out-of-scope

- Typed parameters (T12d), cross-file indexes, generics.
- Fluent chains through an untracked value.

## Acceptance Criteria

- **AC1 — C#.** A `static StripeClient MakeClient()` helper roots `client.Charges.Create(...)`; an
  unannotated/`void`/wrong/cross-file helper does not.
- **AC2 — Policy/regression.** The shared policy decides; no new vocabulary; the existing C# tests
  stay green.
