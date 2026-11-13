# Spec: `inference-python-ts` (T12c)

- **Feature:** `receiver-inference`
- **PRD:** `docs/planning/receiver-inference/prd.md` (§ M1, M2, M6)
- **Boundary:** the Python and TypeScript scanner signature maps and assignment evidence.

## In-scope requirements

- Python `scan(...)`: build a same-file `function/method name -> return type chain` map from the
  `returns` annotations that resolve through the existing SDK roots (`-> stripe.Client` ->
  `("Client",)`); an `Assign`/`AnnAssign` whose RHS is a call to a mapped `Name` binds the receiver.
  A missing return, a non-SDK/string/`Optional`/generic annotation, a `self.method()` call or a
  cross-file function is not evidence; a rebinding without evidence clears.
- TypeScript `scan_ts(...)`: the same map from `function`/method/arrow `return_type`s resolving via
  the import roots/aliases; `const/let/var = fn(...)` with a mapped name binds the receiver. A
  missing/`any`/non-SDK/cross-file return is not evidence; a rebinding clears.
- No new config; `receivers` still applies/overrides.
- Tests: a typed helper with a receiver chain, an unannotated helper, a wrong-return helper, a
  cross-file helper, a rebinding, and a `locate`/`locate_ts` operation/component case; the existing
  suites green.

## Out-of-scope

- Typed parameters (T12d), cross-file indexes, `self`/`this` method return inference.
- Generics/`Optional`/string forward refs.

## Acceptance criteria

- **AC1 — Python.** A `-> stripe.Client` helper roots `client.charges.create(...)`; an unannotated/
  wrong/cross-file helper does not.
- **AC2 — TypeScript.** A `: StripeClient` helper roots `client.charges.create({...})`; an
  unannotated/wrong/cross-file helper does not.
- **AC3 — Policy/regression.** The shared `derive`/`resolve` decides; no new vocabulary; existing
  tests green.
