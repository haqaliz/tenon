# Spec: python-scan

**Slug:** `python-call-site-locator` · **Aspect 3 of 4** · depends on `locate-result`; independent of `symbol-contract`.

## Problem slice

Produce raw, location-accurate evidence from Python source: which expressions in which files
mention an SDK-rooted attribute chain, keyword, dict key or attribute — and which constructs we
cannot see through. This aspect classifies *rootedness* only; naming and certainty are decided
elsewhere.

## In scope

- `scan(root, sdk_package) -> ScanResult` with:
  - `modules: tuple[str, ...]` — repo-relative paths of scanned modules.
  - `hits: tuple[Hit, ...]` — `Hit(path, line, column, shape, symbol, chain, rooted)` where `shape`
    is `call|keyword|dict_key|attribute`, `symbol` is the matched Python name (method name, keyword
    name, dict key string or attribute name), and `chain` is the dotted attribute path after the SDK
    root: the chain of the call itself for `call` hits (`("charges", "delete")` for
    `client.charges.delete`), the chain of the attribute for rooted `attribute` hits, the chain of
    the enclosing rooted call for rooted `keyword`/`dict_key` hits, and `()` otherwise — including
    every unrooted `keyword`, `dict_key` and `attribute` hit.
  - `dynamics: tuple[Dynamic, ...]` — `Dynamic(path, line, column, kind, symbol | None, chain)` with
    `kind` in `star_kwargs|star_args|getattr|alias_chain`. `chain` is the enclosing rooted call's
    dotted chain for `star_kwargs`/`star_args`, the receiver's chain for `getattr`, and `()` when
    unknown, so a consumer can attribute a dynamic to one operation instead of a whole file.
- Reachability: parse every `.py` under `root` (skipping `.venv`, `node_modules`, `build`, `dist`,
  `__pycache__`, and dot-directories); a module is scanned when it directly imports the SDK package
  or imports a local module that is scanned. Relative imports resolve against the package chain;
  absolute local imports resolve against `root` and `root/src`. Unresolvable local imports add no
  edge; a direct SDK import still qualifies the file.
- Import bindings per module: `import stripe` → root name `stripe`; `from stripe import Stripe` →
  `Stripe`; `import stripe as st` → `st`; `from stripe.charges import create` → `create`. Parent
  package of a submodule counts as rooted (`stripe.charges.create` is rooted).
- One-hop aliases: `client = Stripe(...)`, `c = stripe.Stripe(...)`, `c = client` where `client` is
  already rooted. A second hop (`d = c`) is `alias_chain`, not a rooted name. A self-assignment or
  an assignment cycle is also `alias_chain` and must terminate.
- Visitor emits:
  - `call` for an attribute chain ending in a call (`client.charges.delete(...)`), symbol = leaf,
    rooted when the chain's root is an SDK binding; unrooted call hits keep their dotted chain;
  - `keyword` for each keyword argument in a call; rooted when the call's receiver is rooted;
  - `dict_key` for string keys of a dict literal passed (directly or in a list/tuple argument) to a
    call; rooted when that call is rooted;
  - `attribute` for attribute access not in a call position (`charge.amount`), rooted only when the
    receiver is an SDK-imported class or a rooted alias bound to an SDK-imported class;
  - unrooted `keyword`, `dict_key` and `attribute` hits are still emitted, with `rooted=False` and
    `chain=()`;
  - `star_kwargs` / `star_args` dynamics for `**x` / `*x` in a call with a rooted receiver.
  - `getattr` dynamics for `getattr(<rooted expr>, "name", ...)` with the literal name when present.
- Columns: 1-based **character** columns, converting `ast`'s UTF-8 byte offsets through the source
  line. `line_text` is the source line without its newline.
- Read-only: no `import`, no `exec`, no writes to the scanned tree.

## Out of scope

- Deciding certain vs ambiguous, reason assignment, or grouping (aspect 4).
- Cross-file alias resolution, type inference, class-hierarchy method resolution.
- Following a value through function calls or variables holding dicts built elsewhere.
- Executing, importing or installing the scanned code.
- Non-Python files.

## Acceptance criteria

1. A fixture module with `from stripe import Stripe; c = Stripe(); c.charges.delete("ch")` produces
   a `call` hit for `delete`, rooted.
2. The same call in a module that imports nothing from `stripe` is not scanned at all, and a module
   that imports the SDK but calls an unrelated `obj.delete()` yields a non-rooted hit.
3. `client.charges.create(amount=1)` yields a rooted `keyword` for `amount`; `create(**row)` yields a
   `star_kwargs` dynamic; `create({"amount": 1})` yields a rooted `dict_key` for `amount`, and dict
   keys in an unrooted call are reported with `rooted=False`;
   `getattr(client, "delete")` yields a `getattr` dynamic with `symbol="delete"`.
4. `d = c; d.charges.delete("ch")` yields an `alias_chain` dynamic, not a rooted hit.
5. A non-ASCII line before a site yields the correct character column (a byte-offset column would
   be wrong by the encoded length).
6. Scanning the fixture repo twice yields identical `ScanResult`; scanning it never modifies a file
   (mtime/content probe in the test).

## Dependencies & sequencing

Builds after `locate-result`, in parallel with `symbol-contract`. Aspect 4 needs both.

## Open questions

- Local import resolution across a `src/` layout: fixtures cover both `src/`-rooted and flat layouts;
  anything unresolvable is simply not an edge, which can only reduce recall, never inflate certainty.
- Class-body method names (`def delete(self)`) are not call sites and are excluded; a framework that
  dispatches by method name is out of reach and therefore ambiguous by omission, not by claim.
