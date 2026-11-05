# Spec: `ts-scan` (T6)

- **Feature:** `typescript-locator`
- **PRD:** `docs/planning/typescript-locator/prd.md` (§ M3–M11)
- **Boundary:** file discovery, parsing, imports, reachability, aliases, hit/dynamic emission,
  columns. No resolver, no config file, no CLI.

## Problem slice

The shared certainty policy only sees `Hit`/`Dynamic` evidence. This aspect produces that evidence
for TS/TSX/JS without Node: which files are reachable from an SDK import, which names are rooted, and
which constructs are too dynamic to claim.

## In-scope requirements

- `scan_ts(root, sdk_package) -> ScanResult`, reusing `Hit`, `Dynamic`, `DynamicKind`, `ScanResult`
  from `tenon.locate.scan`.
- **Discovery.** Walk `.ts`, `.mts`, `.cts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`; skip
  `node_modules`, `.git`, `dist`, `build`, `.next`, `out`, `coverage`, `.turbo`, `__pycache__`, and
  every dot-directory. Read UTF-8; skip undecodable files and files whose root node `has_error`.
- **Grammar.** `.tsx` → `language_tsx()`; `.ts`/`.mts`/`.cts` → `language_typescript()`;
  `.js`/`.jsx`/`.mjs`/`.cjs` → `language()` from `tree_sitter_javascript`. Cache one `Parser` per
  grammar.
- **Imports.** Bind root names from ES default, named (`as` aliases), namespace,
  `import x = require("pkg")`, and `const x = require("pkg")` / `const { A } = require("pkg")`.
  A specifier is SDK when it equals `sdk_package` or starts with `sdk_package + "/"`. Ignore
  `import type` for runtime roots. A bare `import "pkg"` binds nothing.
- **Reachability.** Record direct SDK importers and relative-import edges (`./x`, `../x` resolved by
  exact path, then + each extension, then `/index.<ext>`). Reverse-edge BFS from direct importers;
  `ScanResult.modules` is the sorted reachable set. No direct SDK import → empty `modules`.
- **Aliases (one hop).** In source order, from `const/let/var` declarators: `new Stripe(...)`,
  `Stripe(...)`, `= stripe`, `= stripe.charges`, and simple object destructuring
  (`{ charges }`, `{ charges: c }`). A redeclaration drops the old alias. A second name hop, a
  nested destructure, a cycle or a computed RHS that is not a static string is an
  `ALIAS_CHAIN`/`GETATTR` `Dynamic`, never a root.
- **Shapes.**
  - `call`: rooted member-chain callee; `chain` is the SDK-relative dotted path, `symbol` the leaf,
    column at the leaf property.
  - `keyword`: identifier object key (`pair` key `property_identifier`, or
    `shorthand_property_identifier`) directly in a rooted call's object argument; column at the key.
  - `dict_key`: string key (`pair` key `string`) in the same position; column at the opening quote,
    symbol the unquoted value.
  - `attribute`: non-callee member access; rooted only when the receiver root is an SDK-imported
    class/constructor or a one-hop class alias.
  - Walk objects inside a direct array argument one level, like T2's dict-in-list rule.
- **Dynamics.**
  - `star_kwargs`: an `object` argument's `spread_element`; a `computed_property_name` key; a
    non-object direct argument to a rooted call (`create(payload)`).
  - `getattr`: `subscript_expression` with a non-string index on a rooted receiver; a computed
    member in a callee chain.
  - `alias_chain`: the multi-hop cases above.
  - Dynamic imports (`import("pkg")`, `require(variable)`) root nothing; calls through them stay
    unrooted.
- **Columns and lines.** tree-sitter points are 0-based rows and byte columns; convert to 1-based
  character columns with the UTF-8 prefix rule, and attach `line_text`.
- **Determinism.** No set iteration in the output; `ScanResult` canonicalises. No writes.

## Out-of-scope

- The certainty policy (`resolve`), config validation, CLI.
- Type inference, `tsconfig` paths, workspace/package `exports`, JSX attribute sites, decorators.
- Static string subscripts as chain segments are optional; a computed chain may be `GETATTR`.

## Acceptance criteria

- **AC1 — Discovery.** All eight extensions are parsed; `node_modules` and build dirs are skipped; a
  parse-error file contributes no hits.
- **AC2 — Imports.** Default/named/namespace/`import =`/`require` roots work; subpath and scoped
  package specifiers match; `import type` does not root; a non-SDK import does not root.
- **AC3 — Reachability.** A file that imports the SDK is scanned; a file that imports it transitively
  is scanned; an unrelated file with `{ amount: 1 }` is absent from a decoy repo; no SDK import at
  all yields empty `modules`.
- **AC4 — Aliases.** `new Stripe()`, `= stripe`, `= stripe.charges`, and object destructuring are one
  hop; a second hop is `ALIAS_CHAIN`; a redeclaration drops the alias.
- **AC5 — Shapes.** A rooted call, an identifier key, a string key and a class-alias attribute each
  produce the expected `Hit` with the exact 1-based line/column/shape/symbol/chain.
- **AC6 — Dynamics.** Object spread, object variable, computed key/member, dynamic import and
  multi-hop alias produce the expected `Dynamic` kinds; a non-rooted call produces rooted=False
  hits.
- **AC7 — Columns.** A non-ASCII line reports the character column a human sees.
- **AC8 — Determinism/no writes.** Two scans are byte-identical; the tree is unchanged.

## Dependencies and sequencing

- Depends on the shipped `tenon.locate.scan` evidence types and the tree-sitter dependencies.
- First aspect; `ts-locate` wraps it.

## Open questions / risks

- tree-sitter node shapes vary slightly between grammar versions; pin the ranges and write fixtures
  against the locked versions.
- A file with a parse error is skipped entirely; a syntax error elsewhere hides its sites.
- Static string subscripts (`client["charges"]`) may be treated as a chain segment or a dynamic;
  choose the simpler honest behaviour and pin it.
