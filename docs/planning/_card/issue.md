# Card: feat/provider-bundle

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer and GitHub App (hosted)** — second slice: **provider migration
  bundle** (`docs/technical/CAPABILITY_ROADMAP.md:16`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), second slice
- **Branch:** `feat/provider-bundle/aliz`
- **Worktree:** `.claude/worktrees/feat-provider-bundle`

## Brief

T10a gives the hosted writer an app identity. A provider still needs a portable way to describe a
migration: which vendor and release, which OpenAPI/MCP documents, how to map the vendor's operations
and fields to the customer's SDK, and what proof level the customer's repo must reach.

T10b adds a **migration bundle** (JSON) and `tenon provider migrate <repo> --bundle PATH`:
- the bundle carries `provider`, `migration`, `source` (openapi/mcp), `language`, `old`/`new` spec
  paths relative to the bundle, the locate config (`sdk_package`, `operations`, `fields`), the proof
  requirement and the stage commands;
- the command runs the shipped detect → locate → propose → prove pipeline on one target repo, prints
  the same fix report with provider/migration identity, and with `--open-pr` opens the PR through
  `gh` or the T10a app remote;
- one repo per invocation. Multi-repo/installed fan-out, webhooks and the hosted service are T10c.

The hard rules do not change: the bundle is untrusted input and is validated by name; the pipeline
and T5 guardrails are unchanged; no merge/default branch/force; the provider identity is metadata,
not a proof upgrade; no service or database in this slice.

## Constraints carried in from the repo

- `CLAUDE.md` §1–5: execution decides, honest levels, no merge/default branch, no egress by default.
- T5's `write_pr` and T10a's `GitHubAppRemote` are the writer paths; this card adds no new host.
- `src/tenon/cli/config.py`'s `CliConfig` is the in-memory contract; the bundle maps to it.
- The CLI `check`/`fix` behavior and exit codes stay as they are.
- Offline tests: fixture repos/specs/bundles; no network, no live GitHub.

## Scope fence

Not this card: multi-repo/installed fan-out, webhook/installation discovery, a hosted service or
database, provider branding in the PR body, T11 languages.
