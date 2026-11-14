# Spec: `parameters-python-ts` (T12d)

- **Feature:** `parameter-inference`
- **PRD:** `docs/planning/parameter-inference/prd.md` (§ M1, M2, M6)
- **Boundary:** the Python/TypeScript parameter seeding and receiver-chain tests.

## In-scope requirements

- Python `scan(...)`: for each function/method, the annotated `args`/`posonlyargs`/`kwonlyargs`
  (a direct `Name`/`Attribute` resolving through the SDK roots) seed the receiver bindings for the
  body. An unannotated parameter (including `self`), a string/`Optional`/generic annotation or a
  non-SDK type is not evidence. A local assignment rebinds/clears.
- TypeScript `scan_ts(...)`: each `required_parameter`/`optional_parameter` with a `type_annotation`
  resolving through the import roots/aliases seeds the function/method/arrow body; a missing/`any`/
  non-SDK parameter is not evidence; a local assignment rebinds/clears.
- No config change; `receivers` still applies.
- Tests: a typed parameter with a receiver chain, an unannotated/`any`/wrong type, a nested
  function, a rebinding, a policy case; the existing suites green.

## Out-of-scope

- Cross-file indexes, `self`/`this`, generics/overloads, unannotated parameters.

## Acceptance criteria

- **AC1 — Python.** `def f(client: stripe.Client): client.charges.create(...)` is rooted; an
  unannotated/nested/rebound parameter is not.
- **AC2 — TypeScript.** `function f(client: StripeClient) { client.charges.create(...) }` is rooted;
  an unannotated/`any`/nested/rebound parameter is not.
- **AC3 — Policy/regression.** The shared policy decides; no new vocabulary; existing tests green.
