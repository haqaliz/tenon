# PRD: Python call-site locator (T2 — locate)

- **Slug:** `python-call-site-locator`
- **Capability:** T2 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M0.2 in `docs/ROADMAP.md` (Phase 0)
- **Status:** draft, awaiting review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1 (`src/tenon/detect/`, shipped 2026-10-26) can say *what* a vendor broke. Nothing can say
*where* it hurts. Without a locator there is no patch target, so T3, T4 and T5 have nothing to
operate on, and the Phase 0 gate in `docs/ROADMAP.md` — one real API change, one real repo, one
patch that passes a real check — cannot be reached.

The gap is not textual search. A T1 record speaks HTTP: `Change.location` carries a JSON pointer,
an HTTP method and a path, and `before`/`after` carry spec payloads (`src/tenon/detect/record.py`).
The code speaks Python: `client.charges.create(amount=100)`. Nothing in the record names that
symbol, and the path `/v1/charges/{id}` appears in no source file. Bridging that gap by guessing
is the one failure mode that would make Tenon indistinguishable from a plausible-patch bot: a
confident wrong line, patched, with a green test that never exercises it.

**For whom:** T3 (propose) as the primary consumer, then T4 (prove) and the developer reading a
`tenon check` report in M1.4. This card has no end-user surface of its own.

## Goals & Success Metrics

1. **Located, not guessed.** Given a `Change` and a repository root, return call sites with
   `file`, `line`, `column` and a `certain` / `ambiguous` verdict. A site is `certain` only when
   the call chain is rooted in an import binding of the configured SDK package.
2. **Ambiguity is first-class.** `**kwargs`, `getattr`, unresolved aliases, unrooted receivers and
   multi-candidate matches are returned as ambiguous groups *with their candidate sites* — never
   dropped and never resolved.
3. **Named non-results.** A change the locator cannot or did not analyze returns a named reason,
   so a caller can tell "no sites" from "not attempted" from "unsupported kind".
4. **Determinism.** Same repository, same `Change`, same config → byte-identical JSON, ordered by
   `(path, line, column)`.
5. **Offline.** No network, no model calls, no language server. Stdlib `ast` only.

**Thresholds, on the committed fixture suite:** 100% of labelled call sites in each fixture repo are
reported (no silent misses), and **zero** certain sites are unrooted — the decoy fixture exists to
make that a hard number, not an intention. Real-repo recall is *not* measurable here and is claimed
only after M0.3; see Risks.

Measured by committed fixture repositories in `tests/`, not by opinion.

## User Personas & Scenarios

- **T3 propose.** "For this removed field, give me the exact lines I may rewrite, and tell me which
  ones you are unsure about so I can decline them." Takes only `certain` sites for mechanical
  fixes; `ambiguous` sites become flagged suggestions.
- **T4 prove.** Needs the site list to know which tests *should* be affected, and needs the reason
  codes to report `AMBIGUOUS_CALL_SITE` honestly instead of a green run that proved nothing.
- **Developer (M1.4).** Needs stable ordering and a reviewable report.

Scenario, end to end: a vendor renames schema property `amount` to `amount_cents`. T1 emits
`renamed` with `before: "amount"`, `after: "amount_cents"` under the `Charge` schema. T2 finds
`client.charges.create(amount=100)` at `billing.py:42:25` as certain, and a
`build_payload(**row)` at `import_job.py:17:5` as ambiguous (`DYNAMIC_KWARGS`). T3 rewrites the
first and flags the second.

## Requirements

### Must have

- **M1 — Change consumption.** `locate(change, root, config)` accepts a `Change` from
  `tenon.detect` and derives a *query* from it: the operation scope (`location.method` + `path`
  when present), the old name to search for, and the new name when the record is an inferred
  rename. No re-reading of the OpenAPI document: the record is the unit
  (`docs/technical/ARCHITECTURE.md`).
- **M2 — Kinds analyzed.** `endpoint_removed`, `endpoint_added`, `renamed`, `property_removed`,
  `property_added`, `property_required_added`, `property_type_changed`, `parameter_removed`,
  `parameter_required_added`, `parameter_type_changed`. Every other kind returns an empty result
  with reason `UNSUPPORTED_CHANGE_KIND` — not a silent empty list.
- **M3 — Symbol contract.** Configuration names the SDK package and carries an optional mapping
  from `"METHOD /path"` to a dotted Python method path, and from `"Schema.field"` to the Python
  keyword name. Without a mapping entry, infer candidates from the path's resource segments, the
  HTTP verb (`get`→`get`/`retrieve`/`list`, `post`→`create`, `put`/`patch`→`update`,
  `delete`→`delete`) and the field name. Inference may produce several candidates; more than one
  candidate that resolves in the repo is ambiguous, never a pick. **`operationId` is not available
  in a T1 record**, so the mapping key is method+path, not operationId.
- **M4 — SDK-rooted scanning.** Parse modules that reach the configured SDK package through
  imports; a file with no path to the SDK is not scanned. Within a file, track simple alias
  bindings (`client = Stripe(...)`, `c = stripe.Stripe(...)`) one hop deep. An attribute chain or
  keyword argument is SDK-rooted only when its root name is an SDK import or such an alias.
- **M5 — Site shapes.** Report four shapes: method call (`client.charges.delete(...)`), keyword
  argument (`...create(amount=...)`), dict key inside an SDK call (`...create({"amount": ...})`),
  and attribute access (`response.amount`). Attribute access is certain only when the receiver is
  an SDK-imported class; otherwise ambiguous.
- **M6 — Ambiguity reasons.** Ambiguous groups carry one reason each: `DYNAMIC_KWARGS`,
  `DYNAMIC_GETATTR`, `ALIAS_CHAIN`, `UNROOTED_RECEIVER`, `MULTIPLE_CANDIDATES`, `UNMAPPED_SYMBOL`.
  Each group keeps its candidate sites.
- **M7 — Result reasons.** `LocateResult.reason` is set only when `certain` and `ambiguous` are
  both empty: `UNSUPPORTED_CHANGE_KIND`, `NO_SDK_IMPORT` (no module reaches the package),
  `OPERATION_NOT_MAPPED` (endpoint scope with no mapping and no inferred symbol),
  `NO_SITES` (analyzed, nothing matched). `NO_SITES` and `UNSUPPORTED_CHANGE_KIND` must be
  distinguishable by the caller.
- **M8 — Canonical order and serialization.** Sites sorted by `(relative_path, line, column)`; JSON
  byte-stable via `sort_keys` and no set iteration, matching `DiffResult`'s contract.
- **M9 — No mutation.** Locating reads the repository; it never writes, imports or executes the
  scanned code.

### Should have

- **S1 — Config from `tenon.toml`.** `[locate] sdk_package`, `[locate.operations]`,
  `[locate.fields]` parsed with stdlib `tomllib`. The in-memory `LocateConfig` is the API; the file
  is a convenience. Shipped only if it stays under ~40 lines including tests.
- **S2 — Reason for every kind reached.** A table test asserting each of the 13 T1 kinds either
  produces sites or a named reason — no third outcome.

### Nice to have

- **N1 — `line_text` on a site**, for report rendering and human review. Free from the parsed
  source; skipped if it complicates serialization.

## Data Model

```
LocateConfig
  sdk_package: str                      # import root, e.g. "stripe"
  operations: Mapping[str, str]         # "DELETE /v1/charges/{id}" -> "charges.delete"
  fields:     Mapping[str, str]         # "Charge.amount" -> "amount_cents"

Site
  path:   str                           # repo-relative, forward slashes
  line:   int                           # 1-based
  column: int                           # 1-based, of the offending name/node
  shape:  "call" | "keyword" | "dict_key" | "attribute"
  symbol: str                           # the Python name matched, e.g. "amount"
  line_text: str | None                 # N1

AmbiguousGroup
  reason: Reason
  symbol: str
  candidates: tuple[Site, ...]

LocateResult
  change:   Change                      # the record this answers, unchanged
  certain:  tuple[Site, ...]
  ambiguous: tuple[AmbiguousGroup, ...]
  reason:   LocateReason | None         # set only when both lists are empty
  to_json() -> str                      # byte-stable
```

Deliberately absent: a confidence score, a proposed replacement, a chosen candidate. T2 answers
"where", never "which is right". A numeric score invites filtering; two lists do not.

## API Contract

```python
from tenon.detect import diff, load
from tenon.locate import LocateConfig, LocateResult, locate

result: LocateResult = locate(change, "path/to/repo", LocateConfig(sdk_package="stripe"))
result.certain      # tuple[Site, ...]
result.ambiguous    # tuple[AmbiguousGroup, ...]
result.reason       # LocateReason | None
result.to_json()    # str, byte-stable
```

No CLI, no exit codes, no patch text. Those are M1.4 and T3.

## Technical Considerations

- **Stdlib only.** `ast`, `pathlib`, `tomllib`. No tree-sitter, no Jedi, no language server: T2
  needs name+line, not type inference. A TypeScript locator (T6) gets its own package behind the
  same result contract.
- **Two passes per file.** Pass one: collect import bindings and one-hop aliases. Pass two: visit
  calls, keywords, dict keys and attribute access, classifying as it goes. Single file, no
  cross-file aliasing — a repo-wide symbol table is a type checker, and this card is not one.
- **Import reachability** is computed cheaply: every `.py` file's import statements are parsed,
  then only files that (transitively) import the SDK package are fully scanned. Transitive
  resolution of *local* imports is best-effort; an unresolved local import means the module is
  scanned anyway (recall over speed) and the site classification still decides certainty.
- **`Change.before` is not uniform.** For `property_removed` it is a rendered dict
  `{"name", "type", "format"}`; for endpoint kinds it is a path string; for `renamed` it is the
  old name string. The query derivation must handle these shapes explicitly and refuse anything
  else with `UNSUPPORTED_CHANGE_KIND` rather than `AttributeError`.
- **Operation scope.** T1 sets `location.method`/`path` for operation-level changes and leaves them
  `None` for component-schema changes (`_record_location` in `src/tenon/detect/diff.py`). That
  distinction decides whether a field hit can be narrowed to one operation or must be reported
  with `UNMAPPED_SYMBOL` when it appears in several.
- **`AMBIGUOUS_CALL_SITE`** is the aggregate cause T4/T5 report per
  `docs/technical/ARCHITECTURE.md`. T2 emits the finer reasons above; the mapping from a group to
  that aggregate cause is a one-liner, not a new vocabulary.

## Risks & Open Questions

- **R4 (`docs/ROADMAP.md`) — wrong location in dynamic code.** The import-rooted rule bounds it;
  it does not eliminate it (`exec`, framework routing, dynamically built clients). Mitigation: any
  construct the visitor cannot see through becomes an ambiguous group, and a decoy fixture proves
  an unrelated `amount=` in a non-SDK module is never certain.
- **R8 — language sprawl.** T6/T11 reuse this contract. Mitigation: `locate/` holds the result type
  and the Python implementation in separate modules, so the contract is not re-invented per
  language.
- **Highest new risk — the symbol contract is wrong for real SDKs.** For a hand-rolled `requests`
  client there is no SDK package to root on, and for a generated SDK the method names may not
  follow the path. Mitigation: explicit mapping exists for exactly this, and M0.3 will reveal how
  often it is required. If it is required for every endpoint, inference is worthless and this PRD's
  M3 should be revisited before T3.
- **Scope assumption — an SDK, not raw HTTP.** `LocateConfig.sdk_package` presumes the repo calls a
  client library (`stripe.charges.create(...)`), not `requests.delete(f"{base}/v1/charges/{id}")`.
  A raw-HTTP repo has no import root and would yield `NO_SDK_IMPORT` on every change. This is the
  single assumption that could make M0.3 fail after T2 lands; it is listed as out of scope and as
  the gate question below rather than silently half-built.
- **Open question — what does a `parameter_required_added` site look like?** The new parameter has
  no old name to search. Current intent: locate calls to the enclosing operation (via M3), then
  report those calls as candidates, since the fix is "add the argument here" rather than "rename
  this name". Confirm during aspect design.
- **Open question — component-schema changes with no operation scope.** A renamed property on a
  shared model can be hit through any endpoint. Current intent: report the name hits that are
  SDK-rooted and mark all others ambiguous; do not attempt to enumerate the endpoints.

## Out of Scope

- Proposing or applying patches (T3).
- Running tests or assigning proof levels (T4).
- PR creation (T5).
- TypeScript/JavaScript location (T6), MCP diffs and probe mode (T8).
- CLI, exit codes, JSON output surface (`tenon check`, M1.4).
- **Raw HTTP call sites** — `requests`/`httpx` calls with path literals or f-strings and no SDK
  import root. A repo like that gets `NO_SDK_IMPORT`, which is honest but empty. Follow-on card if
  M0.3's real repo needs it.
- Dataflow or taint analysis: we do not follow a value from a dict key through three functions.
- Resolving the SDK's own source; only the user's repository is parsed.
- Judging whether a site *should* change.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `locate-result` | `Site`, `AmbiguousGroup`, `LocateResult`, `LocateConfig` (in-memory + optional TOML), reason enums, canonical ordering and byte-stable JSON. No scanning, no query derivation. |
| `symbol-contract` | `Change` → query: scope detection, old/new name extraction per kind, explicit mapping lookup, inference from path segments and HTTP verb, `UNSUPPORTED_CHANGE_KIND` / `OPERATION_NOT_MAPPED`. Pure, no filesystem. |
| `python-scan` | Import reachability, one-hop alias table, `ast` visitor for the four site shapes, SDK-rooted classification, file/line/column. No reason policy beyond "rooted or not". |
| `ambiguity-policy` | Turning scan hits + query into `certain` vs `ambiguous` groups with a reason each; multi-candidate rule; the decoy fixture proving an unrooted match is never certain. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Grounded in T1's actual record shape (`record.py`), not a generic story. |
| User understanding | 🟢 | Internal consumers named (T3, T4, M1.4), each with a concrete need. |
| Success metrics | 🟢 | Now numeric: 100% labelled-site recall on fixtures, zero unrooted certain hits. |
| Scope clarity | 🟢 | M1-M9, explicit out-of-scope, and the raw-HTTP boundary called out. |
| Edge cases & risks | 🟡 | `parameter_required_added` and component-scoped renames still have "current intent" rather than a settled answer; resolve in aspect specs. |
| Stakeholder alignment | 🟡 | Solo project: the reviewer is the gate. No external stakeholder to align. |
| Feasibility | 🟡 | Roughly one card across four aspects; no estimate of scanned-repo size. Assumed acceptable for M0.2. |
| Go-to-market | — | Internal capability; no rollout. |

**The question I would want answered before greenlighting this:** *If the first real repo for M0.3
calls the API over raw `requests`/`httpx` with inline paths, this locator returns `NO_SDK_IMPORT`
on every change and the gate fails. Is that an acceptable Phase 0 risk, or should T2 also locate
raw-HTTP call sites?* The card as specified bets on an SDK-shaped repo; that bet is the largest
unknown here.

**Areas to strengthen before sharing:** none blocking. The two "current intent" items are settled
in the `symbol-contract` and `ambiguity-policy` aspects.
