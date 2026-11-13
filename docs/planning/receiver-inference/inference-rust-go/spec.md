# Spec: `inference-rust-go` (T12c)

- **Feature:** `receiver-inference`
- **PRD:** `docs/planning/receiver-inference/prd.md` (§ M3, M4, M6)
- **Boundary:** the Rust and Go scanner signature maps and assignment evidence.

## In-scope requirements

- Rust `scan_rust(...)`: build a same-file `fn/method name -> return type chain` map from
  `function_item` `return_type`s resolving via the crate roots/aliases (`-> Client`,
  `-> stripe::Client`); a `let` whose value is a call to a mapped bare name binds the receiver. A
  missing/`impl`/non-SDK/cross-file return is not evidence; a rebinding without evidence clears.
- Go `scan_go(...)`: the same map from `func` result types resolving via the import roots/
  `package_name`; a single result or the first type of a result list (`*stripe.Client`,
  `stripe.Client`); a `var`/`:=` whose value is a call to a mapped bare name binds the receiver. A
  named result, a package-qualified/cross-file call, an `error`/non-SDK first result is not
  evidence; a rebinding clears.
- No new config; `receivers` still applies/overrides.
- Tests: a typed helper with a receiver chain, an unannotated helper, a wrong-return helper, a
  cross-file helper, a rebinding, and a `locate_rust`/`locate_go` operation/component case; the
  existing suites green.

## Out-of-scope

- Typed parameters (T12d), cross-file indexes, generics/named returns.
- `self`/method calls through an instance.

## Acceptance Criteria

- **AC1 — Rust.** `fn make_client() -> Client` roots `client.charges().create(...)`; an
  unannotated/wrong/cross-file helper does not.
- **AC2 — Go.** `func newClient() *stripe.Client` roots `client.Charges.New(...)`; an
  unannotated/wrong/cross-file helper does not.
- **AC3 — Policy/regression.** The shared policy decides; no new vocabulary; existing tests green.
