# Phase A — Diagrams & proposal PDFs

## 1. Diagrams (`excalidraw`)

Typical set for Tenon:

| Diagram | When to include |
|---|---|
| System / architecture | Almost always — where the change lives in detect → locate → propose → prove → PR |
| Data flow | A spec diff moves to a change record to a located call site |
| Sequence | Change detection, patch proposal, proof run, PR |
| State machine | A proof-level transition (`TESTS_PASSED`/`CHARACTERIZED`/`REPLAYED`/`TYPES_BUILD_ONLY`/`UNVERIFIED`) |

**Every text element must set `fontFamily: 2` (Helvetica).**

**Diagram the proof contract honestly.** Never draw a model's proposed patch as
already "verified" — only a passed check does that.

## 2. Export to SVG (`excalidraw-to-svg`)

## 3. Write the two proposals

### `<type>-<id>-technical-proposal.md`

Summary, current state, proposed design, data/interface changes (change-record
schema, proof contract, PR format), risks/trade-offs, effort/sequencing
(reference the `T`-capability), open questions.

### `<type>-<id>-non-technical-proposal.md`

The problem in plain language, what we'll do, why it matters (developers whose
integrations silently break), what changes for users, timeline, risks. Don't
imply a PR is safe beyond the proof level it reached.

## 4. Convert to PDF (`md-to-pdf`)

```bash
cd docs/planning/{slug}/proposals
PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  md-to-pdf <type>-<id>-technical-proposal.md --basedir ..
PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  md-to-pdf <type>-<id>-non-technical-proposal.md --basedir ..
```

Verify: `pdftoppm -png -r 70 -f 1 -l 1 <type>-<id>-technical-proposal.pdf /tmp/check`

## 5. Approval gate

Present both PDFs and stop.
