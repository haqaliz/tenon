# PRD: TypeScript/JavaScript locator (T6)

- **Slug:** `typescript-locator`
- **Capability:** T6 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M2.1 in `docs/ROADMAP.md` (Phase 2)
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T2 locates Python call sites. The engine is now usable end to end — detect, locate, propose, prove,
PR, CLI — but only for Python repositories. A vendor that ships a JavaScript SDK, or a customer whose
integration is TypeScript, gets `NO_SDK_IMPORT` on every change. The second-largest ecosystem is
outside the product.

T6 must answer the same question in TS/JS: given a T1 `Change`, where are the affected call sites,
which are certain, and which are too dynamic to claim? It must return the **same** `LocateResult` so
T3's proposer, T4's proof runner, T5's PR writer and the CLI keep working unchanged.

The dangerous shortcut is a regex/token search that reports every `amount` as a site. `CLAUDE.md`
forbids it: a certain site is rooted in an SDK import or an alias of one; everything else is an
ambiguity group with a named reason. The deep dig confirmed `tree-sitter` 0.26 with the TypeScript
0.23 and JavaScript 0.25 grammars installs as wheels and parses TS/TSX/JS offline. T2's `Hit`,
`Dynamic`, `ScanResult`, `Query`, `derive` and `resolve` certainty policy are language-agnostic; T6
needs a TS scanner that emits the same evidence, a TS config, and a CLI language switch.

**For whom:** T3/T4/T5 (same contracts), the developer running `tenon check` on a TS/JS repo, and the
next capabilities (T7 proof levels, T8 MCP/probe) that should not care which language found the site.

## Goals & Success Metrics

1. **Same contract.** `locate_ts(change, root, config)` returns the existing `LocateResult`: certain
   `Site`s with file/line/column, `AmbiguousGroup`s with reasons, or one `LocateReason`.
2. **Certainty is import-rooted.** A site is certain only when its chain starts at an SDK import
   (`import`, `require`, `import =`) or a one-hop alias of one. The decoy fixture proves an unrelated
   `amount` in a non-SDK module is never certain.
3. **Ambiguity is first-class.** Object spread / an object variable → `DYNAMIC_KWARGS`; a computed
   member → `DYNAMIC_GETATTR`; a multi-hop alias → `ALIAS_CHAIN`; unresolved receivers, multiple
   candidates and unmapped symbols keep their T2 reasons. No new reason enum in this card.
4. **Determinism.** Same repo, change and config → byte-identical `LocateResult.to_json()`, ordered
   by `(path, line, column)`.
5. **Offline and Node-free.** Parsing happens in Python via tree-sitter; no Node, no `tsc`, no type
   inference, no network. Committed fixture repos only.
6. **Usable.** `tenon check` / `tenon fix` accept `--language ts` (or `[locate] language = "ts"`) and
   run the same pipeline. T3's existing shapes edit the TS sites; no new proposer rule.

Measured by committed TS/TSX/JS fixtures in `tests/locate/` and CLI tests, offline.

## User Personas & Scenarios

- **T3 propose.** Gets the same `keyword` / `dict_key` / `attribute` / `call` sites and edits the
  first three with the existing rename rule. A TS object key `{ amount: 1 }` is a `keyword`; a quoted
  key `{ "amount": 1 }` is a `dict_key`; `charge.amount` is an `attribute`; a method call is `call`.
- **T4 prove.** Runs the user's `npm test` / `node --test` command in the isolated copy. The copy
  skips `node_modules` (see Risks); a check command that needs it may be `TESTS_FAILED_BEFORE`.
- **Developer.** `tenon check . --old old.json --new new.json --language ts` lists the affected TS
  calls, or `[locate] language = "ts"` in `tenon.toml`.
- **T5 PR.** Unchanged; the proof and the diff are language-neutral.

Scenario: a vendor renames `amount` to `amount_cents` on `POST /v1/charges`. T1 emits `renamed`.
T2's TS scanner finds `stripe.charges.create({ amount: 100 })` certain at the key, a `payload`
variable argument as `DYNAMIC_KWARGS`, and an unrelated `{ amount: 1 }` in a non-SDK module is not
reported. T3 edits the key; T4 proves; T5 opens the PR.

## Requirements

### Must have

- **M1 — Inputs.** `locate_ts(change: Change, root: str | Path, config: TsLocateConfig) ->
  LocateResult`. `TsLocateConfig` carries `sdk_package` (npm package name, scoped names allowed),
  `operations` (`"METHOD /path" -> "charges.create"`) and `fields` (`"Charge.amount" ->
  "amount_cents"`). No re-diff, no re-read of the OpenAPI document.
- **M2 — Shared query.** Reuse `tenon.locate.query.derive` and its `Query` contract. Add a small
  `QueryConfig` protocol for the two mappings so both `LocateConfig` and `TsLocateConfig` satisfy it;
  no behaviour change to Python. Endpoint/component scope, mapping keys, inference and
  `UNSUPPORTED_CHANGE_KIND` / `OPERATION_NOT_MAPPED` stay identical.
- **M3 — File discovery.** Scan `.ts`, `.mts`, `.cts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs` under the
  root, skipping `node_modules`, `.git`, `dist`, `build`, `.next`, `out`, `coverage`, `.turbo`,
  `__pycache__`, and every dot-directory. A file with a tree-sitter parse error is skipped. Reads are
  UTF-8 and read-only.
- **M4 — Grammar.** `.ts`/`.mts`/`.cts` → TypeScript grammar; `.tsx` → TSX grammar; `.js`/`.jsx`/
  `.mjs`/`.cjs` → JavaScript grammar. (`.mts`/`.cts` use the TypeScript grammar; add them to the
  extension set.)
- **M5 — Import bindings.** Root names from:
  - ES default (`import Stripe from "stripe"`), named (`import { Stripe } from "stripe"`, with
    `as` aliases), namespace (`import * as stripe from "stripe"`), and `import stripe = require(
    "stripe")`;
  - CommonJS `const stripe = require("stripe")` and `const { Stripe } = require("stripe")`;
  - a bare `import "stripe"` binds nothing and is not a root.
  `import type` is ignored for runtime rooting. A specifier matches the SDK when it equals
  `sdk_package` or starts with `sdk_package + "/"` (subpath imports). Relative imports are local, not
  SDK.
- **M6 — Reachability.** Parse every candidate file; record local import edges for relative
  specifiers by resolving `./x`/`../x` against the exact path plus `.ts`, `.tsx`, `.js`, `.jsx`,
  `.mjs`, `.cjs`, and `/index.<ext>`. A module is scanned when it directly imports the SDK or
  transitively imports a scanned module (T2's reverse-edge BFS). No SDK import anywhere →
  `NO_SDK_IMPORT`. Path aliases (`@/...`), `tsconfig` `paths` and package `exports` are not resolved;
  a module reachable only through them is missed, not guessed.
- **M7 — One-hop aliases.** In source order, bind a name to an SDK path from `const/let/var x =
  new Stripe(...)`, `= Stripe(...)`, `= stripe`, `= stripe.charges`, and simple object destructuring
  (`const { charges } = stripe`, `const { charges: c } = stripe`). A reassignment to a non-SDK value
  drops the alias. A second name hop, a nested destructure, or a cycle is an `ALIAS_CHAIN`
  `Dynamic`, never a certain root.
- **M8 — Site shapes.** Emit T2's four shapes with TS syntax:
  - `call`: a call expression whose callee member chain is rooted; `chain` is the SDK-relative dotted
    path (`charges.create`), `symbol` the leaf.
  - `keyword`: an unquoted object-literal key (including shorthand) that is an identifier, directly
    in a rooted call's argument object; column at the key.
  - `dict_key`: a quoted string key (`"amount"` / `'amount'`) in the same position; column at the
    opening quote, symbol the unquoted value.
  - `attribute`: a member access whose root is an SDK-imported class/constructor or a one-hop alias
    of one (`charge.amount` where `charge = new Charge()`).
  Arrays of objects in a direct argument are walked one level, matching T2's dict-in-list rule.
  JSX attribute names are not sites in this card; `.tsx`/`.jsx` are parsed so calls and objects in
  those files are found.
- **M9 — Dynamics.** Emit the existing `Dynamic` evidence:
  - an object spread `{ ...payload }` or a non-literal object argument (`create(payload)`) inside a
    rooted call → `STAR_KWARGS` with the call chain (the field may be in the payload);
  - a computed member `client[key]` → `GETATTR`;
  - a computed object key `{ [key]: 1 }` → `STAR_KWARGS`;
  - a second-hop alias/destructure/cycle → `ALIAS_CHAIN`.
  Dynamic imports (`import("stripe")`, `require(variable)`) root nothing; calls through them are
  unrooted and become `UNROOTED_RECEIVER` when their chain matches a candidate.
- **M10 — Certainty.** Reuse `tenon.locate.resolve` unchanged. The TS scanner emits `Hit(rooted)`
  and `Dynamic`; the resolver applies the same rule table. `NO_SDK_IMPORT`, `NO_SITES`,
  `OPERATION_NOT_MAPPED`, `UNSUPPORTED_CHANGE_KIND`, `MULTIPLE_CANDIDATES`, `UNROOTED_RECEIVER`,
  `UNMAPPED_SYMBOL`, `DYNAMIC_KWARGS`, `DYNAMIC_GETATTR`, `ALIAS_CHAIN` keep their T2 meanings.
- **M11 — Determinism and no mutation.** Same inputs → byte-identical JSON; sites ordered by
  `(relative POSIX path, line, column)`; no writes, no imports, no execution of scanned code.
- **M12 — CLI.** `--language python|ts` on `check` and `fix`; `[locate] language` in `tenon.toml`
  (default `python`). For `ts`, load a `TsLocateConfig` from the same `[locate]` table (npm package
  validation) and call `locate_ts`; `propose`, `prove` and `write_pr` are unchanged. An invalid
  combination is a named usage/config error, exit 2.
- **M13 — Tests.** Committed fixture repos: a basic ESM `.ts` repo, a quoted-key/object-variable
  repo, a CJS `.cjs` repo, a `.js`/`.mjs` repo, a `.tsx` repo, an alias/decoy repo, a dynamic
  import/computed member repo, and a no-SDK repo. The decoy proves zero unrooted certain sites; the
  real T1 spec pair produces the expected `Change`.
- **M14 — Dependencies.** Add `tree-sitter` and the two grammar packages to `pyproject.toml` with
  compatible ranges; `uv.lock` records the exact versions. The suite stays offline.

### Should have

- **S1 — `line_text`** on every TS site, as T2 does.
- **S2 — Operation mapping parity.** The same `tenon.toml` `[locate.operations]`/`[locate.fields]`
  tables work for TS; a mapping test with `POST /v1/charges = charges.create`.
- **S3 — CLI end-to-end.** `tenon check --language ts` on a fixture exits 1 with the site;
  `tenon fix --language ts --check "node --test"` proves a diff on a dependency-free JS fixture.
  (A real TS project with `node_modules` is documented, not proven; see Risks.)

### Nice to have

- **N1 — `.mts`/`.cts`** in discovery and the TypeScript grammar (included in M4; keep if free).
- **N2 — JSX attribute sites** when the component is SDK-rooted; explicitly out of this card unless
  the scanner makes it free.
- **N3 — `tenon.toml` `[locate] language`** already in M12; no separate flag in the config file.

## Data Model

```
TsLocateConfig
  sdk_package: str                  # npm package, e.g. "stripe" or "@scope/sdk"
  operations: Mapping[str, str]     # "POST /v1/charges" -> "charges.create"
  fields:     Mapping[str, str]     # "Charge.amount" -> "amount_cents"

QueryConfig (Protocol)              # query.py sees only these
  operations: Mapping[str, str]
  fields:     Mapping[str, str]

locate_ts(change, root, config) -> LocateResult
  certain:   tuple[Site, ...]        # the shipped Site
  ambiguous: tuple[AmbiguousGroup, ...]
  reason:    LocateReason | None
  to_json() -> str                   # byte-stable
```

The scanner reuses `Hit`, `Dynamic`, `DynamicKind`, `ScanResult` from `tenon.locate.scan`; the
resolver reuses `tenon.locate.resolve`. New vocabulary: only `TsLocateConfig` and the scanner
adapter. No new `SiteShape`, `AmbiguityReason` or `LocateReason` value.

## API Contract

```python
from tenon.locate import TsLocateConfig, locate_ts

config = TsLocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/charges": "charges.create"},
)
result = locate_ts(change, "path/to/repo", config)
result.certain    # Site(path="src/billing.ts", line=12, column=34, shape="keyword", ...)
result.ambiguous  # DYNAMIC_KWARGS / DYNAMIC_GETATTR / ALIAS_CHAIN / ...
result.reason     # None, or NO_SDK_IMPORT / NO_SITES / ...
```

CLI:

```sh
tenon check repo --old old.json --new new.json --language ts
tenon fix repo --old old.json --new new.json --language ts --check "node --test"
```

## Technical Considerations

- **tree-sitter, not Node.** The Python wheels parse TS/TSX/JS offline; no Node/tsc/npm runtime for
  analysis. Node is only the user's own check command, if they choose one. The grammar packages
  expose `language_typescript()`, `language_tsx()` and `language()`; the API was spiked with
  tree-sitter 0.26.0.
- **Reuse, not a fork.** `Hit`/`Dynamic`/`ScanResult` are language-neutral evidence; `resolve` is the
  one certainty policy. T6 adds a scanner that emits the evidence and a wrapper that calls the shared
  resolver. This keeps R8 (language sprawl) bounded: a new language is a scanner plus fixtures, not a
  new policy.
- **Columns.** tree-sitter points are 0-based rows and byte columns. Convert to 1-based character
  columns with the UTF-8 prefix rule T2 uses, so a non-ASCII line reports the same column a human
  sees.
- **Why reachability.** T2 only scans modules that reach the SDK. Without it, every unrelated
  `{ amount: 1 }` in a large app would become an `UNROOTED_RECEIVER` group. The reverse-edge BFS
  mirrors T2 and keeps the decoy honest.
- **Object variables are dynamic, not missed.** `create(payload)` has no literal key to report; the
  field may be inside. Emitting `STAR_KWARGS`/`DYNAMIC_KWARGS` is the honest answer. T2 does the same
  for `**kwargs`.
- **T3 compatibility.** The existing rename rule edits `keyword` (identifier at a column),
  `dict_key` (quoted string + quotes) and `attribute` (identifier); TS sites use the same spans. A
  `$`-prefixed JS identifier is a known boundary edge in T3's `_at_identifier`, not solved here.
- **T4 proof caveat.** `isolated_copy` skips `node_modules`; a TS check that needs it will fail the
  baseline in the copy. The CLI still reports `UNVERIFIED / TESTS_FAILED_BEFORE` honestly. A copy
  policy for JS dependencies is a follow-up; this card's JS proof fixture uses Node's built-in runner
  with no dependencies.
- **Parser errors.** A file that tree-sitter cannot parse is skipped, as T2 skips a Python
  `SyntaxError`; it is not reported as a site and does not fail the run.
- **Dependency weight.** Three wheels, no Node. The lockfile pins them; the OSS install stays
  `uv`-only.

## Risks & Open Questions

- **R4 (wrong location in dynamic code).** The import-rooted rule and the one-hop aliases bound it;
  dynamic imports, computed members, factory-returned clients and object variables become ambiguity,
  never certainty. The decoy fixture is the hard test.
- **R8 (language sprawl).** Each language is a scanner + fixtures behind the shared contract; the
  resolver is not duplicated. A future Go/Rust/C# locator follows the same shape.
- **tree-sitter API drift.** The Python bindings and grammar ABI move; pin compatible ranges and the
  lockfile. The spike used 0.26.0 / 0.23.2 / 0.25.0.
- **Native wheels.** macOS/Linux wheels are expected; a platform without one cannot install the
  package. The project targets macOS/Linux today; note it in the install docs.
- **Reachability misses.** `tsconfig` path aliases, package `exports`, and unresolved relative
  imports can hide a module. It is not scanned, so its sites are missed; `NO_SITES`/`NO_SDK_IMPORT`
  is the honest result. The fixture suite covers relative imports only.
- **`node_modules` in the proof copy.** A real TS project's `npm test` needs dependencies the copy
  drops. This card proves a dependency-free JS fixture; a T4 copy policy (symlink or keep
  `node_modules`) is the next integration card. Users can still `tenon check` any TS repo.
- **`$` identifiers.** T3's identifier boundary treats `$` as a non-identifier; a `$amount` key could
  be mis-edited. Rare in API payloads; a T3 follow-up if a real case appears.
- **JSX props.** Parsed but not reported as sites. A React SDK prop rename is a later mapping
  question, not a locator primitive.
- **Open question — should `import type` bindings count?** No: they are erased at runtime; a call
  through one is invalid code. If a real repo uses value imports with `import type`, tree-sitter
  sees the syntax and M5 ignores the type-only form.
- **Open question — TypeScript `as`/non-null wrappers.** Unwrap them to the inner chain; a wrapper
  does not change runtime rootedness. Settle in the scanner spec.

## Out of Scope

- Type inference, the TypeScript type checker, `tsserver`, `tsc`, or Node-based analysis.
- `tsconfig` `paths`, package `exports`, monorepo/workspace resolution.
- JSX attribute sites; decorators that rewrite calls; raw HTTP without an SDK import.
- New proposer rules or edits for TS-specific syntax.
- T4's copy policy for `node_modules`; T7 proof levels; T8 probe/MCP; T9 benchmark.
- Watch mode, incremental parsing, or caching.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `ts-scan` | File discovery, grammar selection, import bindings, reachability, one-hop aliases, `Hit`/`Dynamic` emission, columns, parse-error skipping. No resolver, no config file. |
| `ts-locate` | `TsLocateConfig`, `QueryConfig` protocol, `locate_ts` wrapper over `derive` + shared `resolve`, fixtures and the decoy. No CLI. |
| `ts-cli` | `--language`, `[locate] language`, TS config branch, `check`/`fix` dispatch, dependency-free JS end-to-end. No new proof logic. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | One language is covered; the second ecosystem is unreachable. |
| User understanding | 🟡 | Developer/CI personas are clear; no real TS repo has run yet. |
| Success metrics | 🟢 | Same contract, decoy zero-certain, offline fixtures, byte-stable JSON. |
| Scope clarity | 🟢 | Engine + CLI flag; type inference, JSX props, tsconfig aliases and T4 node_modules excluded. |
| Edge cases & risks | 🟡 | node_modules proof gap and path-alias misses are real, documented, not solved. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | tree-sitter spiked; T2's evidence and resolver are reusable. |
| Go-to-market | 🟢 | Doubles the addressable OSS audience without a Node runtime. |

**Areas to strengthen before sharing:** the `node_modules` proof gap means T6 is fully useful for
`tenon check` but only partially for `tenon fix` on a real TS project. The path-alias reachability
miss is the other honest limit.

**The question I would want answered before greenlighting this:** *If a real TS repo imports its SDK
through a `tsconfig` alias or a workspace package, the scanner may see no SDK import and report
`NO_SDK_IMPORT` on every change. Is that acceptable for the first TS card, or must alias resolution
ship with it?* The answer this card records: relative imports only for now; a real case can force the
alias follow-up, and the named reason tells the user why rather than silently finding nothing.
