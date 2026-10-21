# Tenon: Capability Roadmap

Engine capabilities in build order. Each lands test-first. Nothing is built yet.

| ID | Capability | Depends on | Guardrail tie-in |
|---|---|---|---|
| **T1** | **Change detection.** Diff two OpenAPI versions into typed change records. | none | Machine-readable sources first |
| **T2** | **Call-site location (Python).** Find usages of a changed symbol or endpoint with file and line. | T1 | Ambiguity reported, never guessed |
| **T3** | **Patch proposer seam.** Rule-based proposer for mechanical changes; optional BYOK model proposer. | T1, T2 | A model proposes only |
| **T4** | **Proof runner.** Apply the patch in an isolated working copy, run the user's tests, record the proof level. | T3 | Execution decides the label |
| **T5** | **PR writer.** Branch and PR stating the proof level; never pushes to the default branch. | T4 | No merging |
| **T6** | **TypeScript/JavaScript locator.** Same contract as T2. | T1 | |
| **T7** | **Proof ladder.** Types/build-only, characterization tests, recorded-call replay. | T4 | Weak proof labelled weak |
| **T8** | **MCP diffs and probe mode.** Diff MCP tool schemas; run an agent against an API or server. | T1, T4 | |
| **T9** | **Benchmark and history.** Labelled (change, patch, proof, outcome) corpus. | T4, T5 | Measure against human outcomes |
| **T10** | **Provider layer and GitHub App (hosted).** Vendor-pushed migrations. | T4-T9 | Opt-in, BYOK |
| **T11** | **More languages.** Go, Rust, C#. | T2 pattern | One at a time |

## Sequencing

T1 and T2 first, then T3-T5 give the first end-to-end PR. T6-T8 widen reach and proof depth. T9
makes the result publishable. T10 is the business and is deferred.

## Open questions

- Which vendor and SDK is the first real case? Pick one that publishes OpenAPI and has a public
  changelog of breaking changes.
- How to handle changes with no machine-readable source (changelog only)? Likely flag, not patch.
