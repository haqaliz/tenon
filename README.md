# Tenon

**Keeps your code fitted to the APIs it depends on.** Detects breaking API changes, patches the
affected calls, and proves the fix against your own checks before it opens a pull request.

[![Status](https://img.shields.io/badge/status-T2%20built%20·%20detect%20%2B%20locate-yellow)](docs/ROADMAP.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[Vision](VISION.md) · [Roadmap](docs/ROADMAP.md) · [Architecture](docs/technical/ARCHITECTURE.md) · [Capabilities](docs/technical/CAPABILITY_ROADMAP.md)

---

## Status

**T1 (change detection) and T2 (Python call-site location) are built.** `src/tenon/detect/` diffs
two OpenAPI 3.x documents into typed `Change` records; `src/tenon/locate/` turns one of those records
into call sites with file, line and column, and keeps anything it cannot prove in a separate
ambiguity list. Both run fully offline. Propose, prove and PR do not exist yet. Read `CLAUDE.md`
before writing any code here.

```python
from tenon.detect import diff, load
from tenon.locate import LocateConfig, locate

changes = diff(load("v1.yaml"), load("v2.yaml")).changes
for change in changes:
    result = locate(change, "path/to/repo", LocateConfig(sdk_package="stripe"))
    result.certain    # sites we can point at
    result.ambiguous  # groups with candidates and a named reason
    result.reason     # why there is nothing, when there is nothing
```

`uv run pytest` — no network, no model calls.

## What Tenon is

Two modes sharing one run-and-verify core:

- **Upgrade (lead):** a vendor changes an API. Tenon reads the change from a machine-readable
  source (OpenAPI diff first), finds the affected calls in your repo, proposes a patch, and runs
  your checks. The PR says which proof level it reached.
- **Probe (second):** point Tenon at an API or MCP server and it runs an agent against it to see
  whether agents can actually use it.

## Proof levels

| Level | Meaning |
|---|---|
| `TESTS_PASSED` | Your tests pass after the patch |
| `CHARACTERIZED` | Generated tests of current behavior still pass |
| `REPLAYED` | Recorded calls replay against the new shape |
| `TYPES_BUILD_ONLY` | Types and build pass, nothing more (weak, labelled) |
| `UNVERIFIED` | No acceptable proof ran |

You choose the level you require. A model may propose the patch; running the checks decides the label.

## Scope

Languages in order: Python, TypeScript/JavaScript, then Go, Rust, C#. Change sources: OpenAPI,
MCP schemas, SDK metadata. Consumer side first, provider side later.

## Docs

- [`VISION.md`](VISION.md)
- [`CLAUDE.md`](CLAUDE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md)
- [`docs/technical/ARCHITECTURE.md`](docs/technical/ARCHITECTURE.md)

## Lineage

One of three siblings scaffolded on 2026-10-22 with [Assay](../assay) and [Pry](../pry), sharing
house DNA with [Belay](../belay) and [Plumb](../plumb). Standalone by design.
