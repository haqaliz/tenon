# Releasing Tenon

The release is a local build/install check, a merge, an annotated tag and a GitHub release. No PyPI
publication in 0.2.0.

## Prerequisites

- `uv`, Python 3.11+, `git`, `gh` (for the GitHub release), and a clean `master`.
- The version in `pyproject.toml` (and `uv.lock`) is the release version; `CHANGELOG.md` has the
  `## [x.y.z] - YYYY-MM-DD` section.

## Checklist

1. **Full suite (offline).**

   ```sh
   uv sync --frozen
   uv run pytest
   ```

2. **Version.** The source run shows the installed metadata; re-sync after a bump.

   ```sh
   uv sync
   uv run tenon --version        # tenon 0.2.0
   ```

3. **Changelog.** The release body is the section under `## [0.2.0]`; review it for the shipped
   capabilities and the known limits.

4. **Build and clean-install smoke.**

   ```sh
   uv build
   tmp=$(mktemp -d)
   uv venv "$tmp/venv"
   uv pip install --python "$tmp/venv/bin/python" --quiet dist/tenonhq-0.2.0-py3-none-any.whl
   "$tmp/venv/bin/tenon" --version        # tenon 0.2.0
   "$tmp/venv/bin/tenon" check --help
   rm -rf "$tmp"
   ```

   `scripts/release_check.sh` runs the suite, build and smoke in one go.

5. **Merge the release PR** and update `master`.

   ```sh
   git checkout master
   git pull --ff-only origin master
   ```

6. **Tag the merge commit** (annotated; push the tag).

   ```sh
   git tag -a v0.2.0 -m "Tenon v0.2.0"
   git push origin v0.2.0
   ```

7. **GitHub release** with the changelog section as the body.

   ```sh
   awk '/^## \[0.2.0\]/{flag=1; next} flag && /^## \[/{exit} flag' CHANGELOG.md > /tmp/tenon-notes.md
   gh release create v0.2.0 --title "v0.2.0" --notes-file /tmp/tenon-notes.md
   gh release view v0.2.0
   ```

8. **Verify** the release page, the tag, the README version badge and the changelog link.

## Notes

- Do not retag a published version; cut `0.1.1` for a fix.
- The tag/release happen after the PR merges, on `master`; the release PR only carries the version,
  changelog, examples and checklist.
- The wheel is local for 0.2.0; a later CI release can attach the artifacts.
