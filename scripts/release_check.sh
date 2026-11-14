#!/usr/bin/env bash
# Local release check: tests, build, and a clean-venv install of the wheel.
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="0.2.0"

uv sync --frozen
uv run pytest
uv run tenon --version | grep -qx "tenon ${VERSION}"

rm -rf dist
uv build

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
uv venv "$tmp/venv"
uv pip install --python "$tmp/venv/bin/python" --quiet dist/tenonhq-*.whl
"$tmp/venv/bin/tenon" --version | grep -qx "tenon ${VERSION}"
"$tmp/venv/bin/tenon" check --help >/dev/null

echo "release check ok: tenon ${VERSION}"
