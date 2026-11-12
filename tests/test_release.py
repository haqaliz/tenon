"""Release v0.1.0: version, changelog, checklist and quickstart invariants."""

import shlex
import sys
import tomllib
from pathlib import Path

from tenon.cli import main
from tenon.provider import load_bundle

ROOT = Path(__file__).parent.parent
PROOF_BASIC = ROOT / "tests" / "fixtures" / "repos" / "proof-basic"
EXAMPLES = ROOT / "examples" / "quickstart"
OLD = EXAMPLES / "old.yaml"
NEW = EXAMPLES / "new.yaml"
BUNDLE = EXAMPLES / "bundle.json"


def a_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# Spec AC1: the source version is 0.1.0 and the CLI reports the installed metadata.
def test_version_is_0_1_0(capsys):
    assert a_pyproject()["project"]["version"] == "0.1.0"

    assert main(["--version"]) == 0
    assert capsys.readouterr().out == "tenon 0.1.0\n"


# Spec AC2: the 0.1.0 changelog section exists and names the limits.
def test_changelog_has_the_0_1_0_section():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.1.0] - 2026-11-13" in text
    assert "Known limits" in text


# Spec AC3/AC4: the checklist and the release-check script exist.
def test_release_checklist_and_script_exist():
    checklist = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    for step in ("uv build", "pip install", "tenon --version", "gh release create"):
        assert step in checklist
    script = ROOT / "scripts" / "release_check.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


# Spec AC1/AC2/AC3: the example bundle loads and the three commands work.
def test_example_bundle_and_commands(capsys):
    bundle = load_bundle(BUNDLE)

    assert bundle.provider == "acme"
    assert bundle.migration == "amount-cents"
    assert bundle.old == OLD.resolve()
    assert bundle.new == NEW.resolve()
    assert bundle.command == ("python3", "-c", "import acme.billing")

    # check: the component rename locates amount and exits 1.
    assert (
        main(
            [
                "check",
                str(PROOF_BASIC),
                "--old",
                str(OLD),
                "--new",
                str(NEW),
                "--language",
                "python",
                "--sdk-package",
                "acme.client",
            ]
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "amount -> amount_cents" in out
    assert "1 certain site" in out

    # fix: the rename is proposed and the check passes; no PR, exit 0.
    check = shlex.join([sys.executable, "-c", "import acme.billing"])
    assert (
        main(
            [
                "fix",
                str(PROOF_BASIC),
                "--old",
                str(OLD),
                "--new",
                str(NEW),
                "--language",
                "python",
                "--sdk-package",
                "acme.client",
                "--check",
                check,
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "amount -> amount_cents" in out
    assert "Proof: TESTS_PASSED" in out

    # provider: the example bundle runs to TESTS_PASSED; no PR, exit 0.
    assert (
        main(["provider", "migrate", str(PROOF_BASIC), "--bundle", str(BUNDLE)])
        == 0
    )
    out = capsys.readouterr().out
    assert "provider: acme" in out
    assert "Proof: TESTS_PASSED" in out


# Spec AC4: the README links the changelog, examples and release checklist.
def test_readme_links_the_release_docs():
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "CHANGELOG.md" in text
    assert "examples/README.md" in text
    assert "docs/RELEASE.md" in text
    assert "version-0.1.0" in text
