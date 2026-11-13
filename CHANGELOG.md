# Changelog

All notable changes to Tenon are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Versions before 1.0 make no API-stability
promise: flags, config keys and provider contracts may still change.

## [Unreleased]

### Added

- **Typed-function receiver inference (T12c):** a same-file function/method with an annotated SDK
  return type roots the receiver assigned from its call in all five languages
  (`def make_client() -> stripe.Client`, `fn make_client() -> Client`, `func newClient() *stripe.Client`,
  `StripeClient MakeClient()`, `function makeClient(): StripeClient`). Only a written annotation is
  evidence; unannotated, wrong-return and cross-file helpers stay unrooted.
- **Webhook-triggered runs:** `tenon provider serve --trigger EVENT[.ACTION]=BUNDLE` maps a verified
  GitHub delivery to a registered bundle and queues the normal installed fan-out with the delivery id
  as the idempotency key. A trigger requires the webhook secret; the mapping is operator CLI config,
  not bundle content, so a bundle cannot auto-run itself.

## [0.1.0] - 2026-11-13

The first tagged release: change detection, five locators, the proof ladder, the PR writer, the
provider layer, a deployable service and receiver tracking. 2,527 tests, all offline.

### Added

- **Core (T1–T7):** OpenAPI 3.x change detection (renames, removals, required/type changes); Python
  `ast` and TypeScript/JavaScript tree-sitter call-site location with named ambiguity groups;
  candidate diffs that are never applied to the checkout; the proof ladder
  (`TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`, `UNVERIFIED`) with explicit
  causes; a deterministic PR writer with dirty-tree/default-branch/branch-exists/required-level
  refusals and no merge path; `tenon check`/`tenon fix`, `tenon.toml`, byte-stable JSON and honest
  exit codes.
- **MCP, probe and benchmark (T8/T9):** MCP `tools/list` schema diffs, the Python `call_tool`
  locator, `tenon probe` over stdio with a user-supplied agent, and the `tenon corpus`
  `(change, patch, proof, outcome)` benchmark with a merge rate only where real outcomes exist.
- **Provider layer (T10a–T10e):** a GitHub App remote (installation token, credential-helper push,
  PR creation) alongside `gh`; a portable JSON migration bundle and `tenon provider migrate`; local
  multi-repo fan-out over a repos file; installed fan-out over the app installation's repositories
  with temp clones; a self-hosted service (`POST /runs`, run/report status, SQLite, bearer auth,
  HMAC-verified webhooks, one worker, readiness).
- **Deployment and resilience (T13a/T13b):** a non-root multi-stage Docker image, Compose + Caddy
  automatic HTTPS, read-only bundles/secrets, DB volume, non-root runtime, `GET /ready`,
  `--workers`, infrastructure-only retries, queued/running cancel with process-group termination,
  bearer-guarded Prometheus `/metrics`, startup recovery and SQLite WAL/busy-timeout hardening.
- **Languages (T11a–T11c):** Rust, Go and C# locators on the shared certainty policy, with
  associated calls, struct/composite/object initializers, field access, imports, aliases and
  package/namespace inference.
- **Receiver tracking (T12a/T12b):** explicit receiver evidence (construction/annotation or a
  `receivers`/`--receiver` factory mapping) roots `client.resource.method` as
  `Type.resource.method` in all five languages; the shared policy decides certainty.
- **Release:** `CHANGELOG.md`, a runnable `examples/quickstart`, a release checklist and a local
  build/install check.

### Changed

- `tenon provider migrate` runs the shipped `fix` pipeline; the provider JSON envelope wraps the fix
  results without changing the fix envelope.
- `receivers` is available in every OpenAPI language config, `tenon.toml`, a bundle's
  `locate.receivers` and `--receiver KEY=VALUE`; flags override config.
- `--language` accepts `rust`, `go` and `csharp`; `--package-name` covers Go's root package clause;
  `--language`/`source=mcp` remains Python-only.
- The service runs the installed fan-out as one CLI subprocess per run, so the pipeline stays one
  code path.

### Fixed

- The GitHub App push passes the credential helper as `credential.helper=...`, a valid git config
  (previously a bare value was rejected by real git).
- Provider bundles accept the documented `check` key, with `command` kept as a `tenon.toml` alias.
- A Rust/Go receiver field that is evidence on two chains is listed once, not twice.
- A service run stores the CLI's `--json` error message (previously an exit 2 could leave the error
  empty), and the worker resolves a run's bundle name to the confined path before invoking the CLI.
- Discovered installation repos and temp clones are cleaned up on success and failure.

### Known limits

- The service is self-hosted (Compose + Caddy); there is no cloud deployment, Postgres, web UI,
  multi-tenant auth or webhook-triggered run. Rate limiting is the proxy's job.
- Retries cover infrastructure failures only; a run that produced a report is terminal. A timed-out
  run may already have opened PRs, so its retry reports per-repo `BRANCH_EXISTS` refusals and never
  force-pushes or deletes.
- Receiver tracking needs explicit evidence (a visible construction/annotation or a configured
  factory); method/fluent chains on an untracked value, `dynamic`/`getattr`, macros, re-exports and
  return-type/interprocedural inference are not followed.
- A mapped field spelling locates the site, but `fix` only edits when the located spelling equals the
  spec's old name; otherwise it reports `NO_EDITABLE_SITES`.
- No merge, no default-branch push, no force-push, no provider branding in the PR body. Windows is
  not a target. No PyPI publication yet.
