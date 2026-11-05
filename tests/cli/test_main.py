"""The CLI entry point: parse, compose the stages, report and return a code."""

import json
import subprocess
import sys

import pytest

from tenon.cli import main


# Spec AC1: help is a 0, and no SystemExit escapes main.
@pytest.mark.parametrize("argv", [["--help"], ["check", "--help"], ["fix", "--help"]])
def test_help_returns_zero(argv, capsys):
    assert main(argv) == 0
    assert "usage: tenon" in capsys.readouterr().out


# Spec AC1: --version prints the package version and returns 0.
def test_version_returns_zero(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("tenon ")
    assert out.strip().split(" ", 1)[1]


# Spec AC1: a missing or unknown subcommand is a usage error, not a traceback.
def test_no_subcommand_is_usage(capsys):
    assert main([]) == 2
    assert "usage: tenon" in capsys.readouterr().err


def test_unknown_subcommand_is_usage(capsys):
    assert main(["probe"]) == 2
    assert "usage: tenon" in capsys.readouterr().err


# Spec AC9: python -m tenon is a runnable module.
def test_module_help_subprocess():
    completed = subprocess.run(
        [sys.executable, "-m", "tenon", "--help"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "usage: tenon" in completed.stdout


def a_check(repo, specs, *extra):
    old, new = specs
    return main(["check", str(repo), "--old", str(old), "--new", str(new), *extra])


# Spec AC2: one certain site is a 1, and the text names it.
def test_check_finds_a_certain_site(a_repo, a_specs, capsys):
    assert a_check(a_repo, a_specs) == 1
    out = capsys.readouterr().out
    assert "acme/billing.py:7:34" in out
    assert "keyword" in out
    assert "amount" in out
    assert "1 changes, 1 certain sites, 0 ambiguity groups" in out


# Spec AC2: --json is exactly one object with the three envelope keys.
def test_check_json_has_one_exact_envelope(a_repo, a_specs, capsys):
    assert a_check(a_repo, a_specs, "--json") == 1
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    assert payload["summary"] == {"changes": 1, "certain": 1, "ambiguous": 0}
    (result,) = payload["results"]
    assert set(result) == {"change", "certain", "ambiguous", "reason"}
    assert result["reason"] is None
    assert result["certain"][0]["path"] == "acme/billing.py"
    assert out.count("\n") == 1


# Spec AC2: no site is a clean 0.
def test_check_clean_repo_exits_zero(a_clean_repo, a_specs, capsys):
    assert a_check(a_clean_repo, a_specs) == 0
    assert "NO_SITES" in capsys.readouterr().out


# Spec AC3: a repository that never imports the SDK cannot be analyzed.
def test_check_without_sdk_import_names_the_reason(a_repo_without_sdk, a_specs, capsys):
    assert a_check(a_repo_without_sdk, a_specs) == 1
    assert "NO_SDK_IMPORT" in capsys.readouterr().out

    assert a_check(a_repo_without_sdk, a_specs, "--json") == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["reason"] == "NO_SDK_IMPORT"


# Spec AC7: a flag overrides [locate].
def test_sdk_package_flag_overrides_config(a_repo, a_specs, capsys):
    assert a_check(a_repo, a_specs, "--json", "--sdk-package", "acme.other") == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["reason"] == "NO_SDK_IMPORT"


# Spec AC7: an operation mapping overrides the inferred call.
def test_operation_flag_overrides_config(a_repo, a_endpoint_specs, capsys):
    assert a_check(a_repo, a_endpoint_specs) == 1
    assert "acme/billing.py:7:27" in capsys.readouterr().out

    assert (
        a_check(
            a_repo,
            a_endpoint_specs,
            "--operation",
            "POST /v1/charges=charges.delete",
        )
        == 0
    )
    assert "NO_SITES" in capsys.readouterr().out


# Spec AC7 + S2: --breaking-only drops the non-breaking addition.
def test_breaking_only_filters_non_breaking_changes(a_repo, a_mixed_specs, capsys):
    assert a_check(a_repo, a_mixed_specs, "--json") == 1
    assert json.loads(capsys.readouterr().out)["summary"]["changes"] == 2

    assert a_check(a_repo, a_mixed_specs, "--json", "--breaking-only") == 1
    assert json.loads(capsys.readouterr().out)["summary"]["changes"] == 1


# Spec AC7: --no-breaking-only overrides a true [tenon] default.
def test_no_breaking_only_overrides_the_config(a_repo, a_mixed_specs, a_breaking_config, capsys):
    flags = ("--config", str(a_breaking_config), "--json")

    assert a_check(a_repo, a_mixed_specs, *flags) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["changes"] == 1

    assert a_check(a_repo, a_mixed_specs, *flags, "--no-breaking-only") == 1
    assert json.loads(capsys.readouterr().out)["summary"]["changes"] == 2


# Spec AC7: a missing tenon.toml is valid when --sdk-package supplies the package.
def test_missing_config_with_sdk_package_is_valid(a_repo_without_config, a_specs, capsys):
    assert (
        a_check(a_repo_without_config, a_specs, "--sdk-package", "acme.client") == 1
    )
    assert "acme/billing.py" in capsys.readouterr().out


# Spec AC7: neither the file nor the flag is a usage error.
def test_missing_config_without_sdk_package_is_usage(a_repo_without_config, a_specs, capsys):
    assert a_check(a_repo_without_config, a_specs) == 2
    assert "sdk-package" in capsys.readouterr().err
