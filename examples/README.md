# Tenon examples

The quickstart runs the shipped pipeline against the committed, read-only fixture
`tests/fixtures/repos/proof-basic`. It locates the `amount` keyword in
`acme/billing.py`'s `client.charges.create(...)`, proposes the `amount_cents` rename and proves it
with the fixture's import.

From the repository root:

```sh
# 1. Locate the affected sites (exit 1 when sites are found).
uv run tenon check tests/fixtures/repos/proof-basic \
  --old examples/quickstart/old.yaml \
  --new examples/quickstart/new.yaml \
  --language python --sdk-package acme.client
```

Expected: `renamed #/components/schemas/Charge/properties: amount -> amount_cents`,
`acme/billing.py:6:... keyword amount`, `1 certain site`.

```sh
# 2. Propose the diff and prove it (no checkout write, no PR).
uv run tenon fix tests/fixtures/repos/proof-basic \
  --old examples/quickstart/old.yaml \
  --new examples/quickstart/new.yaml \
  --language python --sdk-package acme.client \
  --check "python3 -c 'import acme.billing'"
```

Expected: the one-line diff `amount=amount` -> `amount_cents=amount`, `Proof: TESTS_PASSED`, exit 0.

```sh
# 3. The same run as a provider bundle (dry run: no --open-pr).
uv run tenon provider migrate tests/fixtures/repos/proof-basic \
  --bundle examples/quickstart/bundle.json
```

Expected: `provider: acme`, `migration: amount-cents`, the diff, `Proof: TESTS_PASSED`, exit 0.

Add `--open-pr --remote gh` (or `--remote app` with the T10a app flags) to open the reviewed PR; the
fixture is not a git remote, so keep the examples to the dry run.

The bundle's paths are relative to `bundle.json`, so the example directory is portable. The check
uses `python3` from `PATH`; the fixture package is imported from the copy's working directory.
