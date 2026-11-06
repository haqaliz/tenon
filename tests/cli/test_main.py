"""The CLI entry point: parse, compose the stages, report and return a code."""

import importlib
import json
import os
import subprocess
import sys

import pytest

from tenon.cli import main
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
