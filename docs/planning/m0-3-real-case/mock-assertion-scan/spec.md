# Spec: mock-assertion-scan

Parent: `docs/planning/m0-3-real-case/prd.md` (aspect 1 of 3).

## Problem slice

T2 locates the production keyword of a renamed operation field but not the same field inside a
mocked-operation assertion, so T3's patch breaks the repo's own test. The gate cannot pass until the
assertion keyword is a certain site.

## In scope

- `_MOCK_ASSERTIONS = frozenset({"assert_called_with", "assert_called_once_with"})` in `scan.py`.
- In `_Visitor.visit_Call`, when the call is rooted and its SDK-relative chain ends in one of those
  names, keyword hits are emitted with the chain minus the final segment, still rooted, shape
  `KEYWORD`.
- The assertion's own `CALL` hit keeps its full chain, so one production call is still one
  operation call.
- A synthetic fixture repo `tests/fixtures/repos/sdk-mock-assert/` with one production call and one
  assertion.
- Tests in `tests/locate/test_scan.py` and `tests/locate/test_resolve.py`, including negatives.

## Out of scope

- `call_args.kwargs["field"]`, `call_args[1]["field"]`, `assert_has_calls`, `assert_not_called`.
- Any change to `resolve.py`, `query.py`, `propose/`, `prove/`.
- Star-args / star-kwargs dynamics inside assertions.
- Other mock libraries or pytest assertion rewriting.

## Acceptance criteria

1. `scan` over the fixture reports the assertion keyword with chain
   `("checkout", "Session", "create")` and `rooted=True`.
2. The same scan reports exactly one `CALL` hit on `("checkout", "Session", "create")`.
3. `locate` over the fixture with the operation mapping returns exactly two certain sites, no
   ambiguity groups and no `reason`.
4. A keyword on an unrooted `create.assert_called_with(...)` stays unrooted and is not a site.
5. An ordinary rooted call keyword is unchanged.
6. The full suite passes offline; no new dependency.

## Dependencies

None beyond T2 as shipped. This aspect lands before the pinning test, which depends on it.
