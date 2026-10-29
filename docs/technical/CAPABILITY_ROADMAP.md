# Tenon: Capability Roadmap

Engine capabilities in build order. Each lands test-first.

| ID | Capability | Depends on | Guardrail tie-in | State |
|---|---|---|---|---|
| **T1** | **Change detection.** Diff two OpenAPI versions into typed change records. | none | Machine-readable sources first | **Shipped 2026-10-26** |
| **T2** | **Call-site location (Python).** Find usages of a changed symbol or endpoint with file and line. | T1 | Ambiguity reported, never guessed | **Shipped 2026-10-29** |
| **T3** | **Patch proposer seam.** Rule-based proposer for mechanical changes; optional BYOK model proposer. | T1, T2 | A model proposes only | **Shipped 2026-10-29** |
| **T4** | **Proof runner.** Apply the patch in an isolated working copy, run the user's tests, record the proof level. | T3 | Execution decides the label | Not started |
| **T5** | **PR writer.** Branch and PR stating the proof level; never pushes to the default branch. | T4 | No merging | Not started |
| **T6** | **TypeScript/JavaScript locator.** Same contract as T2. | T1 | | Not started |
| **T7** | **Proof ladder.** Types/build-only, characterization tests, recorded-call replay. | T4 | Weak proof labelled weak | Not started |
| **T8** | **MCP diffs and probe mode.** Diff MCP tool schemas; run an agent against an API or server. | T1, T4 | | Not started |
| **T9** | **Benchmark and history.** Labelled (change, patch, proof, outcome) corpus. | T4, T5 | Measure against human outcomes | Not started |
| **T10** | **Provider layer and GitHub App (hosted).** Vendor-pushed migrations. | T4-T9 | Opt-in, BYOK | Not started |
| **T11** | **More languages.** Go, Rust, C#. | T2 pattern | One at a time | Not started |

### T1 as shipped (2026-10-26)

`src/tenon/detect/`: `load`/`parse` (OpenAPI 3.0.x/3.1.x, YAML or JSON, local `$ref` resolution),
`diff` producing 13 typed record kinds with `breaking` and `confidence`, and rename inference that
pairs only unambiguous removed/added records. Bad input is a named refusal with a JSON pointer.
136 tests, offline and deterministic.

Known limits at this level: recursive schemas are refused (fail-closed); added optional *parameters*
produce no record (no `parameter_added` kind); request-body/media-type/response add-remove and
`additionalProperties` are not walked; no real vendor spec pair is committed yet.

## Sequencing

T1 and T2 first, then T3-T5 give the first end-to-end PR. T6-T8 widen reach and proof depth. T9
makes the result publishable. T10 is the business and is deferred.

### T2 as built (2026-10-28)

`src/tenon/locate/`: `change → query` (explicit `METHOD /path` and `Schema.field` mappings, then
inference from path segments and HTTP verb), an `ast` scan of modules that reach the configured SDK
package (one-hop aliases, character-precise file/line/column), and a single certainty policy that
returns `certain` sites plus ambiguity groups with named reasons (`DYNAMIC_KWARGS`,
`DYNAMIC_GETATTR`, `ALIAS_CHAIN`, `UNROOTED_RECEIVER`, `MULTIPLE_CANDIDATES`, `UNMAPPED_SYMBOL`).
207 tests, offline and deterministic.

Known limits at this level: an SDK-shaped repo is assumed (a raw `requests`/`httpx` client yields
`NO_SDK_IMPORT`); aliases resolve one hop past an assignment-created alias; operation-scoped field
changes report only the resolved call's arguments; `AMBIGUOUS_CALL_SITE` is the aggregate cause T4
will report, not a T2 output.

### T3 as built (2026-10-29)

`src/tenon/propose/`: a `Proposal` contract, a deterministic `RuleProposer` for field renames, and
an assembly that verifies every candidate span against the current source before applying it in
memory and rendering a unified diff. Ambiguous sites, uneditable call sites and stale spans become
skipped suggestions with named reasons; a proposal carries `NO_RULE`, `NO_CERTAIN_SITES`,
`NO_EDITABLE_SITES` or `STALE_SITE` when nothing survives. 114 tests, offline and deterministic.

Known limits at this level: one rule only (field rename, `keyword`/`dict_key`/`attribute` shapes);
removals, required additions, type changes and endpoint renames have no mechanical fix; a
proposer seam exists but no model ships; nothing is applied, so every proposal is unverified until
T4; a file without a final newline produces a diff `git apply` will reject (documented shortcut).



## Open questions

- Which vendor and SDK is the first real case? Pick one that publishes OpenAPI and has a public
  changelog of breaking changes.
- How to handle changes with no machine-readable source (changelog only)? Likely flag, not patch.
