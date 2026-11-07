"""The CLI entry point: parse, compose the stages, report and return a code."""

import importlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tenon.cli import main
from tenon.corpus import (
    CorpusRecord,
    Outcome,
    benchmark,
    load_corpus,
    record_id,
)
from tenon.detect import diff, diff_mcp, load, load_mcp
from tenon.pr import PrDraft, PrRefusal, PrResult, PrStatus
from tenon.prove import CheckResult, ProofLevel, ProofPlan, ProofResult

# ``tenon.cli.main`` the submodule is shadowed by the exported function.
cli_main = importlib.import_module("tenon.cli.main")


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
    assert "1 change, 1 certain site, 0 ambiguity groups" in out


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


# Spec AC3: [locate] language = "ts" is enough; no flag is needed.
def test_check_ts_language_from_the_config(a_ts_repo, capsys):
    assert a_check(a_ts_repo.repo, a_ts_repo.specs) == 1

    out = capsys.readouterr().out
    assert "src/billing.ts:5:25" in out
    assert "amount" in out
    assert "1 change, 1 certain site, 0 ambiguity groups" in out


# Spec AC3: --language ts overrides a file written for Python.
def test_check_language_flag_overrides_a_python_config(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").write_text(
        '[locate]\nsdk_package = "stripe"\n'
    )

    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--language", "ts") == 1
    assert "src/billing.ts:5:25" in capsys.readouterr().out


# Spec AC3: the TS check uses the shipped JSON envelope.
def test_check_ts_json_has_one_exact_envelope(a_ts_repo, capsys):
    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--json") == 1
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    assert payload["summary"] == {"changes": 1, "certain": 1, "ambiguous": 0}
    (result,) = payload["results"]
    assert result["certain"][0]["path"] == "src/billing.ts"
    assert result["certain"][0]["line"] == 5
    assert result["certain"][0]["column"] == 25
    assert result["certain"][0]["symbol"] == "amount"
    assert result["reason"] is None
    assert out.count("\n") == 1


# Spec AC3: a TS change with no matching site is a clean 0.
def test_check_ts_without_a_site_exits_zero(a_ts_repo, capsys):
    (a_ts_repo.repo / "src" / "billing.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        'export const client = new Stripe("sk_test");\n'
        "\n"
        'client.charges.delete("ch_1");\n'
    )

    assert a_check(a_ts_repo.repo, a_ts_repo.specs) == 0
    assert "NO_SITES" in capsys.readouterr().out


# Spec AC5: --language python validates the file's npm package as Python.
def test_language_python_rejects_a_scoped_npm_package(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").write_text(
        '[locate]\nlanguage = "ts"\nsdk_package = "@scope/pkg"\n'
    )

    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--language", "python") == 2

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Traceback" not in err


# Spec AC5: argparse rejects an unknown --language before any analysis.
def test_unknown_language_flag_is_usage(a_ts_repo, capsys):
    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--language", "ruby") == 2

    captured = capsys.readouterr()
    assert "--language" in captured.err
    assert "Traceback" not in captured.err


# Spec AC5: a missing file builds the TS default from --sdk-package.
def test_missing_config_with_language_ts_uses_sdk_package(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").unlink()

    assert (
        a_check(
            a_ts_repo.repo,
            a_ts_repo.specs,
            "--language",
            "ts",
            "--sdk-package",
            "stripe",
        )
        == 1
    )
    assert "src/billing.ts" in capsys.readouterr().out


# Spec AC5: --language ts without any package is still a usage error.
def test_missing_config_with_language_ts_without_package_is_usage(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").unlink()

    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--language", "ts") == 2
    assert "sdk-package" in capsys.readouterr().err


# Spec AC3: check --source mcp runs the MCP diff and names the argument key.
def test_check_mcp_source_names_the_argument_key(a_mcp_repo, a_mcp_specs, capsys):
    assert a_check(a_mcp_repo, a_mcp_specs, "--source", "mcp") == 1

    out = capsys.readouterr().out
    assert "app.py:7:" in out
    assert "amount" in out
    assert "1 change, 1 certain site, 0 ambiguity groups" in out


# Spec AC3: the MCP check JSON has the shipped envelope and the key.
def test_check_mcp_json_names_the_argument_key(a_mcp_repo, a_mcp_specs, capsys):
    assert a_check(a_mcp_repo, a_mcp_specs, "--source", "mcp", "--json") == 1
    payload = json.loads(capsys.readouterr().out)

    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    assert payload["summary"] == {"changes": 1, "certain": 1, "ambiguous": 0}
    (result,) = payload["results"]
    site = result["certain"][0]
    assert (site["path"], site["symbol"]) == ("app.py", "amount")
    assert result["reason"] is None


# Spec AC2/AC3: [locate] source = "mcp" needs no flag.
def test_check_mcp_source_from_the_config(a_mcp_repo, a_mcp_specs, capsys):
    assert a_check(a_mcp_repo, a_mcp_specs) == 1
    assert "amount" in capsys.readouterr().out


# Spec AC3: identical MCP documents are a clean 0.
def test_check_mcp_clean_change_exits_zero(a_mcp_repo, a_mcp_clean_specs, capsys):
    assert a_check(a_mcp_repo, a_mcp_clean_specs, "--source", "mcp") == 0
    assert "0 changes" in capsys.readouterr().out


# Spec AC5: MCP with TypeScript is one named error.
def test_language_ts_with_source_mcp_is_named(a_mcp_repo, a_mcp_specs, capsys):
    assert (
        a_check(a_mcp_repo, a_mcp_specs, "--source", "mcp", "--language", "ts")
        == 2
    )

    err = capsys.readouterr().err
    assert "mcp" in err
    assert "python" in err
    assert "Traceback" not in err


# Spec AC5: the MCP+TS error in JSON mode is one object.
def test_language_ts_with_source_mcp_json_is_one_error(
    a_mcp_repo, a_mcp_specs, capsys
):
    assert (
        a_check(
            a_mcp_repo,
            a_mcp_specs,
            "--source",
            "mcp",
            "--language",
            "ts",
            "--json",
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert "mcp" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC2/AC5: --source overrides the default, and a missing tenon.toml
# still uses the default mcp client package.
def test_check_mcp_flag_overrides_the_default_source(
    a_mcp_repo_without_config, a_mcp_specs, capsys
):
    assert (
        a_check(a_mcp_repo_without_config, a_mcp_specs, "--source", "mcp")
        == 1
    )
    assert "amount" in capsys.readouterr().out


def a_fix(repo, specs, *extra, remote=None):
    old, new = specs
    return main(
        ["fix", str(repo), "--old", str(old), "--new", str(new), *extra],
        remote=remote,
    )


# Spec AC4: a green check prints the diff and the proof, and writes nothing.
def test_fix_passing_check_prints_diff_and_proof(
    a_repo, a_specs, a_snapshot, capsys
):
    before = a_snapshot(a_repo)

    assert a_fix(a_repo, a_specs) == 0

    out = capsys.readouterr().out
    assert (
        '+    return client.charges.create(amount_cents=amount, currency="usd")'
        in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert "Baseline exit: 0" in out
    assert "After exit: 0" in out
    assert a_snapshot(a_repo) == before


# Spec AC5: no proof command is UNVERIFIED, not a passed proof.
def test_fix_without_a_proof_command_is_unverified(
    a_repo, a_specs, a_no_command_config, capsys
):
    assert (
        a_fix(a_repo, a_specs, "--config", str(a_no_command_config)) == 1
    )
    out = capsys.readouterr().out
    assert "Proof: UNVERIFIED" in out
    assert "Cause: NO_PROOF_COMMAND" in out


# Spec AC5: --require changes the exit code only; the label stays UNVERIFIED.
def test_fix_require_unverified_exits_zero(
    a_repo, a_specs, a_no_command_config, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--require",
            "UNVERIFIED",
        )
        == 0
    )
    assert "Proof: UNVERIFIED" in capsys.readouterr().out


# Spec AC1/AC2: a build-only plan meets TYPES_BUILD_ONLY and shows the build.
def test_fix_build_only_with_build_requirement_exits_zero(
    a_repo, a_specs, a_no_command_config, a_build, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--build",
            a_build,
            "--require",
            "TYPES_BUILD_ONLY",
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Proof: TYPES_BUILD_ONLY" in out
    assert "import acme.billing" in out
    assert "TESTS_PASSED" not in out


# Spec AC3: the same build-only proof does not meet TESTS_PASSED.
def test_fix_build_only_under_tests_requirement_exits_one(
    a_repo, a_specs, a_no_command_config, a_build, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--build",
            a_build,
            "--require",
            "TESTS_PASSED",
        )
        == 1
    )
    assert "Proof: TYPES_BUILD_ONLY" in capsys.readouterr().out


# Spec AC4: a green build with a red test fails closed at TESTS_FAILED_AFTER.
def test_fix_green_build_red_test_is_unverified_after(
    a_repo, a_specs, a_build, a_test_red_after_patch, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--build",
            a_build,
            "--check",
            a_test_red_after_patch,
            "--json",
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    proof = payload["results"][0]["proof"]
    assert proof["level"] == "UNVERIFIED"
    assert proof["cause"] == "TESTS_FAILED_AFTER"
    build_checks = [check for check in proof["checks"] if check["stage"] == "BUILD"]
    test_checks = [check for check in proof["checks"] if check["stage"] == "TESTS"]
    assert [check["returncode"] for check in build_checks] == [0, 0]
    assert [check["returncode"] for check in test_checks] == [0, 1]


# Spec AC4/AC7: the text keeps the green build visible before the red test.
def test_fix_green_build_red_test_text_shows_the_build_pass(
    a_repo, a_specs, a_build, a_test_red_after_patch, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--build",
            a_build,
            "--check",
            a_test_red_after_patch,
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "Proof: UNVERIFIED" in out
    assert "Cause: TESTS_FAILED_AFTER" in out
    build = out.index("BUILD: ")
    tests = out.index("TESTS: ")
    assert build < out.index("import acme.billing", build) < tests
    assert build < out.index("After exit: 0", build) < tests
    assert out.index("After exit: 1", tests) > tests


# Spec AC7: a build-only run counts build_only and carries the build checks.
def test_fix_build_only_json_counts_the_level(
    a_repo, a_specs, a_no_command_config, a_build, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--build",
            a_build,
            "--require",
            "TYPES_BUILD_ONLY",
            "--json",
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["build_only"] == 1
    assert payload["summary"]["passed"] == 0
    assert payload["summary"]["characterized"] == 0
    proof = payload["results"][0]["proof"]
    assert proof["level"] == "TYPES_BUILD_ONLY"
    assert [check["stage"] for check in proof["checks"]] == ["BUILD", "BUILD"]


# Spec AC1: the four stage flags reach one plan, in plan order.
def test_fix_stage_flags_reach_one_plan(a_repo, a_specs, monkeypatch):
    seen = []

    def prove_plan_spy(proposal, repo, plan):
        seen.append(plan)
        return a_green_proof()

    monkeypatch.setattr(cli_main, "prove_plan", prove_plan_spy)

    assert (
        a_fix(
            a_repo,
            a_specs,
            "--build",
            "build one",
            "--characterize",
            "characterize one",
            "--replay",
            "replay one",
            "--check",
            "tests one",
        )
        == 0
    )
    assert seen == [
        ProofPlan(
            tests=("tests", "one"),
            characterize=("characterize", "one"),
            replay=("replay", "one"),
            build=("build", "one"),
        )
    ]


# Spec AC1: a missing stage flag falls back to [tenon], not to empty.
def test_fix_stage_commands_fall_back_to_the_config(a_repo, a_specs, monkeypatch):
    (a_repo / "tenon.toml").write_text(
        '[locate]\nsdk_package = "acme.client"\n'
        "\n[tenon]\n"
        'command = ["tests", "from", "config"]\n'
        'build = ["build", "from", "config"]\n'
        'characterize = ["characterize", "from", "config"]\n'
        'replay = ["replay", "from", "config"]\n'
    )
    seen = []

    def prove_plan_spy(proposal, repo, plan):
        seen.append(plan)
        return a_green_proof()

    monkeypatch.setattr(cli_main, "prove_plan", prove_plan_spy)

    assert a_fix(a_repo, a_specs) == 0
    assert seen == [
        ProofPlan(
            tests=("tests", "from", "config"),
            characterize=("characterize", "from", "config"),
            replay=("replay", "from", "config"),
            build=("build", "from", "config"),
        )
    ]


# Spec AC5: the JSON proof carries the named cause.
def test_fix_json_carries_the_unverified_cause(
    a_repo, a_specs, a_no_command_config, capsys
):
    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--json",
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)

    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "fix"
    assert payload["results"][0]["proof"]["level"] == "UNVERIFIED"
    assert payload["results"][0]["proof"]["cause"] == "NO_PROOF_COMMAND"
    assert payload["results"][0]["pr"] is None
    assert payload["summary"]["unverified"] == 1


# Spec AC5: a change with no rule still names the proposal reason.
def test_fix_no_rule_reports_the_proposal_reason(a_repo, a_removed_specs, capsys):
    assert a_fix(a_repo, a_removed_specs) == 1
    out = capsys.readouterr().out
    assert "No patch: NO_RULE" in out
    assert "Cause: NO_PATCH_PROPOSED" in out


# Spec AC2/M5: zero changes after filtering is a clean 0.
def test_fix_zero_changes_exits_zero(a_repo, a_same_specs, capsys):
    assert a_fix(a_repo, a_same_specs) == 0
    out = capsys.readouterr().out
    assert "0 changes, 0 proposals" in out


def a_green_proof():
    green = CheckResult(
        kind="baseline", command=("npm", "test"), returncode=0, timed_out=False
    )
    after = CheckResult(
        kind="after", command=("npm", "test"), returncode=0, timed_out=False
    )
    return ProofResult(
        level=ProofLevel.TESTS_PASSED,
        baseline=green,
        after=after,
        patch_applied=True,
    )


# Spec AC4: fix uses the TS site, proposes against it and leaves the tree alone.
def test_fix_ts_locates_proposes_and_renders_the_diff(
    a_ts_repo, a_snapshot, monkeypatch, capsys
):
    located = []
    real_propose = cli_main.propose

    def propose_spy(change, result, repo):
        located.append(result)
        return real_propose(change, result, repo)

    monkeypatch.setattr(cli_main, "propose", propose_spy)
    monkeypatch.setattr(
        cli_main, "prove_plan", lambda *args, **kwargs: a_green_proof()
    )
    before = a_snapshot(a_ts_repo.repo)

    assert a_fix(a_ts_repo.repo, a_ts_repo.specs, "--language", "ts") == 0

    out = capsys.readouterr().out
    assert (
        '+client.charges.create({ amount_cents: 100, currency: "usd" });' in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert [
        (site.path, site.line, site.column) for site in located[0].certain
    ] == [a_ts_repo.site]
    assert a_snapshot(a_ts_repo.repo) == before


# Spec AC4: fix --source mcp locates the MCP key, proposes and renders the diff.
def test_fix_mcp_locates_proposes_and_renders_the_diff(
    a_mcp_repo, a_mcp_specs, a_snapshot, monkeypatch, capsys
):
    located = []
    real_propose = cli_main.propose

    def propose_spy(change, result, repo):
        located.append(result)
        return real_propose(change, result, repo)

    monkeypatch.setattr(cli_main, "propose", propose_spy)
    monkeypatch.setattr(
        cli_main, "prove_plan", lambda *args, **kwargs: a_green_proof()
    )
    before = a_snapshot(a_mcp_repo)

    assert a_fix(a_mcp_repo, a_mcp_specs, "--source", "mcp") == 0

    out = capsys.readouterr().out
    assert (
        '-            "create_charge", arguments={"amount": 100}' in out
    )
    assert (
        '+            "create_charge", arguments={"amount_cents": 100}' in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert [
        (site.path, site.line, site.column) for site in located[0].certain
    ] == [("app.py", 7, 41)]
    assert a_snapshot(a_mcp_repo) == before


# Spec AC4: fix with the source from the config needs no flag.
def test_fix_mcp_source_from_the_config(
    a_mcp_repo, a_mcp_specs, monkeypatch, capsys
):
    monkeypatch.setattr(
        cli_main, "prove_plan", lambda *args, **kwargs: a_green_proof()
    )

    assert a_fix(a_mcp_repo, a_mcp_specs) == 0
    assert "amount_cents" in capsys.readouterr().out


# Spec AC5: --language ts with a package npm cannot accept is a named config error.
def test_language_ts_rejects_an_invalid_npm_package(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").write_text(
        '[locate]\nsdk_package = "acme/client"\n'
    )

    assert a_check(a_ts_repo.repo, a_ts_repo.specs, "--language", "ts") == 2

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Traceback" not in err


# Spec AC2/AC5: a TS config with an invalid Python package is one JSON error object.
def test_ts_config_invalid_python_package_json_is_one_error(a_ts_repo, capsys):
    (a_ts_repo.repo / "tenon.toml").write_text(
        '[locate]\nlanguage = "ts"\nsdk_package = "@scope/pkg"\n'
    )

    assert (
        a_check(
            a_ts_repo.repo,
            a_ts_repo.specs,
            "--language",
            "python",
            "--json",
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert "sdk_package" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


def a_pr(proof, status=PrStatus.OPENED, refusal=None):
    draft = PrDraft(
        title=f"[{proof.level.value}] tenon: rename",
        body="body",
        branch="tenon/rename-1234abcd",
        commit_message="tenon: rename",
    )
    if status is PrStatus.OPENED:
        return PrResult(
            status=status,
            level=proof.level,
            draft=draft,
            url="https://github.com/example/repo/pull/7",
        )
    return PrResult(
        status=status, level=proof.level, draft=draft, refusal=refusal
    )


def a_recorder(make_result):
    calls = []

    def write_pr(
        proposal,
        proof,
        repo,
        *,
        remote,
        required=ProofLevel.TESTS_PASSED,
        allow_below_required=False,
        unanalyzed=(),
    ):
        calls.append(
            {
                "proposal": proposal,
                "proof": proof,
                "repo": repo,
                "remote": remote,
                "required": required,
                "allow_below_required": allow_below_required,
                "unanalyzed": unanalyzed,
            }
        )
        return make_result(proof)

    return write_pr, calls


# Spec AC6: one passed proposal is one opened PR, with the diff's unanalyzed list.
def test_fix_open_pr_opens_one_pr(a_repo, a_specs, monkeypatch, capsys):
    old, new = a_specs
    expected_unanalyzed = diff(load(old), load(new)).unanalyzed
    write_pr, calls = a_recorder(a_pr)
    remote = object()
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fix(a_repo, a_specs, "--open-pr", remote=remote) == 0

    assert "PR: https://github.com/example/repo/pull/7" in capsys.readouterr().out
    (call,) = calls
    assert call["proposal"].edits
    assert call["proof"].level is ProofLevel.TESTS_PASSED
    assert call["repo"] == a_repo
    assert call["remote"] is remote
    assert call["required"] is ProofLevel.TESTS_PASSED
    assert call["allow_below_required"] is False
    assert call["unanalyzed"] == expected_unanalyzed


# Spec AC3/AC5: the MCP diff's unanalyzed list reaches the PR writer.
def test_fix_mcp_open_pr_passes_the_unanalyzed_list(
    a_mcp_repo, a_mcp_unanalyzed_specs, monkeypatch, capsys
):
    old, new = a_mcp_unanalyzed_specs
    expected_unanalyzed = diff_mcp(load_mcp(old), load_mcp(new)).unanalyzed
    assert expected_unanalyzed
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)
    monkeypatch.setattr(
        cli_main, "prove_plan", lambda *args, **kwargs: a_green_proof()
    )

    assert (
        a_fix(
            a_mcp_repo,
            a_mcp_unanalyzed_specs,
            "--source",
            "mcp",
            "--open-pr",
            remote=object(),
        )
        == 0
    )

    (call,) = calls
    assert call["unanalyzed"] == expected_unanalyzed


# Spec AC5: below the requirement with no opt-in, the CLI never calls the writer.
def test_fix_open_pr_below_required_makes_no_pr_call(
    a_repo, a_specs, a_no_command_config, monkeypatch, capsys
):
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--open-pr",
            remote=object(),
        )
        == 1
    )

    assert calls == []
    assert "PR:" not in capsys.readouterr().out


# Spec AC5/AC6: either opt-in reaches the writer as allow_below_required.
@pytest.mark.parametrize(
    "flag", ["--allow-below-required", "--allow-unverified"]
)
def test_fix_open_pr_below_required_opt_in_reaches_the_writer(
    flag, a_repo, a_specs, a_no_command_config, monkeypatch
):
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--open-pr",
            flag,
            remote=object(),
        )
        == 1
    )
    (call,) = calls
    assert call["required"] is ProofLevel.TESTS_PASSED
    assert call["allow_below_required"] is True


# Spec AC6: --allow-unverified still works at the requirement with --require.
def test_fix_open_pr_allow_unverified_is_passed_through(
    a_repo, a_specs, a_no_command_config, monkeypatch
):
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_fix(
            a_repo,
            a_specs,
            "--config",
            str(a_no_command_config),
            "--open-pr",
            "--allow-unverified",
            "--require",
            "UNVERIFIED",
            remote=object(),
        )
        == 0
    )
    assert calls[0]["allow_below_required"] is True


# Spec AC6: any refused writer result makes the run a 1 and is rendered.
def test_fix_open_pr_refusal_is_rendered(a_repo, a_specs, monkeypatch, capsys):
    write_pr, _calls = a_recorder(
        lambda proof: a_pr(proof, PrStatus.REFUSED, PrRefusal.DIRTY_CHECKOUT)
    )
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fix(a_repo, a_specs, "--open-pr", "--json", remote=object()) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["pr"]["status"] == "REFUSED"
    assert payload["results"][0]["pr"]["refusal"] == "DIRTY_CHECKOUT"
    assert payload["summary"]["prs_opened"] == 0
    assert payload["summary"]["prs_refused"] == 1


# Spec AC10: the real adapter is never constructed without --open-pr.
def test_fix_without_open_pr_does_not_construct_a_remote(
    a_repo, a_specs, monkeypatch
):
    def bomb():
        raise AssertionError("GitGhRemote must not be constructed")

    monkeypatch.setattr(cli_main, "GitGhRemote", bomb)

    assert a_fix(a_repo, a_specs) == 0


# Spec AC6/M11: --open-pr without an injected remote builds the real adapter once.
def test_fix_open_pr_builds_the_default_remote(a_repo, a_specs, monkeypatch):
    marker = object()
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "GitGhRemote", lambda: marker)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fix(a_repo, a_specs, "--open-pr") == 0
    assert calls[0]["remote"] is marker


APP_ENV = (
    "TENON_GITHUB_APP_ID",
    "TENON_GITHUB_APP_INSTALLATION_ID",
    "TENON_GITHUB_APP_PRIVATE_KEY",
    "TENON_GITHUB_API_URL",
)


@pytest.fixture
def a_app_env(monkeypatch):
    """No inherited app inputs; each test sets only what it needs."""
    for name in APP_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def a_app_key(tmp_path, name="app.pem"):
    path = tmp_path / name
    path.write_text(
        "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    return path


def a_app_recorders(monkeypatch):
    """Record the app token and remote construction, in order."""
    tokens = []
    remotes = []

    class Token:
        def __init__(
            self,
            app_id,
            installation_id,
            private_key_pem,
            transport,
            api_url="https://api.github.com",
        ):
            self.record = {
                "app_id": app_id,
                "installation_id": installation_id,
                "private_key_pem": private_key_pem,
                "transport": transport,
                "api_url": api_url,
            }
            tokens.append(self.record)

    class Remote:
        def __init__(self, provider, api_url="https://api.github.com"):
            self.record = {"provider": provider, "api_url": api_url}
            remotes.append(self.record)

    monkeypatch.setattr(cli_main, "GitHubAppToken", Token)
    monkeypatch.setattr(cli_main, "GitHubAppRemote", Remote)
    return tokens, remotes


# Spec AC1: an explicit gh remote keeps the shipped GitGhRemote path.
def test_fix_open_pr_remote_gh_uses_gitgh(a_repo, a_specs, monkeypatch):
    marker = object()
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "GitGhRemote", lambda: marker)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fix(a_repo, a_specs, "--open-pr", "--remote", "gh") == 0
    assert calls[0]["remote"] is marker


# Spec AC2: --remote app builds the token and remote from the flags, and the
# writer receives that remote.
def test_fix_open_pr_remote_app_constructs_the_app_remote(
    a_repo, a_specs, tmp_path, monkeypatch, a_app_env
):
    key = a_app_key(tmp_path)
    tokens, remotes = a_app_recorders(monkeypatch)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_fix(
            a_repo,
            a_specs,
            "--open-pr",
            "--remote",
            "app",
            "--app-id",
            "123",
            "--app-installation-id",
            "456",
            "--app-private-key",
            str(key),
            "--api-url",
            "https://ghe.example/api/v3",
        )
        == 0
    )

    (token,) = tokens
    assert token["app_id"] == "123"
    assert token["installation_id"] == "456"
    assert token["private_key_pem"] == key.read_text(encoding="utf-8")
    assert token["api_url"] == "https://ghe.example/api/v3"
    (remote,) = remotes
    assert remote["provider"].record is token
    assert remote["api_url"] == "https://ghe.example/api/v3"
    assert calls[0]["remote"].record is remote


# Spec AC8: a refused spec is exit 2, named, and never a traceback.
def test_bad_spec_is_a_named_refusal(a_repo, a_specs, tmp_path, capsys):
    _old, new = a_specs
    bad = tmp_path / "bad.yaml"
    bad.write_text("openapi: 2.0\n")

    assert a_check(a_repo, (bad, new)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tenon: spec:" in captured.err
    assert "UNSUPPORTED_VERSION" in captured.err
    assert "Traceback" not in captured.err


# Spec AC8/M10: with --json the one error object is the only stdout.
def test_bad_spec_json_is_one_error_object_on_stdout(a_repo, a_specs, tmp_path, capsys):
    _old, new = a_specs
    bad = tmp_path / "bad.yaml"
    bad.write_text("openapi: 2.0\n")

    assert a_check(a_repo, (bad, new), "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "spec"
    assert payload["error"]["code"] == "UNSUPPORTED_VERSION"
    assert payload["error"]["pointer"] == "#/openapi"
    assert payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC8: a malformed tenon.toml is a named config error.
def test_bad_toml_is_a_config_error(a_repo, a_specs, capsys):
    (a_repo / "tenon.toml").write_text("[locate\n")

    assert a_check(a_repo, a_specs) == 2

    err = capsys.readouterr().err
    assert "tenon: config:" in err
    assert "tenon.toml" in err
    assert "Traceback" not in err


# Spec AC8: a missing spec file is exit 2 and names the file.
def test_missing_spec_exits_two(a_repo, a_specs, tmp_path, capsys):
    _old, new = a_specs
    missing = tmp_path / "missing.yaml"

    assert a_check(a_repo, (missing, new)) == 2

    err = capsys.readouterr().err
    assert "missing.yaml" in err
    assert "Traceback" not in err


# Spec AC2/M6: an unknown --require names the five ladder levels.
def test_unknown_require_names_the_five_levels(a_repo, a_specs, capsys):
    assert a_fix(a_repo, a_specs, "--require", "BY_HAND") == 2

    err = capsys.readouterr().err
    assert "--require" in err
    assert "TYPES_BUILD_ONLY" in err
    assert "UNVERIFIED" in err


# Spec AC2/AC7: a bad [tenon] require in --json mode is one error object.
def test_bad_require_in_the_config_json_is_one_error(a_repo, a_specs, capsys):
    (a_repo / "tenon.toml").write_text(
        '[locate]\nsdk_package = "acme.client"\n\n[tenon]\nrequire = "BY_HAND"\n'
    )

    assert a_fix(a_repo, a_specs, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert "TYPES_BUILD_ONLY" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec M10: an unexpected failure is an internal 1, not a traceback.
def test_unexpected_failure_is_internal(a_repo, a_specs, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "diff", boom)

    assert a_check(a_repo, a_specs) == 1

    captured = capsys.readouterr()
    assert "tenon: internal: boom" in captured.err
    assert "Traceback" not in captured.err


def a_run_module_check(repo, specs, seed, *extra):
    old, new = specs
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tenon",
            "check",
            str(repo),
            "--old",
            str(old),
            "--new",
            str(new),
            *extra,
            "--json",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
    )


def a_run_module_fix(repo, specs, seed, *extra):
    old, new = specs
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tenon",
            "fix",
            str(repo),
            "--old",
            str(old),
            "--new",
            str(new),
            *extra,
            "--json",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
    )


# Spec AC10/M12: the same inputs give byte-identical JSON across hash seeds.
def test_check_json_is_byte_stable_across_hash_seeds(a_repo, a_specs):
    first = a_run_module_check(a_repo, a_specs, "0")
    second = a_run_module_check(a_repo, a_specs, "1")

    assert first.returncode == 1
    assert second.returncode == 1
    assert first.stdout == second.stdout
    assert b"acme/billing.py" in first.stdout
    assert str(a_repo).encode() not in first.stdout


# Spec AC3/M12: the same TS check report is byte-identical across hash seeds.
def test_check_ts_json_is_byte_stable_across_hash_seeds(a_ts_repo):
    first = a_run_module_check(a_ts_repo.repo, a_ts_repo.specs, "0")
    second = a_run_module_check(a_ts_repo.repo, a_ts_repo.specs, "1")

    assert first.returncode == 1
    assert second.returncode == 1
    assert first.stdout == second.stdout
    assert b"src/billing.ts" in first.stdout
    assert str(a_ts_repo.repo).encode() not in first.stdout


# Spec AC3/M12: the MCP check report is byte-identical across hash seeds.
def test_check_mcp_json_is_byte_stable_across_hash_seeds(a_mcp_repo, a_mcp_specs):
    first = a_run_module_check(a_mcp_repo, a_mcp_specs, "0", "--source", "mcp")
    second = a_run_module_check(a_mcp_repo, a_mcp_specs, "1", "--source", "mcp")

    assert first.returncode == 1
    assert second.returncode == 1
    assert first.stdout == second.stdout
    assert b"amount" in first.stdout
    assert str(a_mcp_repo).encode() not in first.stdout


# Spec AC7/M12: a build-only fix report is byte-identical across hash seeds.
def test_fix_build_only_json_is_byte_stable_across_hash_seeds(
    a_repo, a_specs, a_no_command_config, a_build
):
    flags = (
        "--config",
        str(a_no_command_config),
        "--build",
        a_build,
        "--require",
        "TYPES_BUILD_ONLY",
    )
    first = a_run_module_fix(a_repo, a_specs, "0", *flags)
    second = a_run_module_fix(a_repo, a_specs, "1", *flags)

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
    assert b"TYPES_BUILD_ONLY" in first.stdout
    assert str(a_repo).encode() not in first.stdout


PROBE_FIXTURES = Path(__file__).parent.parent / "fixtures" / "mcp"
PROBE_SERVER = PROBE_FIXTURES / "probe_server.py"
PROBE_AGENT = PROBE_FIXTURES / "probe_agent.py"
PROBE_TASKS = PROBE_FIXTURES / "probe_tasks.json"


def a_probe(*extra, tasks=PROBE_TASKS, server=(), agent=(), timeout="5"):
    return main(
        [
            "probe",
            "--server-cmd",
            shlex.join([sys.executable, str(PROBE_SERVER), *server]),
            "--tasks",
            str(tasks),
            "--agent",
            shlex.join([sys.executable, str(PROBE_AGENT), *agent]),
            "--timeout",
            timeout,
            *extra,
        ]
    )


def a_tasks_file(tmp_path, tasks, name="tasks.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    return path


@pytest.fixture
def a_pass_tasks(tmp_path):
    return a_tasks_file(
        tmp_path,
        [
            {
                "name": "echo",
                "prompt": "Echo hello",
                "expect": {"tools": ["echo"], "result_contains": "echo:hello"},
            }
        ],
    )


# Spec AC1: probe is the third subcommand and its own help is a 0.
def test_probe_help_returns_zero(capsys):
    assert main(["probe", "--help"]) == 0

    out = capsys.readouterr().out
    assert "usage: tenon probe" in out
    assert "--server-cmd" in out
    assert "--tasks" in out
    assert "--agent" in out


# Spec AC1: the probe flags are required, and the missing flag is named.
def test_probe_missing_required_flags_exit_two(capsys):
    assert main(["probe", "--tasks", str(PROBE_TASKS)]) == 2

    err = capsys.readouterr().err
    assert "--server-cmd" in err
    assert "Traceback" not in err


# Spec AC2: a valid fake server/agent/tasks run is a 0; probe takes no repo.
def test_probe_passing_run_exits_zero(a_pass_tasks, capsys):
    assert a_probe(tasks=a_pass_tasks) == 0


# Spec AC2: the passing text names the task and the tool count.
def test_probe_text_names_the_task_and_tools(a_pass_tasks, capsys):
    assert a_probe(tasks=a_pass_tasks) == 0

    out = capsys.readouterr().out
    assert "PASS echo: echo:hello" in out
    assert "2 tools, 1 task, 1 passed, 0 failed" in out


# Spec AC3: a failing task is a 1 that names the failed call and its error.
def test_probe_failing_task_exits_one_and_names_the_call(capsys):
    assert a_probe() == 1

    out = capsys.readouterr().out
    assert "FAIL fail: fail: isError: boom" in out
    assert "1 passed, 1 failed" in out


# Spec AC2/AC7: --json is the report object, byte-identical across runs.
def test_probe_json_has_the_report_shape_and_is_byte_stable(a_pass_tasks, capsys):
    assert a_probe("--json", tasks=a_pass_tasks) == 0
    first = capsys.readouterr().out
    assert a_probe("--json", tasks=a_pass_tasks) == 0
    second = capsys.readouterr().out

    assert first == second
    payload = json.loads(first)
    assert set(payload) == {"server", "tools", "tasks", "summary"}
    assert payload["server"]["name"] == "fake"
    assert [tool["name"] for tool in payload["tools"]] == ["echo", "fail"]
    (task,) = payload["tasks"]
    assert task["ok"] is True
    assert task["calls"][0]["result_excerpt"] == "echo:hello"
    assert payload["summary"] == {"tasks": 1, "ok": 1, "failed": 0}
    assert first.count("\n") == 1


# Spec AC2: an empty tasks file is valid, exits 0 and reports zero.
def test_probe_empty_tasks_exits_zero(tmp_path, capsys):
    tasks = a_tasks_file(tmp_path, [], name="empty.json")

    assert a_probe(tasks=tasks) == 0
    assert "0 tasks, 0 passed, 0 failed" in capsys.readouterr().out


def a_probe_error(captured):
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"kind", "reason", "message"}
    assert payload["error"]["kind"] == "probe"
    assert captured.out.count("\n") == 1
    return payload["error"]


# Spec AC4: a bad tasks file is one probe error object and exit 2.
def test_probe_bad_tasks_json_is_one_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    assert a_probe("--json", tasks=bad) == 2

    error = a_probe_error(capsys.readouterr())
    assert error["reason"] == "invalid_tasks"
    assert "invalid JSON" in error["message"]


# Spec AC4: without --json the same setup failure is one stderr line.
def test_probe_bad_tasks_text_is_one_stderr_line(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    assert a_probe(tasks=bad) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("tenon: probe: invalid_tasks:")
    assert "invalid JSON" in captured.err
    assert "Traceback" not in captured.err


# Spec AC4: a server that exits during the handshake is one probe error object.
def test_probe_server_exit_json_is_one_error(capsys):
    assert a_probe("--json", server=("--exit-after-first",)) == 2

    error = a_probe_error(capsys.readouterr())
    assert error["reason"] == "server_exit"


# Spec AC4: an agent that cannot spawn is one probe error object.
def test_probe_bad_agent_spawn_json_is_one_error(capsys):
    command = [
        "probe",
        "--server-cmd",
        shlex.join([sys.executable, str(PROBE_SERVER)]),
        "--tasks",
        str(PROBE_TASKS),
        "--agent",
        "/tenon-no-such-agent-xyz",
        "--timeout",
        "5",
        "--json",
    ]

    assert main(command) == 2

    error = a_probe_error(capsys.readouterr())
    assert error["reason"] == "AGENT_SPAWN_FAILED"


# Spec AC4: a non-positive --timeout is one probe error object in JSON mode.
@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_probe_non_positive_timeout_json_is_one_error(timeout, a_pass_tasks, capsys):
    assert a_probe("--json", tasks=a_pass_tasks, timeout=timeout) == 2

    error = a_probe_error(capsys.readouterr())
    assert error["reason"] == "invalid_timeout"
    assert "positive" in error["message"]


# Spec AC4: an unbalanced command quote is a named error, not a traceback.
def test_probe_unbalanced_command_quote_is_one_error(a_pass_tasks, capsys):
    command = [
        "probe",
        "--server-cmd",
        "python 'unclosed",
        "--tasks",
        str(a_pass_tasks),
        "--agent",
        shlex.join([sys.executable, str(PROBE_AGENT)]),
        "--timeout",
        "5",
        "--json",
    ]

    assert main(command) == 2

    error = a_probe_error(capsys.readouterr())
    assert error["reason"] == "invalid_command"
    assert "quotation" in error["message"]


# Spec AC1: a non-numeric --timeout stays an argparse usage error.
def test_probe_non_numeric_timeout_is_usage(a_pass_tasks, capsys):
    assert a_probe(tasks=a_pass_tasks, timeout="soon") == 2

    err = capsys.readouterr().err
    assert "--timeout" in err
    assert "Traceback" not in err


CORPUS_REPO = "https://github.com/o/r"
CORPUS_COMMIT = "0123456789abcdef0123456789abcdef01234567"
CORPUS_CHANGE = {
    "kind": "renamed",
    "location": {
        "method": "post",
        "path": "/v1/checkout/sessions",
        "pointer": (
            "#/paths/~1v1~1checkout~1sessions/post/requestBody/content/"
            "application~1x-www-form-urlencoded/schema/properties"
        ),
    },
    "before": "payment_method_types",
    "after": "allowed_payment_method_types",
    "breaking": True,
    "confidence": "inferred",
}
CORPUS_DIFF = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -4,7 +4,7 @@\n"
    '-    payment_method_types=["card"],\n'
    '+    allowed_payment_method_types=["card"],\n'
)
CORPUS_PROPOSAL = {
    "change": CORPUS_CHANGE,
    "edits": [
        {
            "path": "app.py",
            "line": 7,
            "column": 13,
            "shape": "keyword",
            "old": "payment_method_types",
            "new": "allowed_payment_method_types",
        }
    ],
    "skipped": [],
    "files": ["app.py"],
    "diff": CORPUS_DIFF,
    "reason": None,
}
CORPUS_PROOF = {
    "level": "TESTS_PASSED",
    "cause": None,
    "baseline": {
        "kind": "baseline",
        "stage": "TESTS",
        "command": ["pytest", "tests/test_app.py", "-q"],
        "returncode": 0,
        "timed_out": False,
        "stdout_tail": "1 passed",
        "stderr_tail": "",
    },
    "after": {
        "kind": "after",
        "stage": "TESTS",
        "command": ["pytest", "tests/test_app.py", "-q"],
        "returncode": 0,
        "timed_out": False,
        "stdout_tail": "1 passed",
        "stderr_tail": "",
    },
    "patch_applied": True,
    "checks": [],
}
SECOND_CHANGE = {**CORPUS_CHANGE, "before": "currency", "after": "currency_code"}
SECOND_PROPOSAL = {
    **CORPUS_PROPOSAL,
    "change": SECOND_CHANGE,
    "edits": [
        {
            **CORPUS_PROPOSAL["edits"][0],
            "path": "other.py",
            "line": 12,
            "old": "currency",
            "new": "currency_code",
        }
    ],
    "files": ["other.py"],
    "diff": (
        "--- a/other.py\n"
        "+++ b/other.py\n"
        "@@ -10,7 +10,7 @@\n"
        '-    currency="usd",\n'
        '+    currency_code="usd",\n'
    ),
}


def a_corpus_result(**overrides):
    """One result shaped exactly like ``render_fix_json`` output."""
    values = {
        "change": CORPUS_CHANGE,
        "locate": {
            "change": CORPUS_CHANGE,
            "certain": [],
            "ambiguous": [],
            "reason": None,
        },
        "proposal": CORPUS_PROPOSAL,
        "proof": CORPUS_PROOF,
        "pr": None,
    }
    values.update(overrides)
    return values


def a_fix_json(tmp_path, *results, name="fix.json"):
    payload = {
        "command": "fix",
        "results": list(results),
        "summary": {"changes": len(results)},
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def a_corpus_record(fix, corpus, *extra, outcome="local_only", date="2026-11-07"):
    return main(
        [
            "corpus",
            "record",
            "--from",
            str(fix),
            "--repo",
            CORPUS_REPO,
            "--commit",
            CORPUS_COMMIT,
            "--outcome",
            outcome,
            "--date",
            date,
            "--corpus",
            str(corpus),
            *extra,
        ]
    )


# Spec AC1: a valid two-result fix report appends one deterministic record each.
def test_corpus_record_appends_one_record_per_result(tmp_path, capsys):
    fix = a_fix_json(
        tmp_path,
        a_corpus_result(),
        a_corpus_result(change=SECOND_CHANGE, proposal=SECOND_PROPOSAL),
    )
    corpus = tmp_path / "corpus.jsonl"

    assert (
        a_corpus_record(
            fix,
            corpus,
            "--outcome-url",
            "https://github.com/o/r/pull/1",
            "--notes",
            "focused test",
            "--evidence",
            "docs/evidence.md",
        )
        == 0
    )

    records = load_corpus(corpus)
    assert len(records) == 2
    first, second = records
    assert first.id == record_id(
        CORPUS_REPO, CORPUS_COMMIT, CORPUS_CHANGE, CORPUS_PROPOSAL
    )
    assert second.id == record_id(
        CORPUS_REPO, CORPUS_COMMIT, SECOND_CHANGE, SECOND_PROPOSAL
    )
    assert first.id != second.id
    assert (first.repo, first.commit) == (CORPUS_REPO, CORPUS_COMMIT)
    assert (first.change, first.proposal, first.proof) == (
        CORPUS_CHANGE,
        CORPUS_PROPOSAL,
        CORPUS_PROOF,
    )
    assert first.pr is None
    assert first.outcome is Outcome.LOCAL_ONLY
    assert first.recorded == "2026-11-07"
    assert first.outcome_url == "https://github.com/o/r/pull/1"
    assert first.notes == "focused test"
    assert first.evidence == "docs/evidence.md"
    assert capsys.readouterr().out == f"{first.id}\n{second.id}\n"


# Spec AC1: a fix report with no results records nothing and prints no ids.
def test_corpus_record_with_no_results_records_nothing(tmp_path, capsys):
    fix = a_fix_json(tmp_path)
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus) == 0

    assert capsys.readouterr().out == ""
    assert load_corpus(corpus) == ()


# Spec AC1: --json lists the recorded ids as one object.
def test_corpus_record_json_lists_the_ids(tmp_path, capsys):
    fix = a_fix_json(
        tmp_path,
        a_corpus_result(),
        a_corpus_result(change=SECOND_CHANGE, proposal=SECOND_PROPOSAL),
    )
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus, "--json") == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ids": [
            record_id(CORPUS_REPO, CORPUS_COMMIT, CORPUS_CHANGE, CORPUS_PROPOSAL),
            record_id(
                CORPUS_REPO, CORPUS_COMMIT, SECOND_CHANGE, SECOND_PROPOSAL
            ),
        ]
    }
    assert captured.out.count("\n") == 1


# Spec AC1/AC2: every lowercase outcome token maps to the uppercase enum.
@pytest.mark.parametrize(
    "token", ["pending", "merged", "rejected", "closed", "incident", "local_only"]
)
def test_corpus_record_maps_every_outcome_token(tmp_path, capsys, token):
    fix = a_fix_json(tmp_path, a_corpus_result())
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus, outcome=token) == 0

    (record,) = load_corpus(corpus)
    assert record.outcome.value == token.upper()


# Spec AC2: a non-fix report, a missing results list, a missing result key and
# a non-object result are named errors that append nothing.
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"command": "check", "results": []}, 'command != "fix"'),
        ({"command": "fix"}, "results list"),
        (
            {"command": "fix", "results": [{"change": {}, "proposal": {}}]},
            "proof must be a mapping",
        ),
        ({"command": "fix", "results": ["not an object"]}, "must be an object"),
    ],
)
def test_corpus_record_bad_fix_json_appends_nothing(
    tmp_path, capsys, payload, message
):
    fix = tmp_path / "fix.json"
    fix.write_text(json.dumps(payload), encoding="utf-8")
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus) == 2

    captured = capsys.readouterr()
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert not corpus.exists()


# Spec AC2: a malformed fix JSON body is a named error, not a traceback.
def test_corpus_record_invalid_json_is_a_named_error(tmp_path, capsys):
    fix = tmp_path / "fix.json"
    fix.write_text("{", encoding="utf-8")
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus) == 2

    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err
    assert "Traceback" not in captured.err
    assert not corpus.exists()


# Spec AC2: a missing fix file is a named error.
def test_corpus_record_missing_fix_file_exits_two(tmp_path, capsys):
    assert a_corpus_record(tmp_path / "missing.json", tmp_path / "corpus.jsonl") == 2

    err = capsys.readouterr().err
    assert "cannot read fix JSON" in err
    assert "Traceback" not in err


# Spec AC2: a date that is not a real YYYY-MM-DD appends nothing.
@pytest.mark.parametrize("date", ["2026-13-01", "07/11/2026", "2026-1-1"])
def test_corpus_record_bad_date_exits_two(tmp_path, capsys, date):
    fix = a_fix_json(tmp_path, a_corpus_result())
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus, date=date) == 2

    captured = capsys.readouterr()
    assert "YYYY-MM-DD" in captured.err
    assert "Traceback" not in captured.err
    assert not corpus.exists()


# Spec AC2: an unknown outcome token appends nothing.
def test_corpus_record_unknown_outcome_exits_two(tmp_path, capsys):
    fix = a_fix_json(tmp_path, a_corpus_result())
    corpus = tmp_path / "corpus.jsonl"

    assert a_corpus_record(fix, corpus, outcome="bogus") == 2

    captured = capsys.readouterr()
    assert "unknown outcome" in captured.err
    assert "Traceback" not in captured.err
    assert not corpus.exists()


# Spec AC2/AC7: a --json error is one object on stdout, never a traceback.
def test_corpus_record_json_error_is_one_object(tmp_path, capsys):
    fix = a_fix_json(tmp_path, a_corpus_result())

    assert a_corpus_record(
        fix, tmp_path / "corpus.jsonl", "--json", outcome="bogus"
    ) == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "corpus"
    assert "unknown outcome" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


def a_stored_record(commit="commit-one", outcome=Outcome.LOCAL_ONLY, **overrides):
    values = {
        "repo": CORPUS_REPO,
        "commit": commit,
        "change": CORPUS_CHANGE,
        "proposal": CORPUS_PROPOSAL,
        "proof": CORPUS_PROOF,
        "pr": None,
        "outcome": outcome,
        "recorded": "2026-11-07",
        "outcome_url": None,
        "notes": "",
        "evidence": "",
    }
    values.update(overrides)
    if "id" not in values:
        values["id"] = record_id(
            values["repo"], values["commit"], values["change"], values["proposal"]
        )
    return CorpusRecord(**values)


def a_corpus_file(tmp_path, *records, name="corpus.jsonl"):
    path = tmp_path / name
    path.write_text(
        "".join(record.to_json() + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def a_corpus_outcome(corpus, record_id, *extra):
    return main(
        [
            "corpus",
            "outcome",
            "--corpus",
            str(corpus),
            "--id",
            record_id,
            "--outcome",
            "merged",
            *extra,
        ]
    )


# Spec AC3: an outcome update changes the outcome/url/notes and keeps the id.
def test_corpus_outcome_updates_and_keeps_the_id(tmp_path, capsys):
    record = a_stored_record()
    corpus = a_corpus_file(tmp_path, record)

    assert (
        a_corpus_outcome(
            corpus,
            record.id,
            "--outcome-url",
            "https://github.com/o/r/pull/1",
            "--notes",
            "merged by hand",
        )
        == 0
    )

    (updated,) = load_corpus(corpus)
    assert updated.id == record.id
    assert updated.outcome is Outcome.MERGED
    assert updated.outcome_url == "https://github.com/o/r/pull/1"
    assert updated.notes == "merged by hand"
    out = capsys.readouterr().out
    assert record.id in out
    assert "MERGED" in out


# Spec AC3: --json returns the updated record as one object.
def test_corpus_outcome_json_returns_the_updated_record(tmp_path, capsys):
    record = a_stored_record()
    corpus = a_corpus_file(tmp_path, record)

    assert (
        a_corpus_outcome(
            corpus,
            record.id,
            "--outcome-url",
            "https://github.com/o/r/pull/1",
            "--notes",
            "merged by hand",
            "--json",
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["id"] == record.id
    assert payload["outcome"] == "MERGED"
    assert payload["outcome_url"] == "https://github.com/o/r/pull/1"
    assert payload["notes"] == "merged by hand"
    assert captured.out.count("\n") == 1


# Spec AC3: omitted --outcome-url/--notes keep the existing values.
def test_corpus_outcome_keeps_the_existing_url_and_notes(tmp_path):
    record = a_stored_record(
        outcome_url="https://github.com/o/r/pull/1", notes="old note"
    )
    corpus = a_corpus_file(tmp_path, record)

    assert main(
        [
            "corpus",
            "outcome",
            "--corpus",
            str(corpus),
            "--id",
            record.id,
            "--outcome",
            "rejected",
        ]
    ) == 0

    (updated,) = load_corpus(corpus)
    assert updated.outcome is Outcome.REJECTED
    assert updated.outcome_url == "https://github.com/o/r/pull/1"
    assert updated.notes == "old note"


# Spec AC3: an unknown id exits 2 and leaves the file alone.
def test_corpus_outcome_unknown_id_exits_two(tmp_path, capsys):
    record = a_stored_record()
    corpus = a_corpus_file(tmp_path, record)

    assert a_corpus_outcome(corpus, "000000000000") == 2

    captured = capsys.readouterr()
    assert "unknown corpus id" in captured.err
    assert "Traceback" not in captured.err
    assert load_corpus(corpus) == (record,)


# Spec AC3: an unknown outcome token exits 2 and leaves the file alone.
def test_corpus_outcome_unknown_outcome_exits_two(tmp_path, capsys):
    record = a_stored_record()
    corpus = a_corpus_file(tmp_path, record)

    assert main(
        [
            "corpus",
            "outcome",
            "--corpus",
            str(corpus),
            "--id",
            record.id,
            "--outcome",
            "bogus",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert "unknown outcome" in captured.err
    assert "Traceback" not in captured.err
    assert load_corpus(corpus) == (record,)


# Spec AC3/AC7: a --json outcome error is one object on stdout.
def test_corpus_outcome_json_error_is_one_object(tmp_path, capsys):
    record = a_stored_record()
    corpus = a_corpus_file(tmp_path, record)

    assert main(
        [
            "corpus",
            "outcome",
            "--corpus",
            str(corpus),
            "--id",
            record.id,
            "--outcome",
            "bogus",
            "--json",
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["error"]["kind"] == "corpus"
    assert "unknown outcome" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC3: a missing corpus exits 2.
def test_corpus_outcome_missing_corpus_exits_two(tmp_path, capsys):
    assert a_corpus_outcome(tmp_path / "missing.jsonl", "abc") == 2

    err = capsys.readouterr().err
    assert "cannot read corpus" in err
    assert "Traceback" not in err


# Spec AC4: the text report is exactly the benchmark's text.
def test_corpus_report_text_matches_benchmark(tmp_path, capsys):
    records = (a_stored_record(), a_stored_record(commit="commit-two"))
    corpus = a_corpus_file(tmp_path, *records)

    assert main(["corpus", "report", "--corpus", str(corpus)]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == benchmark(records).render_text()


# Spec AC4: the JSON report is exactly the benchmark's JSON.
def test_corpus_report_json_matches_benchmark(tmp_path, capsys):
    records = (a_stored_record(), a_stored_record(commit="commit-two"))
    corpus = a_corpus_file(tmp_path, *records)

    assert main(["corpus", "report", "--corpus", str(corpus), "--json"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == benchmark(records).to_json() + "\n"
    assert captured.out.count("\n") == 1


# Spec AC4/M8: an empty file is a valid zero report with a null rate.
def test_corpus_report_empty_file_is_valid(tmp_path, capsys):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")

    assert main(["corpus", "report", "--corpus", str(corpus), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 0
    assert all(
        stats["merge_rate"] is None for stats in payload["by_level"].values()
    )
    assert set(payload["outcomes"].values()) == {0}

    assert main(["corpus", "report", "--corpus", str(corpus)]) == 0
    assert "0 records" in capsys.readouterr().out


# Spec AC4: a missing corpus exits 2.
def test_corpus_report_missing_corpus_exits_two(tmp_path, capsys):
    assert main(
        ["corpus", "report", "--corpus", str(tmp_path / "missing.jsonl")]
    ) == 2

    err = capsys.readouterr().err
    assert "cannot read corpus" in err
    assert "Traceback" not in err


# Spec AC4/AC7: a malformed corpus is one JSON error object and exit 2.
def test_corpus_report_malformed_corpus_json_is_one_object(tmp_path, capsys):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("{", encoding="utf-8")

    assert main(["corpus", "report", "--corpus", str(corpus), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["error"]["kind"] == "corpus"
    assert "line 1" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


BENCHMARK_CORPUS = (
    Path(__file__).parent.parent.parent / "docs" / "benchmark" / "corpus.jsonl"
)
BENCHMARK_README = BENCHMARK_CORPUS.with_name("README.md")
FHI_COMMIT = "56e69cfa4440aea0a42d016f84e6af336c5e0d3c"
STRIPE_TEMPLATE_COMMIT = "9d9178c47a191112b86a6ce6edd71962faee80d1"


# Spec AC5: the committed seed is exactly the two public M0.3 cases.
def test_benchmark_seed_has_the_two_public_cases():
    records = load_corpus(BENCHMARK_CORPUS)

    assert len(records) == 2
    by_commit = {record.commit: record for record in records}
    assert set(by_commit) == {FHI_COMMIT, STRIPE_TEMPLATE_COMMIT}

    fhi = by_commit[FHI_COMMIT]
    assert fhi.repo == "https://github.com/fighthealthinsurance/fighthealthinsurance"
    assert fhi.recorded == "2026-11-02"
    assert fhi.evidence == "docs/planning/m0-3-first-real-case/evidence.md"
    assert len(fhi.proposal["edits"]) == 3
    assert fhi.proposal["files"] == [
        "fhi_users/auth/rest_auth_views.py",
        "fighthealthinsurance/views.py",
    ]
    assert sum(line.startswith("@@") for line in fhi.proposal["diff"].splitlines()) == 3

    stripe_template = by_commit[STRIPE_TEMPLATE_COMMIT]
    assert stripe_template.repo == "https://github.com/yezz123/stripe-template"
    assert stripe_template.recorded == "2026-10-31"
    assert stripe_template.evidence == "docs/planning/m0-3-real-case/evidence.md"
    assert len(stripe_template.proposal["edits"]) == 2
    assert stripe_template.proposal["files"] == [
        "app/router/v1/payment.py",
        "tests/test_payment.py",
    ]
    assert (
        sum(
            line.startswith("@@")
            for line in stripe_template.proposal["diff"].splitlines()
        )
        == 2
    )

    for record in records:
        assert record.id == record_id(
            record.repo, record.commit, record.change, record.proposal
        )
        assert record.outcome is Outcome.LOCAL_ONLY
        assert record.proof["level"] == "TESTS_PASSED"
        assert record.proof["patch_applied"] is True
        assert record.proof["cause"] is None
        assert record.pr is None
        assert record.change["kind"] == "renamed"
        assert record.change["location"]["method"] == "post"
        assert record.change["location"]["path"] == "/v1/checkout/sessions"
        assert (
            record.change["before"],
            record.change["after"],
        ) == ("payment_method_types", "allowed_payment_method_types")


# Spec AC5: with no real outcomes, known is 0 and every merge rate is null.
def test_benchmark_seed_report_has_no_known_outcomes():
    report = benchmark(load_corpus(BENCHMARK_CORPUS))

    assert report.total == 2
    assert report.by_level[ProofLevel.TESTS_PASSED].count == 2
    assert report.by_level[ProofLevel.TESTS_PASSED].known == 0
    assert all(stats.merge_rate is None for stats in report.by_level.values())
    assert report.outcomes[Outcome.LOCAL_ONLY] == 2


# Spec AC4/AC5: the CLI report over the seed is the benchmark report.
def test_corpus_report_on_the_seed_matches_benchmark(capsys):
    assert (
        main(["corpus", "report", "--corpus", str(BENCHMARK_CORPUS), "--json"])
        == 0
    )

    assert capsys.readouterr().out == (
        benchmark(load_corpus(BENCHMARK_CORPUS)).to_json() + "\n"
    )


# Spec AC5: the README states the method, the cases and the honest no-merge note.
def test_benchmark_readme_documents_the_method_and_no_merge_outcomes():
    text = BENCHMARK_README.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "docs/benchmark/corpus.jsonl" in text
    assert "tenon corpus record" in text
    assert "tenon corpus outcome" in text
    assert "tenon corpus report --corpus docs/benchmark/corpus.jsonl" in text
    assert "no merge outcomes yet" in lowered
    assert "merge rate n/a" in lowered
    for outcome in (
        "pending",
        "merged",
        "rejected",
        "closed",
        "incident",
        "local_only",
    ):
        assert outcome in text
    assert "fighthealthinsurance" in text
    assert "stripe-template" in text
    assert "local" in lowered
    assert "opt-in" in lowered
