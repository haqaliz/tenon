# Spec: `parameters-rust-go` (T12d)

- **Feature:** `parameter-inference`
- **PRD:** `docs/planning/parameter-inference/prd.md` (§ M3, M4, M6)
- **Boundary:** the Rust/Go parameter seeding and receiver-chain tests.

## In-scope requirements

- Rust `scan_rust(...)`: each `function_item` `parameter` with a `type` resolving through the crate
  roots/aliases (`client: Client`, `client: &Client`, `client: stripe::Client`) seeds the body; an
  untyped `self`, a generic/`impl` or non-SDK parameter is not evidence; a local assignment
  rebinds/clears.
- Go `scan_go(...)`: each `parameter_declaration` type resolving through the import roots/
  `package_name` (`client *stripe.Client`, `client stripe.Client`) seeds the body; a grouped name
  list (`a, b *Client`) binds each; an untyped/non-SDK parameter is not evidence; a local assignment
  rebinds/clears.
- No config change; `receivers` still applies.
- Tests: a typed parameter with a receiver chain, an unannotated/wrong type, a nested function, a
  rebinding, a policy case; the existing suites green.

## Out-of-scope

- Cross-file indexes, generic/`impl Trait`, named result/parameter edge cases.

## Acceptance criteria

- **AC1 — Rust.** `fn f(client: &Client) { client.charges().create(...) }` is rooted; an
  untyped/generic/nested/rebound parameter is not.
- **AC2 — Go.** `func f(client *stripe.Client) { client.Charges.New(...) }` is rooted; a
  grouped list binds each; an untyped/non-SDK/nested/rebound parameter is not.
- **AC3 — Policy/regression.** The shared policy decides; no new vocabulary; existing tests green.
