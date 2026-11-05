"""The CLI entry point: parse, compose the stages, report and return a code."""

import importlib
import json
import os
import subprocess
import sys

import pytest

from tenon.cli import main
from tenon.detect import diff, load
from tenon.pr import PrDraft, PrRefusal, PrResult, PrStatus
from tenon.prove import ProofLevel

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


# Spec AC5: no check command is UNVERIFIED, not a passed proof.
def test_fix_without_a_check_command_is_unverified(
    a_repo, a_specs, a_no_command_config, capsys
):
    assert (
        a_fix(a_repo, a_specs, "--config", str(a_no_command_config)) == 1
    )
    out = capsys.readouterr().out
    assert "Proof: UNVERIFIED" in out
    assert "Cause: NO_TESTS_FOUND" in out


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
    assert payload["results"][0]["proof"]["cause"] == "NO_TESTS_FOUND"
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
        proposal, proof, repo, *, remote, allow_unverified=False, unanalyzed=()
    ):
        calls.append(
            {
                "proposal": proposal,
                "proof": proof,
                "repo": repo,
                "remote": remote,
                "allow_unverified": allow_unverified,
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
    assert call["allow_unverified"] is False
    assert call["unanalyzed"] == expected_unanalyzed


# Spec AC6: the CLI does not pre-gate UNVERIFIED; the writer refuses and says so.
def test_fix_open_pr_unverified_is_refused_by_the_writer(
    a_repo, a_specs, a_no_command_config, monkeypatch, capsys
):
    write_pr, calls = a_recorder(
        lambda proof: a_pr(
            proof, PrStatus.REFUSED, PrRefusal.UNVERIFIED_NOT_ALLOWED
        )
    )
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

    assert "PR refused: UNVERIFIED_NOT_ALLOWED" in capsys.readouterr().out
    assert calls[0]["allow_unverified"] is False


# Spec AC6: --allow-unverified reaches the writer; --require only moves the exit.
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
    assert calls[0]["allow_unverified"] is True


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


# Spec AC8/M6: only the shipped proof levels parse; the rest names T7.
def test_unknown_require_names_t7(a_repo, a_specs, capsys):
    assert a_fix(a_repo, a_specs, "--require", "BY_HAND") == 2

    err = capsys.readouterr().err
    assert "--require" in err
    assert "T7" in err


# Spec M10: an unexpected failure is an internal 1, not a traceback.
def test_unexpected_failure_is_internal(a_repo, a_specs, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "diff", boom)

    assert a_check(a_repo, a_specs) == 1

    captured = capsys.readouterr()
    assert "tenon: internal: boom" in captured.err
    assert "Traceback" not in captured.err


def a_run_module_check(repo, specs, seed):
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
