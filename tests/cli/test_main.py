"""The CLI entry point: parse, compose the stages, report and return a code."""

import importlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from tenon.cli import CliConfig, main
from tenon.corpus import (
    CorpusRecord,
    Outcome,
    benchmark,
    load_corpus,
    record_id,
)
from tenon.detect import (
    Change,
    ChangeKind,
    Location,
    diff,
    diff_mcp,
    load,
    load_mcp,
)
from tenon.locate import (
    CSharpLocateConfig,
    GoLocateConfig,
    LocateConfig,
    RustLocateConfig,
    TsLocateConfig,
)
from tenon.pr import (
    InstalledRepo,
    PrDraft,
    PrRefusal,
    PrResult,
    PrStatus,
    RemoteError,
    StaticToken,
    clone_repo as real_clone_repo,
)
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


# Spec AC7: an operation flag overrides the configured mapping.
def test_operation_flag_overrides_config(a_repo, a_endpoint_specs, capsys):
    config = (a_repo / "tenon.toml").read_text(encoding="utf-8")
    (a_repo / "tenon.toml").write_text(
        config
        + '\n[locate.operations]\n"POST /v1/charges" = "StripeClient.charges.create"\n',
        encoding="utf-8",
    )

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


# Spec AC1/AC3: [locate] language = "rust" is enough; no flag is needed.
def test_check_rust_language_from_the_config(tmp_path, a_specs, capsys):
    (tmp_path / "tenon.toml").write_text(
        '[locate]\nlanguage = "rust"\nsdk_package = "stripe"\n'
    )

    assert a_check(tmp_path, a_specs) == 1
    assert "NO_SDK_IMPORT" in capsys.readouterr().out


# Spec AC1: --language rust is a parser choice; no config builds the Rust config.
def test_missing_config_with_language_rust_uses_sdk_package(
    tmp_path, a_specs, capsys
):
    assert (
        a_check(tmp_path, a_specs, "--language", "rust", "--sdk-package", "stripe")
        == 1
    )
    assert "NO_SDK_IMPORT" in capsys.readouterr().out


# Spec AC3: a bad Rust crate from the flag is one named config error.
def test_language_rust_rejects_a_bad_crate(tmp_path, a_specs, capsys):
    assert (
        a_check(tmp_path, a_specs, "--language", "rust", "--sdk-package", "a::b")
        == 2
    )

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Rust crate" in err
    assert "Traceback" not in err


# Spec AC3: MCP with Rust is one named error.
def test_language_rust_with_source_mcp_is_named(a_mcp_repo, a_mcp_specs, capsys):
    assert (
        a_check(a_mcp_repo, a_mcp_specs, "--source", "mcp", "--language", "rust")
        == 2
    )

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


# Spec AC1: --language go with no config builds GoLocateConfig from the flags.
def test_missing_config_with_language_go_uses_sdk_package(
    tmp_path, a_same_specs
):
    assert (
        a_check(
            tmp_path,
            a_same_specs,
            "--language",
            "go",
            "--sdk-package",
            "github.com/stripe/stripe-go/v76",
            "--package-name",
            "stripe",
        )
        == 0
    )


# Spec AC3: a bad Go import root from the flag is one named config error.
def test_language_go_rejects_a_bad_root(tmp_path, a_specs, capsys):
    assert (
        a_check(tmp_path, a_specs, "--language", "go", "--sdk-package", "/stripe")
        == 2
    )

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Go import root" in err
    assert "Traceback" not in err


# Spec AC3: a bad Go package name from the flag is one named config error.
def test_language_go_rejects_a_bad_package_name(tmp_path, a_specs, capsys):
    assert (
        a_check(
            tmp_path,
            a_specs,
            "--language",
            "go",
            "--sdk-package",
            "github.com/stripe/stripe-go/v76",
            "--package-name",
            "not-a-name",
        )
        == 2
    )

    err = capsys.readouterr().err
    assert "package_name" in err
    assert "Go identifier" in err
    assert "Traceback" not in err


# Spec AC3: MCP with Go is one named error.
def test_language_go_with_source_mcp_is_named(a_mcp_repo, a_mcp_specs, capsys):
    assert (
        a_check(a_mcp_repo, a_mcp_specs, "--source", "mcp", "--language", "go")
        == 2
    )

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


# Spec AC4: --receiver is a repeatable common check/fix flag.
@pytest.mark.parametrize("command", ["check", "fix"])
def test_receiver_is_a_repeatable_common_flag(command):
    args = cli_main._parser().parse_args(
        [
            command,
            ".",
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--receiver",
            "a=b",
            "--receiver",
            "c=d",
        ]
    )

    assert args.receiver == ["a=b", "c=d"]


# Spec AC4: --receiver reaches the Rust config and wins over the file.
def test_receiver_flag_reaches_the_rust_config(tmp_path):
    (tmp_path / "tenon.toml").write_text(
        '[locate]\nlanguage = "rust"\nsdk_package = "stripe"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = "FileClient"\n'
    )
    args = cli_main._parser().parse_args(
        [
            "check",
            str(tmp_path),
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--receiver",
            "stripe.NewClient=FlagClient",
            "--receiver",
            "stripe.NewOther=Other",
        ]
    )

    config = cli_main._config(args)

    assert isinstance(config.locate, RustLocateConfig)
    assert dict(config.locate.receivers) == {
        "stripe.NewClient": "FlagClient",
        "stripe.NewOther": "Other",
    }


# Spec AC5: the no-config --sdk-package fallback builds the receiver mapping.
@pytest.mark.parametrize(
    ("language", "sdk_package", "expected_type"),
    [
        ("python", "stripe", LocateConfig),
        ("ts", "stripe", TsLocateConfig),
        ("rust", "stripe", RustLocateConfig),
        ("go", "github.com/stripe/stripe-go/v76", GoLocateConfig),
        ("csharp", "Stripe", CSharpLocateConfig),
    ],
)
def test_missing_config_fallback_builds_the_receivers(
    tmp_path, language, sdk_package, expected_type
):
    args = cli_main._parser().parse_args(
        [
            "check",
            str(tmp_path),
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--language",
            language,
            "--sdk-package",
            sdk_package,
            "--receiver",
            "stripe.NewClient=Client",
        ]
    )

    config = cli_main._config(args)

    assert isinstance(config.locate, expected_type)
    assert dict(config.locate.receivers) == {"stripe.NewClient": "Client"}


# Spec AC4: --receiver reaches Python, TS and C# and wins over the file.
@pytest.mark.parametrize(
    ("language", "sdk_package", "expected_type"),
    [
        ("python", "stripe", LocateConfig),
        ("ts", "stripe", TsLocateConfig),
        ("csharp", "Stripe", CSharpLocateConfig),
    ],
)
def test_receiver_flag_reaches_every_language(
    tmp_path, language, sdk_package, expected_type
):
    (tmp_path / "tenon.toml").write_text(
        f'[locate]\nlanguage = "{language}"\nsdk_package = "{sdk_package}"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = "FileClient"\n'
    )
    args = cli_main._parser().parse_args(
        [
            "check",
            str(tmp_path),
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--receiver",
            "stripe.NewClient=FlagClient",
            "--receiver",
            "stripe.NewOther=Other",
        ]
    )

    config = cli_main._config(args)

    assert isinstance(config.locate, expected_type)
    assert dict(config.locate.receivers) == {
        "stripe.NewClient": "FlagClient",
        "stripe.NewOther": "Other",
    }


# Spec AC4: a malformed --receiver is one named config error.
def test_receiver_flag_rejects_a_malformed_pair(a_repo, a_specs, capsys):
    assert (
        a_check(
            a_repo,
            a_specs,
            "--receiver",
            "missing-equals",
        )
        == 2
    )

    err = capsys.readouterr().err
    assert "--receiver" in err
    assert "unrecognized" not in err
    assert "Traceback" not in err


# Spec AC1: --language csharp is a parser choice.
def test_csharp_language_is_a_parser_choice():
    args = cli_main._parser().parse_args(
        [
            "check",
            ".",
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--language",
            "csharp",
        ]
    )

    assert args.language == "csharp"


# Spec AC1: --language csharp with no config builds the C# config from the flags.
def test_missing_config_with_language_csharp_uses_sdk_package(
    tmp_path, a_same_specs
):
    assert (
        a_check(
            tmp_path,
            a_same_specs,
            "--language",
            "csharp",
            "--sdk-package",
            "Stripe",
        )
        == 0
    )


# Spec AC1: --language csharp with a changed spec dispatches the C# locator.
def test_missing_config_with_language_csharp_dispatches(
    tmp_path, a_specs, capsys
):
    assert (
        a_check(
            tmp_path,
            a_specs,
            "--language",
            "csharp",
            "--sdk-package",
            "Stripe",
        )
        == 1
    )
    assert "NO_SDK_IMPORT" in capsys.readouterr().out


# Spec AC3: a bad C# namespace from the flag is one named config error.
def test_language_csharp_rejects_a_bad_namespace(tmp_path, a_specs, capsys):
    assert (
        a_check(
            tmp_path, a_specs, "--language", "csharp", "--sdk-package", "a/b"
        )
        == 2
    )

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "C# namespace" in err
    assert "Traceback" not in err


# Spec AC3: MCP with C# is one named error.
def test_language_csharp_with_source_mcp_is_named(
    a_mcp_repo, a_mcp_specs, capsys
):
    assert (
        a_check(
            a_mcp_repo, a_mcp_specs, "--source", "mcp", "--language", "csharp"
        )
        == 2
    )

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


LOCATE_CONFIGS = {
    "python": LocateConfig,
    "ts": TsLocateConfig,
    "rust": RustLocateConfig,
    "go": GoLocateConfig,
    "csharp": CSharpLocateConfig,
}


def a_rust_change():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer="#/components/schemas/Charge/properties"),
        before="amount",
        after="amount_total",
        breaking=True,
        confidence="inferred",
    )


# Spec AC5: the one table names each language's locator.
def test_the_locator_table_names_each_locator():
    assert cli_main.LOCATORS == {
        "python": cli_main.locate,
        "ts": cli_main.locate_ts,
        "rust": cli_main.locate_rust,
        "go": cli_main.locate_go,
        "csharp": cli_main.locate_csharp,
    }


# Spec AC5: one table sends each language to its own locator.
@pytest.mark.parametrize("language", ["python", "ts", "rust", "go", "csharp"])
def test_locate_dispatches_each_language(language, monkeypatch, tmp_path):
    seen = []
    marker = object()

    def spy(change, repo, config):
        seen.append((change, repo, config))
        return marker

    monkeypatch.setitem(cli_main.LOCATORS, language, spy)
    change = a_rust_change()
    config = CliConfig(
        locate=LOCATE_CONFIGS[language](sdk_package="stripe"),
        language=language,
    )

    assert cli_main._locate(change, tmp_path, config) is marker
    assert seen == [(change, tmp_path, config.locate)]


# Spec AC2: --package-name is a common check/fix flag.
@pytest.mark.parametrize("command", ["check", "fix"])
def test_package_name_is_a_common_flag(command):
    args = cli_main._parser().parse_args(
        [
            command,
            ".",
            "--old",
            "old.yaml",
            "--new",
            "new.yaml",
            "--package-name",
            "stripe",
        ]
    )

    assert args.package_name == "stripe"


# Spec AC1: --language go with no config dispatches the Go locator.
def test_missing_config_with_language_go_locates(tmp_path, a_specs, capsys):
    assert (
        a_check(
            tmp_path,
            a_specs,
            "--language",
            "go",
            "--sdk-package",
            "github.com/stripe/stripe-go/v76",
            "--package-name",
            "stripe",
        )
        == 1
    )
    assert "NO_SDK_IMPORT" in capsys.readouterr().out


# Spec AC1/AC3: the temp tenon.toml selects Rust; the struct field is reported.
def test_check_rust_reports_the_struct_field(a_rust_repo, capsys):
    assert (
        a_check(
            a_rust_repo.repo,
            a_rust_repo.specs,
            "--field",
            "Charge.amount=amount_cents",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "src/lib.rs:5:9" in out
    assert "amount_cents" in out
    assert "1 change" in out


# Spec AC1: the Rust check uses the shipped JSON envelope.
def test_check_rust_json_has_the_exact_envelope(a_rust_repo, capsys):
    assert (
        a_check(
            a_rust_repo.repo,
            a_rust_repo.specs,
            "--field",
            "Charge.amount=amount_cents",
            "--json",
        )
        == 1
    )

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    (result,) = payload["results"]
    assert result["reason"] is None
    assert {
        (site["path"], site["line"], site["column"], site["symbol"])
        for site in result["certain"]
    } == {(*a_rust_repo.site, "amount_cents")}
    assert out.count("\n") == 1


# Spec AC1: an endpoint removal reports the associated call site.
def test_check_rust_reports_the_removed_endpoint_call(a_rust_repo, capsys):
    assert (
        a_check(
            a_rust_repo.repo,
            a_rust_repo.endpoint_specs,
            "--operation",
            "POST /v1/charges=Charge.create",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "src/lib.rs:9:5" in out
    assert "create" in out


# Spec AC2: fix proposes the rename, proves it and leaves the fixture alone.
def test_fix_rust_proposes_and_proves_the_rename(
    a_rust_repo, a_snapshot, capsys
):
    before = a_snapshot(a_rust_repo.repo)

    assert (
        a_fix(
            a_rust_repo.repo,
            a_rust_repo.fix_specs,
            "--check",
            shlex.join([sys.executable, "-c", "pass"]),
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "-        amount_cents: amount," in out
    assert "+        amount_total: amount," in out
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(a_rust_repo.repo) == before


# Spec AC1: the temp tenon.toml selects Go; the literal key is reported.
def test_check_go_reports_the_literal_field(a_go_repo, capsys):
    assert (
        a_check(
            a_go_repo.repo,
            a_go_repo.specs,
            "--field",
            "ChargeParams.AmountCents=AmountCents",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "main.go:9:36" in out
    assert "AmountCents" in out
    assert "1 change, 1 certain site, 0 ambiguity groups" in out


# Spec AC1: the Go check uses the shipped JSON envelope.
def test_check_go_json_has_the_exact_envelope(a_go_repo, capsys):
    assert (
        a_check(
            a_go_repo.repo,
            a_go_repo.specs,
            "--field",
            "ChargeParams.AmountCents=AmountCents",
            "--json",
        )
        == 1
    )

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    (result,) = payload["results"]
    assert result["reason"] is None
    assert {
        (site["path"], site["line"], site["column"], site["symbol"])
        for site in result["certain"]
    } == {(*a_go_repo.site, "AmountCents")}
    assert out.count("\n") == 1


# Spec AC1: an endpoint removal reports the associated Go call site.
def test_check_go_reports_the_removed_endpoint_call(a_go_repo, capsys):
    assert (
        a_check(
            a_go_repo.repo,
            a_go_repo.endpoint_specs,
            "--operation",
            "POST /v1/charges=charge.New",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "main.go:10:5" in out
    assert "New" in out


# Spec AC2: fix proposes the rename, proves it and leaves the fixture alone.
def test_fix_go_proposes_and_proves_the_rename(
    a_go_repo, a_snapshot, capsys
):
    before = a_snapshot(a_go_repo.repo)

    assert (
        a_fix(
            a_go_repo.repo,
            a_go_repo.fix_specs,
            "--check",
            shlex.join([sys.executable, "-c", "pass"]),
        )
        == 0
    )

    out = capsys.readouterr().out
    assert (
        '-    params := &stripe.ChargeParams{AmountCents: 100, Currency: "usd"}'
        in out
    )
    assert (
        '+    params := &stripe.ChargeParams{AmountTotal: 100, Currency: "usd"}'
        in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(a_go_repo.repo) == before


# Spec AC1: the temp tenon.toml selects C#; the initializer property is reported.
def test_check_csharp_reports_the_initializer_property(a_csharp_repo, capsys):
    assert (
        a_check(
            a_csharp_repo.repo,
            a_csharp_repo.specs,
            "--language",
            "csharp",
            "--field",
            "ChargeCreateOptions.AmountCents=AmountCents",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "Program.cs:10:49" in out
    assert "AmountCents" in out
    assert "1 change, 1 certain site, 0 ambiguity groups" in out


# Spec AC1: the C# check uses the shipped JSON envelope.
def test_check_csharp_json_has_the_exact_envelope(a_csharp_repo, capsys):
    assert (
        a_check(
            a_csharp_repo.repo,
            a_csharp_repo.specs,
            "--language",
            "csharp",
            "--field",
            "ChargeCreateOptions.AmountCents=AmountCents",
            "--json",
        )
        == 1
    )

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload) == {"command", "results", "summary"}
    assert payload["command"] == "check"
    (result,) = payload["results"]
    assert result["reason"] is None
    assert {
        (site["path"], site["line"], site["column"], site["symbol"])
        for site in result["certain"]
    } == {(*a_csharp_repo.site, "AmountCents")}
    assert out.count("\n") == 1


# Spec AC1: an endpoint removal reports the associated C# call site.
def test_check_csharp_reports_the_removed_endpoint_call(a_csharp_repo, capsys):
    assert (
        a_check(
            a_csharp_repo.repo,
            a_csharp_repo.endpoint_specs,
            "--language",
            "csharp",
            "--operation",
            "POST /v1/charges=ChargeService.Create",
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "Program.cs:12:9" in out
    assert "Create" in out


# Spec AC2: fix proposes the rename, proves it and leaves the fixture alone.
def test_fix_csharp_proposes_and_proves_the_rename(
    a_csharp_repo, a_snapshot, capsys
):
    before = a_snapshot(a_csharp_repo.repo)

    assert (
        a_fix(
            a_csharp_repo.repo,
            a_csharp_repo.fix_specs,
            "--language",
            "csharp",
            "--check",
            shlex.join([sys.executable, "-c", "pass"]),
        )
        == 0
    )

    out = capsys.readouterr().out
    assert (
        '-        var options = new ChargeCreateOptions { AmountCents = 100, '
        'Currency = "usd" };' in out
    )
    assert (
        '+        var options = new ChargeCreateOptions { AmountTotal = 100, '
        'Currency = "usd" };' in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(a_csharp_repo.repo) == before


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
            transport=None,
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


def a_app_fix(repo, specs, *extra):
    return a_fix(repo, specs, "--open-pr", "--remote", "app", *extra)


def a_app_flag_inputs(key):
    return (
        "--app-id",
        "123",
        "--app-installation-id",
        "456",
        "--app-private-key",
        str(key),
    )


# Spec AC3: every app input falls back to its environment variable.
def test_fix_open_pr_remote_app_reads_the_env(
    a_repo, a_specs, tmp_path, monkeypatch, a_app_env
):
    key = a_app_key(tmp_path)
    a_app_env.setenv("TENON_GITHUB_APP_ID", "111")
    a_app_env.setenv("TENON_GITHUB_APP_INSTALLATION_ID", "222")
    a_app_env.setenv("TENON_GITHUB_APP_PRIVATE_KEY", str(key))
    a_app_env.setenv("TENON_GITHUB_API_URL", "https://env.example/api/v3")
    tokens, remotes = a_app_recorders(monkeypatch)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_app_fix(a_repo, a_specs) == 0

    (token,) = tokens
    assert token["app_id"] == "111"
    assert token["installation_id"] == "222"
    assert token["private_key_pem"] == key.read_text(encoding="utf-8")
    assert token["api_url"] == "https://env.example/api/v3"
    (remote,) = remotes
    assert remote["provider"].record is token
    assert remote["api_url"] == "https://env.example/api/v3"
    assert calls[0]["remote"].record is remote


# Spec AC3: a flag wins over the environment.
def test_fix_open_pr_remote_app_flags_win_over_the_env(
    a_repo, a_specs, tmp_path, monkeypatch, a_app_env
):
    env_key = a_app_key(tmp_path, "env.pem")
    flag_key = a_app_key(tmp_path, "flag.pem")
    a_app_env.setenv("TENON_GITHUB_APP_ID", "111")
    a_app_env.setenv("TENON_GITHUB_APP_INSTALLATION_ID", "222")
    a_app_env.setenv("TENON_GITHUB_APP_PRIVATE_KEY", str(env_key))
    a_app_env.setenv("TENON_GITHUB_API_URL", "https://env.example/api/v3")
    tokens, remotes = a_app_recorders(monkeypatch)
    monkeypatch.setattr(cli_main, "write_pr", a_recorder(a_pr)[0])

    assert (
        a_app_fix(
            a_repo,
            a_specs,
            *a_app_flag_inputs(flag_key),
            "--api-url",
            "https://flag.example/api/v3",
        )
        == 0
    )

    (token,) = tokens
    assert token["app_id"] == "123"
    assert token["installation_id"] == "456"
    assert token["private_key_pem"] == flag_key.read_text(encoding="utf-8")
    assert token["api_url"] == "https://flag.example/api/v3"
    (remote,) = remotes
    assert remote["api_url"] == "https://flag.example/api/v3"


# Spec AC2/AC3: with no --api-url, the public GitHub API is the default.
def test_fix_open_pr_remote_app_uses_the_default_api_url(
    a_repo, a_specs, tmp_path, monkeypatch, a_app_env
):
    key = a_app_key(tmp_path)
    tokens, remotes = a_app_recorders(monkeypatch)
    monkeypatch.setattr(cli_main, "write_pr", a_recorder(a_pr)[0])

    assert a_app_fix(a_repo, a_specs, *a_app_flag_inputs(key)) == 0

    assert tokens[0]["api_url"] == "https://api.github.com"
    assert remotes[0]["api_url"] == "https://api.github.com"


# Spec AC4: each missing app input is exit 2, named, and builds nothing.
@pytest.mark.parametrize(
    ("omitted", "message"),
    [
        ("--app-id", "--app-id or TENON_GITHUB_APP_ID"),
        (
            "--app-installation-id",
            "--app-installation-id or TENON_GITHUB_APP_INSTALLATION_ID",
        ),
        (
            "--app-private-key",
            "--app-private-key or TENON_GITHUB_APP_PRIVATE_KEY",
        ),
    ],
)
def test_fix_open_pr_remote_app_missing_input_is_usage(
    omitted,
    message,
    a_repo,
    a_specs,
    tmp_path,
    monkeypatch,
    a_app_env,
    capsys,
):
    key = a_app_key(tmp_path)
    inputs = {
        "--app-id": "123",
        "--app-installation-id": "456",
        "--app-private-key": str(key),
    }
    del inputs[omitted]
    flat = [part for pair in inputs.items() for part in pair]
    tokens, remotes = a_app_recorders(monkeypatch)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_app_fix(a_repo, a_specs, *flat) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert tokens == [] and remotes == [] and calls == []


# Spec AC4: an unreadable private key is exit 2 and names the path.
def test_fix_open_pr_remote_app_unreadable_key_is_usage(
    a_repo, a_specs, tmp_path, monkeypatch, a_app_env, capsys
):
    missing = tmp_path / "missing.pem"
    tokens, remotes = a_app_recorders(monkeypatch)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_app_fix(
            a_repo,
            a_specs,
            "--app-id",
            "123",
            "--app-installation-id",
            "456",
            "--app-private-key",
            str(missing),
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read the app private key" in captured.err
    assert str(missing) in captured.err
    assert "Traceback" not in captured.err
    assert tokens == [] and remotes == [] and calls == []


# Spec AC4: an explicit --remote without --open-pr is a usage error.
@pytest.mark.parametrize("remote", ["gh", "app"])
def test_fix_remote_without_open_pr_is_usage(
    remote, a_repo, a_specs, monkeypatch, capsys
):
    def bomb():
        raise AssertionError("no remote may be constructed")

    monkeypatch.setattr(cli_main, "GitGhRemote", bomb)
    monkeypatch.setattr(cli_main, "GitHubAppRemote", bomb)

    assert a_fix(a_repo, a_specs, "--remote", remote) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--open-pr" in captured.err
    assert "Traceback" not in captured.err


# Spec AC4/AC5: a --json input error is one object on stdout, never a traceback.
@pytest.mark.parametrize(
    "omitted", ["--app-id", "--app-installation-id", "--app-private-key"]
)
def test_fix_open_pr_remote_app_json_error_is_one_object(
    omitted, a_repo, a_specs, tmp_path, monkeypatch, a_app_env, capsys
):
    key = a_app_key(tmp_path)
    inputs = {
        "--app-id": "123",
        "--app-installation-id": "456",
        "--app-private-key": str(key),
    }
    del inputs[omitted]
    flat = [part for pair in inputs.items() for part in pair]
    a_app_recorders(monkeypatch)
    monkeypatch.setattr(cli_main, "write_pr", a_recorder(a_pr)[0])

    assert a_app_fix(a_repo, a_specs, *flat, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert omitted in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC4/AC5: --remote without --open-pr is the same one-object error.
def test_fix_remote_without_open_pr_json_is_one_object(
    a_repo, a_specs, capsys
):
    assert a_fix(a_repo, a_specs, "--remote", "app", "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert "--open-pr" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


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


PROOF_BASIC = Path(__file__).parent.parent / "fixtures" / "repos" / "proof-basic"
RUST_BASIC = Path(__file__).parent.parent / "fixtures" / "repos" / "rust-basic"
GO_BASIC = Path(__file__).parent.parent / "fixtures" / "repos" / "go-basic"
CSHARP_BASIC = (
    Path(__file__).parent.parent / "fixtures" / "repos" / "csharp-basic"
)
GO_ROOT = "github.com/stripe/stripe-go/v76"
PROVIDER_CHECK = [sys.executable, "-c", "import acme.billing"]
PROVIDER_OLD = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
"""
PROVIDER_NEW = PROVIDER_OLD.replace("amount:", "amount_cents:")
PROVIDER_MIXED = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount_cents:
          type: integer
        currency:
          type: string
"""
RUST_PROVIDER_OLD = PROVIDER_OLD.replace("amount:", "amount_cents:")
RUST_PROVIDER_NEW = PROVIDER_OLD.replace("amount:", "amount_total:")
GO_PROVIDER_OLD = """\
openapi: 3.1.0
components:
  schemas:
    ChargeParams:
      type: object
      properties:
        AmountCents:
          type: integer
"""
GO_PROVIDER_NEW = GO_PROVIDER_OLD.replace("AmountCents:", "AmountTotal:")
CSHARP_PROVIDER_OLD = """\
openapi: 3.1.0
components:
  schemas:
    ChargeCreateOptions:
      type: object
      properties:
        AmountCents:
          type: integer
"""
CSHARP_PROVIDER_NEW = CSHARP_PROVIDER_OLD.replace(
    "AmountCents:", "AmountTotal:"
)


def a_bundle(
    tmp_path, *, old_text=PROVIDER_OLD, new_text=PROVIDER_NEW, **overrides
):
    """One temp provider bundle over the proof-basic repo's acme.client SDK."""
    (tmp_path / "old.yaml").write_text(old_text, encoding="utf-8")
    (tmp_path / "new.yaml").write_text(new_text, encoding="utf-8")
    data = {
        "provider": "acme",
        "migration": "amount-cents",
        "source": "openapi",
        "language": "python",
        "old": "old.yaml",
        "new": "new.yaml",
        "locate": {"sdk_package": "acme.client"},
        "command": PROVIDER_CHECK,
    }
    data.update(overrides)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def a_rust_bundle(tmp_path):
    """One temp Rust provider bundle over the rust-basic fixture."""
    (tmp_path / "old.yaml").write_text(RUST_PROVIDER_OLD, encoding="utf-8")
    (tmp_path / "new.yaml").write_text(RUST_PROVIDER_NEW, encoding="utf-8")
    data = {
        "provider": "stripe",
        "migration": "amount-total",
        "source": "openapi",
        "language": "rust",
        "old": "old.yaml",
        "new": "new.yaml",
        "locate": {
            "sdk_package": "stripe",
            "fields": {"Charge.amount": "amount_cents"},
        },
        "check": [sys.executable, "-c", "pass"],
    }
    path = tmp_path / "rust-bundle.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def a_go_bundle(tmp_path):
    """One temp Go provider bundle over the go-basic fixture."""
    (tmp_path / "old.yaml").write_text(GO_PROVIDER_OLD, encoding="utf-8")
    (tmp_path / "new.yaml").write_text(GO_PROVIDER_NEW, encoding="utf-8")
    data = {
        "provider": "stripe",
        "migration": "amount-total",
        "source": "openapi",
        "language": "go",
        "old": "old.yaml",
        "new": "new.yaml",
        "locate": {
            "sdk_package": GO_ROOT,
            "package_name": "stripe",
            "fields": {"ChargeParams.AmountCents": "AmountCents"},
        },
        "check": [sys.executable, "-c", "pass"],
    }
    path = tmp_path / "go-bundle.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def a_csharp_bundle(tmp_path):
    """One temp C# provider bundle over the csharp-basic fixture."""
    (tmp_path / "old.yaml").write_text(CSHARP_PROVIDER_OLD, encoding="utf-8")
    (tmp_path / "new.yaml").write_text(CSHARP_PROVIDER_NEW, encoding="utf-8")
    data = {
        "provider": "stripe",
        "migration": "amount-total",
        "source": "openapi",
        "language": "csharp",
        "old": "old.yaml",
        "new": "new.yaml",
        "locate": {
            "sdk_package": "Stripe",
            "fields": {"ChargeCreateOptions.AmountCents": "AmountCents"},
        },
        "check": [sys.executable, "-c", "pass"],
    }
    path = tmp_path / "csharp-bundle.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def a_provider(bundle, *extra, repo=PROOF_BASIC, remote=None):
    return main(
        ["provider", "migrate", str(repo), "--bundle", str(bundle), *extra],
        remote=remote,
    )


# Spec AC1: a valid bundle runs the fix pipeline on the fixture and leaves it alone.
def test_provider_migrate_passing_bundle_exits_zero(a_snapshot, tmp_path, capsys):
    bundle = a_bundle(tmp_path)
    before = a_snapshot(PROOF_BASIC)

    assert a_provider(bundle) == 0

    out = capsys.readouterr().out
    assert (
        '+    return client.charges.create(amount_cents=amount, currency="usd")'
        in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(PROOF_BASIC) == before


# Spec AC4: a Rust bundle runs through provider migrate and leaves the repo alone.
def test_provider_migrate_rust_bundle_exits_zero(
    a_snapshot, tmp_path, capsys
):
    bundle = a_rust_bundle(tmp_path)
    before = a_snapshot(RUST_BASIC)

    assert a_provider(bundle, repo=RUST_BASIC) == 0

    out = capsys.readouterr().out
    assert "-        amount_cents: amount," in out
    assert "+        amount_total: amount," in out
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(RUST_BASIC) == before


# Spec AC4: a Go bundle runs through provider migrate and leaves the repo alone.
def test_provider_migrate_go_bundle_exits_zero(
    a_snapshot, tmp_path, capsys
):
    bundle = a_go_bundle(tmp_path)
    before = a_snapshot(GO_BASIC)

    assert a_provider(bundle, repo=GO_BASIC) == 0

    out = capsys.readouterr().out
    assert (
        '-    params := &stripe.ChargeParams{AmountCents: 100, Currency: "usd"}'
        in out
    )
    assert (
        '+    params := &stripe.ChargeParams{AmountTotal: 100, Currency: "usd"}'
        in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(GO_BASIC) == before


# Spec AC4: a C# bundle runs through provider migrate and leaves the repo alone.
def test_provider_migrate_csharp_bundle_exits_zero(
    a_snapshot, tmp_path, capsys
):
    bundle = a_csharp_bundle(tmp_path)
    before = a_snapshot(CSHARP_BASIC)

    assert a_provider(bundle, repo=CSHARP_BASIC) == 0

    out = capsys.readouterr().out
    assert (
        '-        var options = new ChargeCreateOptions { AmountCents = 100, '
        'Currency = "usd" };' in out
    )
    assert (
        '+        var options = new ChargeCreateOptions { AmountTotal = 100, '
        'Currency = "usd" };' in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert a_snapshot(CSHARP_BASIC) == before


# Spec AC1: a red check is exit 1 and the proof names the failure.
def test_provider_migrate_red_check_exits_one(tmp_path, capsys):
    bundle = a_bundle(
        tmp_path, command=[sys.executable, "-c", "raise SystemExit(1)"]
    )

    assert a_provider(bundle) == 1

    out = capsys.readouterr().out
    assert "Proof: UNVERIFIED" in out
    assert "Cause: TESTS_FAILED_BEFORE" in out


# Spec AC1: the provider and migrate help screens are zeros.
@pytest.mark.parametrize(
    "argv", [["provider", "--help"], ["provider", "migrate", "--help"]]
)
def test_provider_help_returns_zero(argv, capsys):
    assert main(argv) == 0
    assert "usage: tenon provider" in capsys.readouterr().out


# Spec AC2: --check overrides the bundle's (empty) command.
def test_provider_check_flag_overrides_the_bundle_command(tmp_path, capsys):
    bundle = a_bundle(tmp_path, command=[])

    assert a_provider(bundle) == 1
    assert "Cause: NO_PROOF_COMMAND" in capsys.readouterr().out

    assert a_provider(bundle, "--check", shlex.join(PROVIDER_CHECK)) == 0
    assert "Proof: TESTS_PASSED" in capsys.readouterr().out


# Spec AC2: the bundle's require sets the bar; --require overrides it.
def test_provider_require_comes_from_the_bundle_and_the_flag(tmp_path, capsys):
    bundle = a_bundle(tmp_path, command=[], require="UNVERIFIED")

    assert a_provider(bundle) == 0
    assert "Proof: UNVERIFIED" in capsys.readouterr().out

    assert a_provider(bundle, "--require", "TESTS_PASSED") == 1
    assert "Proof: UNVERIFIED" in capsys.readouterr().out


# Spec AC2: the bundle's stage commands reach one plan.
def test_provider_bundle_commands_reach_the_plan(tmp_path, monkeypatch):
    bundle = a_bundle(tmp_path)
    seen = []

    def prove_plan_spy(proposal, repo, plan):
        seen.append(plan)
        return a_green_proof()

    monkeypatch.setattr(cli_main, "prove_plan", prove_plan_spy)

    assert a_provider(bundle) == 0
    assert seen == [ProofPlan(tests=tuple(PROVIDER_CHECK))]


# Spec AC2/S3: the bundle's breaking_only filters the diff.
def test_provider_breaking_only_filters_changes(tmp_path, capsys):
    breaking = a_bundle(tmp_path, new_text=PROVIDER_MIXED, breaking_only=True)

    assert a_provider(breaking) == 0
    assert "1 change, 1 proposal" in capsys.readouterr().out

    everything = a_bundle(tmp_path, new_text=PROVIDER_MIXED)

    assert a_provider(everything) == 1
    assert "2 changes" in capsys.readouterr().out


# Spec AC3/M5: the text is the provider header then the fix report.
def test_provider_text_has_the_header_and_the_fix_report(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle) == 0

    out = capsys.readouterr().out
    assert out.startswith("provider: acme\nmigration: amount-cents\n\n")
    assert (
        '+    return client.charges.create(amount_cents=amount, currency="usd")'
        in out
    )
    assert "Proof: TESTS_PASSED" in out
    assert "1 change, 1 proposal" in out


# Spec AC3/M5: the provider JSON has the exact keys and the fix item shape.
def test_provider_json_has_the_exact_envelope(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle, "--json") == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload) == {
        "command",
        "provider",
        "migration",
        "repo",
        "results",
        "summary",
    }
    assert payload["command"] == "provider"
    assert payload["provider"] == "acme"
    assert payload["migration"] == "amount-cents"
    assert payload["repo"] == str(PROOF_BASIC)
    (result,) = payload["results"]
    assert set(result) == {"change", "locate", "proposal", "proof", "pr"}
    assert result["proof"]["level"] == "TESTS_PASSED"
    assert result["pr"] is None
    assert payload["summary"] == {
        "changes": 1,
        "proposals": 1,
        "passed": 1,
        "characterized": 0,
        "replayed": 0,
        "build_only": 0,
        "unverified": 0,
        "prs_opened": 0,
        "prs_refused": 0,
    }
    assert out.count("\n") == 1


# Spec AC3/M5: the provider envelope reuses the shipped fix items and summary.
def test_provider_json_reuses_the_fix_results_and_summary(tmp_path, capsys):
    bundle = a_bundle(tmp_path)
    old = tmp_path / "old.yaml"
    new = tmp_path / "new.yaml"

    assert (
        a_fix(
            PROOF_BASIC,
            (old, new),
            "--sdk-package",
            "acme.client",
            "--check",
            shlex.join(PROVIDER_CHECK),
            "--json",
        )
        == 0
    )
    fixed = json.loads(capsys.readouterr().out)

    assert a_provider(bundle, "--json") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "provider"
    assert payload["results"] == fixed["results"]
    assert payload["summary"] == fixed["summary"]


def a_run_module_provider(bundle, seed):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tenon",
            "provider",
            "migrate",
            str(PROOF_BASIC),
            "--bundle",
            str(bundle),
            "--json",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
    )


# Spec AC3/M5: the provider JSON is byte-identical across hash seeds.
def test_provider_json_is_byte_stable_across_hash_seeds(tmp_path):
    bundle = a_bundle(tmp_path)

    first = a_run_module_provider(bundle, "0")
    second = a_run_module_provider(bundle, "1")

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
    assert b'"command":"provider"' in first.stdout
    assert b'"provider":"acme"' in first.stdout


# Spec AC4: --open-pr --remote gh uses the shipped adapter and the bundle require.
def test_provider_open_pr_remote_gh_uses_gitgh(tmp_path, monkeypatch, capsys):
    bundle = a_bundle(tmp_path)
    marker = object()
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "GitGhRemote", lambda: marker)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_provider(bundle, "--open-pr", "--remote", "gh") == 0

    assert "PR: https://github.com/example/repo/pull/7" in capsys.readouterr().out
    (call,) = calls
    assert call["remote"] is marker
    assert call["required"] is ProofLevel.TESTS_PASSED
    assert call["allow_below_required"] is False


# Spec AC4: --remote app builds the token and remote from the same flags as fix.
def test_provider_open_pr_remote_app_constructs_the_app_remote(
    tmp_path, monkeypatch, a_app_env
):
    bundle = a_bundle(tmp_path)
    key = a_app_key(tmp_path)
    tokens, remotes = a_app_recorders(monkeypatch)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_provider(
            bundle,
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


# Spec AC4/AC5: --remote without --open-pr is a named usage error.
@pytest.mark.parametrize("remote", ["gh", "app"])
def test_provider_remote_without_open_pr_is_usage(
    remote, tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)

    def bomb(*_args, **_kwargs):
        raise AssertionError("no remote may be constructed")

    monkeypatch.setattr(cli_main, "GitGhRemote", bomb)
    monkeypatch.setattr(cli_main, "GitHubAppRemote", bomb)

    assert a_provider(bundle, "--remote", remote) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--open-pr" in captured.err
    assert "Traceback" not in captured.err


# Spec AC5: the same usage error in --json mode is one object.
def test_provider_remote_without_open_pr_json_is_one_object(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle, "--remote", "app", "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert "--open-pr" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC4: below the requirement with no opt-in, the CLI never calls the writer.
def test_provider_open_pr_below_required_makes_no_pr_call(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path, command=[])
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_provider(bundle, "--open-pr", remote=object()) == 1

    assert calls == []
    assert "PR:" not in capsys.readouterr().out


# Spec AC4: either opt-in reaches the writer as allow_below_required.
@pytest.mark.parametrize("flag", ["--allow-below-required", "--allow-unverified"])
def test_provider_open_pr_below_required_opt_in_reaches_the_writer(
    flag, tmp_path, monkeypatch
):
    bundle = a_bundle(tmp_path, command=[])
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_provider(bundle, "--open-pr", flag, remote=object()) == 1

    (call,) = calls
    assert call["required"] is ProofLevel.TESTS_PASSED
    assert call["allow_below_required"] is True


# Spec AC5: a missing bundle is a named config error.
def test_provider_missing_bundle_is_a_named_error(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    assert a_provider(missing) == 2

    err = capsys.readouterr().err
    assert str(missing) in err
    assert "Traceback" not in err


# Spec AC4: a Rust bundle with MCP is a named bundle error.
def test_provider_rust_bundle_with_mcp_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path, source="mcp", language="rust")

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


# Spec AC4: a Rust bundle with a bad crate is a named bundle error.
@pytest.mark.parametrize("crate", ["a::b", "a/b", ""])
def test_provider_rust_bundle_with_a_bad_crate_is_a_named_error(
    crate, tmp_path, capsys
):
    bundle = a_bundle(tmp_path, language="rust", locate={"sdk_package": crate})

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "sdk_package" in err
    if crate:
        assert "Rust crate" in err
    assert "Traceback" not in err


# Spec AC4: a Go bundle with MCP is a named bundle error.
def test_provider_go_bundle_with_mcp_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path, source="mcp", language="go")

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


# Spec AC4: a Go bundle with a bad import root is a named bundle error.
@pytest.mark.parametrize("root", ["/stripe", "a b", "a::b"])
def test_provider_go_bundle_with_a_bad_root_is_a_named_error(
    root, tmp_path, capsys
):
    bundle = a_bundle(tmp_path, language="go", locate={"sdk_package": root})

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Traceback" not in err


# Spec AC4: a Go bundle with a bad package name is a named bundle error.
def test_provider_go_bundle_with_a_bad_package_is_a_named_error(
    tmp_path, capsys
):
    bundle = a_bundle(
        tmp_path,
        language="go",
        locate={
            "sdk_package": "github.com/stripe/stripe-go/v76",
            "package_name": "not-a-name",
        },
    )

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "package_name" in err
    assert "Traceback" not in err


# Spec AC4: a C# bundle with MCP is a named bundle error.
def test_provider_csharp_bundle_with_mcp_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path, source="mcp", language="csharp")

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "mcp requires language python" in err
    assert "Traceback" not in err


# Spec AC4: a C# bundle with a bad namespace is a named bundle error.
@pytest.mark.parametrize("root", ["", "a/b", "a::b"])
def test_provider_csharp_bundle_with_a_bad_namespace_is_a_named_error(
    root, tmp_path, capsys
):
    bundle = a_bundle(tmp_path, language="csharp", locate={"sdk_package": root})

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "sdk_package" in err
    assert "Traceback" not in err


# Spec AC5: malformed bundle JSON in --json mode is one error object.
def test_provider_bad_bundle_json_is_one_error_object(tmp_path, capsys):
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{", encoding="utf-8")

    assert a_provider(bundle, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert str(bundle) in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC5: a bundle naming a missing spec is a named error.
def test_provider_missing_spec_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path, old="missing.yaml")

    assert a_provider(bundle) == 2

    err = capsys.readouterr().err
    assert "missing.yaml" in err
    assert "Traceback" not in err


# Spec AC5: a spec the differ refuses is a named spec error, not a traceback.
def test_provider_bad_spec_is_a_named_spec_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path, new_text="openapi: 2.0\n")

    assert a_provider(bundle) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tenon: spec:" in captured.err
    assert "UNSUPPORTED_VERSION" in captured.err
    assert "Traceback" not in captured.err


# Spec AC5: the same bad spec in --json mode is one error object.
def test_provider_bad_spec_json_is_one_error_object(tmp_path, capsys):
    bundle = a_bundle(tmp_path, new_text="openapi: 2.0\n")

    assert a_provider(bundle, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "spec"
    assert payload["error"]["code"] == "UNSUPPORTED_VERSION"
    assert captured.out.count("\n") == 1


# Spec AC5: an invalid --require names the five levels and is exit 2.
def test_provider_invalid_require_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle, "--require", "BY_HAND") == 2

    err = capsys.readouterr().err
    assert "--require" in err
    assert "TYPES_BUILD_ONLY" in err
    assert "UNVERIFIED" in err
    assert "Traceback" not in err


# Spec AC5: an invalid --require in --json mode is one error object.
def test_provider_invalid_require_json_is_one_error_object(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle, "--require", "BY_HAND", "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert "TYPES_BUILD_ONLY" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC5: a repository that is not a directory is a named usage error.
def test_provider_missing_repo_is_usage(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_provider(bundle, repo=tmp_path / "missing") == 2

    err = capsys.readouterr().err
    assert "repository is not a directory" in err
    assert "Traceback" not in err


def a_repo_copies(tmp_path):
    """Two independent copies of the proof-basic fixture, in file order."""
    first = tmp_path / "a"
    second = tmp_path / "b"
    shutil.copytree(PROOF_BASIC, first)
    shutil.copytree(PROOF_BASIC, second)
    return first, second


def a_repos_file(tmp_path, *repos):
    """One repos file listing the given checkouts, one per line."""
    path = tmp_path / "repos.txt"
    path.write_text("".join(f"{repo}\n" for repo in repos), encoding="utf-8")
    return path


def a_fanout(bundle, repos, *extra, remote=None):
    return main(
        [
            "provider",
            "migrate",
            "--bundle",
            str(bundle),
            "--repos",
            str(repos),
            *extra,
        ],
        remote=remote,
    )


# Spec AC1: two fixture copies and one bundle pass; each checkout is unchanged.
def test_fanout_two_repos_pass_and_leave_the_checkouts_unchanged(
    a_snapshot, tmp_path, capsys
):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)
    before = {first: a_snapshot(first), second: a_snapshot(second)}

    assert a_fanout(bundle, repos) == 0

    out = capsys.readouterr().out
    assert out.count("Proof: TESTS_PASSED") == 2
    assert a_snapshot(first) == before[first]
    assert a_snapshot(second) == before[second]


# Spec AC2: one missing directory is a per-repo failure; the other repo still runs.
def test_fanout_missing_directory_fails_while_the_other_repo_runs(tmp_path, capsys):
    first, _second = a_repo_copies(tmp_path)
    missing = tmp_path / "missing"
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, missing, first)

    assert a_fanout(bundle, repos) == 1

    out = capsys.readouterr().out
    assert "Proof: TESTS_PASSED" in out


# Spec AC4: the text has the provider header, one block per repo and the summary.
def test_fanout_text_has_the_header_blocks_and_summary(tmp_path, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)

    assert a_fanout(bundle, repos) == 0

    out = capsys.readouterr().out
    assert out.startswith("provider: acme\nmigration: amount-cents\n\n")
    assert out.count(f"repo: {first}\n") == 1
    assert out.count(f"repo: {second}\n") == 1
    assert f"\n\nrepo: {second}\n" in out
    assert out.count("Proof: TESTS_PASSED") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")


# Spec AC2/AC4: a repo that did not run is one named error block, not a fake report.
def test_fanout_text_names_a_missing_directory_and_counts_it(tmp_path, capsys):
    first, _second = a_repo_copies(tmp_path)
    missing = tmp_path / "missing"
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, missing, first)

    assert a_fanout(bundle, repos) == 1

    out = capsys.readouterr().out
    assert f"repo: {missing}\nerror: not a directory" in out
    assert out.endswith("repos: 2, passed: 1, failed: 1\n")


# Spec AC3: the fan-out envelope has exactly the shipped top-level and per-repo keys.
def test_fanout_json_has_the_exact_envelope(tmp_path, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)

    assert a_fanout(bundle, repos, "--json") == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload) == {"command", "provider", "migration", "repos", "summary"}
    assert payload["command"] == "provider"
    assert payload["provider"] == "acme"
    assert payload["migration"] == "amount-cents"
    assert [repo["repo"] for repo in payload["repos"]] == [str(first), str(second)]
    for repo in payload["repos"]:
        assert set(repo) == {"repo", "results", "summary", "exit", "error"}
        (result,) = repo["results"]
        assert set(result) == {"change", "locate", "proposal", "proof", "pr"}
        assert result["proof"]["level"] == "TESTS_PASSED"
        assert repo["summary"]["passed"] == 1
        assert repo["exit"] == 0
        assert repo["error"] is None
    assert payload["summary"] == {"repos": 2, "passed": 2, "failed": 0}
    assert out.count("\n") == 1


# Spec AC3: a repo that did not run has a zero fix summary, not an invented one.
def test_fanout_json_zero_summary_for_a_repo_that_did_not_run(tmp_path, capsys):
    missing = tmp_path / "missing"
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, missing)

    assert a_fanout(bundle, repos, "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    (repo,) = payload["repos"]
    assert repo["repo"] == str(missing)
    assert repo["results"] == []
    assert repo["summary"] == {
        "changes": 0,
        "proposals": 0,
        "passed": 0,
        "characterized": 0,
        "replayed": 0,
        "build_only": 0,
        "unverified": 0,
        "prs_opened": 0,
        "prs_refused": 0,
    }
    assert repo["exit"] == 1
    assert repo["error"] == "not a directory"
    assert payload["summary"] == {"repos": 1, "passed": 0, "failed": 1}


def a_run_module_fanout(bundle, repos, seed):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tenon",
            "provider",
            "migrate",
            "--bundle",
            str(bundle),
            "--repos",
            str(repos),
            "--json",
        ],
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
    )


# Spec AC3: the fan-out JSON is byte-identical across hash seeds.
def test_fanout_json_is_byte_stable_across_hash_seeds(tmp_path):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)

    zero = a_run_module_fanout(bundle, repos, "0")
    one = a_run_module_fanout(bundle, repos, "1")

    assert zero.returncode == 0
    assert one.returncode == 0
    assert zero.stdout == one.stdout
    assert b'"command":"provider"' in zero.stdout
    assert b'"repos":[' in zero.stdout
    assert str(first).encode() in zero.stdout


# Spec AC6: one injected remote opens one PR per repo.
def test_fanout_open_pr_writes_one_pr_per_repo_with_one_remote(
    tmp_path, monkeypatch, capsys
):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)
    marker = object()
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fanout(bundle, repos, "--open-pr", remote=marker) == 0

    assert [call["repo"] for call in calls] == [first, second]
    assert all(call["remote"] is marker for call in calls)
    out = capsys.readouterr().out
    assert out.count("PR: https://github.com/example/repo/pull/7") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")


# Spec AC6: the app remote is constructed once for the whole fan-out.
def test_fanout_open_pr_constructs_the_app_remote_once(
    tmp_path, monkeypatch, capsys
):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)
    marker = object()
    seen = []

    def remote_spy(args):
        seen.append(args)
        return marker

    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "_remote", remote_spy)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fanout(bundle, repos, "--open-pr", "--remote", "app") == 0

    assert len(seen) == 1
    assert [call["remote"] for call in calls] == [marker, marker]


# Spec AC6: a refused PR fails only its repo; the other still opens.
def test_fanout_refused_pr_fails_that_repo_only(tmp_path, monkeypatch, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = a_repos_file(tmp_path, first, second)
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
        calls.append(repo)
        if repo == second:
            return a_pr(
                proof,
                status=PrStatus.REFUSED,
                refusal=PrRefusal.DIRTY_CHECKOUT,
            )
        return a_pr(proof)

    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fanout(bundle, repos, "--open-pr", remote=object()) == 1

    assert calls == [first, second]
    out = capsys.readouterr().out
    assert out.count("PR: https://github.com/example/repo/pull/7") == 1
    assert "PR refused: DIRTY_CHECKOUT" in out
    assert out.endswith("repos: 2, passed: 1, failed: 1\n")


# Spec AC6: below the requirement with no opt-in, no repo calls the writer.
def test_fanout_open_pr_below_required_makes_no_pr_calls(tmp_path, monkeypatch):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path, command=[])
    repos = a_repos_file(tmp_path, first, second)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_fanout(bundle, repos, "--open-pr", remote=object()) == 1
    assert calls == []


# Spec AC6: the below-required opt-in reaches the writer for every repo.
def test_fanout_allow_below_required_reaches_every_writer_call(
    tmp_path, monkeypatch
):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path, command=[])
    repos = a_repos_file(tmp_path, first, second)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert (
        a_fanout(
            bundle,
            repos,
            "--open-pr",
            "--allow-below-required",
            remote=object(),
        )
        == 1
    )

    assert [call["repo"] for call in calls] == [first, second]
    assert all(call["allow_below_required"] is True for call in calls)
    assert all(call["required"] is ProofLevel.TESTS_PASSED for call in calls)


# Spec AC7: --check overrides the bundle command for every repo.
def test_fanout_check_flag_reaches_every_repo(tmp_path, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path, command=[])
    repos = a_repos_file(tmp_path, first, second)

    assert a_fanout(bundle, repos) == 1
    assert capsys.readouterr().out.count("Cause: NO_PROOF_COMMAND") == 2

    assert a_fanout(bundle, repos, "--check", shlex.join(PROVIDER_CHECK)) == 0
    out = capsys.readouterr().out
    assert out.count("Proof: TESTS_PASSED") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")


# Spec AC7: --require overrides the bundle bar for every repo.
def test_fanout_require_flag_reaches_every_repo(tmp_path, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path, command=[], require="UNVERIFIED")
    repos = a_repos_file(tmp_path, first, second)

    assert a_fanout(bundle, repos) == 0
    assert capsys.readouterr().out.count("Proof: UNVERIFIED") == 2

    assert a_fanout(bundle, repos, "--require", "TESTS_PASSED") == 1
    out = capsys.readouterr().out
    assert out.count("Proof: UNVERIFIED") == 2
    assert out.endswith("repos: 2, passed: 0, failed: 2\n")


SELECTIONS = [
    ("neither", "a repository, --repos or --installed is required"),
    ("repo_repos", "provide only one of <repo>, --repos or --installed"),
    ("repo_installed", "provide only one of <repo>, --repos or --installed"),
    ("repos_installed", "provide only one of <repo>, --repos or --installed"),
    ("all", "provide only one of <repo>, --repos or --installed"),
]


def a_selection_argv(selection, bundle, first, repos):
    argv = ["provider", "migrate", "--bundle", str(bundle)]
    if selection in ("repo_repos", "repo_installed", "all"):
        argv.append(str(first))
    if selection in ("repo_repos", "repos_installed", "all"):
        argv += ["--repos", str(repos)]
    if selection in ("repo_installed", "repos_installed", "all"):
        argv.append("--installed")
    return argv


@pytest.mark.parametrize("selection, message", SELECTIONS)
def test_fanout_selection_errors_are_named(
    selection, message, tmp_path, capsys
):
    bundle = a_bundle(tmp_path)
    first, _second = a_repo_copies(tmp_path)
    repos = a_repos_file(tmp_path, first)
    argv = a_selection_argv(selection, bundle, first, repos)

    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("selection, message", SELECTIONS)
def test_fanout_selection_errors_json_are_one_object(
    selection, message, tmp_path, capsys
):
    bundle = a_bundle(tmp_path)
    first, _second = a_repo_copies(tmp_path)
    repos = a_repos_file(tmp_path, first)
    argv = a_selection_argv(selection, bundle, first, repos) + ["--json"]

    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert payload["error"]["message"] == message
    assert captured.out.count("\n") == 1


# Spec AC7: a missing repos file is a named config error.
def test_fanout_missing_repos_file_is_a_named_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path)
    missing = tmp_path / "missing.txt"

    assert a_fanout(bundle, missing) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(missing) in captured.err
    assert "Traceback" not in captured.err


# Spec AC7: an empty repos file is one JSON config error object.
def test_fanout_empty_repos_file_json_is_one_error(tmp_path, capsys):
    bundle = a_bundle(tmp_path)
    empty = tmp_path / "repos.txt"
    empty.write_text("", encoding="utf-8")

    assert a_fanout(bundle, empty, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "config"
    assert "no paths" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC7: a bad bundle with --repos is a named config error, not a traceback.
def test_fanout_bad_bundle_is_a_named_error(tmp_path, capsys):
    first, _second = a_repo_copies(tmp_path)
    repos = a_repos_file(tmp_path, first)
    missing = tmp_path / "missing.json"

    assert a_fanout(missing, repos) == 2

    err = capsys.readouterr().err
    assert str(missing) in err
    assert "Traceback" not in err


# Spec AC7: a shared spec refusal aborts the whole fan-out with exit 2.
def test_fanout_shared_bad_spec_exits_two(tmp_path, capsys):
    first, second = a_repo_copies(tmp_path)
    bundle = a_bundle(tmp_path, new_text="openapi: 2.0\n")
    repos = a_repos_file(tmp_path, first, second)

    assert a_fanout(bundle, repos) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tenon: spec:" in captured.err
    assert "UNSUPPORTED_VERSION" in captured.err
    assert "Traceback" not in captured.err


def a_installed(bundle, *extra, remote=None):
    return main(
        ["provider", "migrate", "--installed", "--bundle", str(bundle), *extra],
        remote=remote,
    )


# Spec AC4: installed discovery needs the app identity, never a gh remote.
def test_installed_remote_gh_is_usage(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_installed(bundle, "--open-pr", "--remote", "gh") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--installed requires --remote app" in captured.err
    assert "Traceback" not in captured.err


# Spec AC4/AC7: each missing app input is exit 2 before any discovery.
@pytest.mark.parametrize(
    ("omitted", "message"),
    [
        ("--app-id", "--app-id or TENON_GITHUB_APP_ID"),
        (
            "--app-installation-id",
            "--app-installation-id or TENON_GITHUB_APP_INSTALLATION_ID",
        ),
        (
            "--app-private-key",
            "--app-private-key or TENON_GITHUB_APP_PRIVATE_KEY",
        ),
    ],
)
def test_installed_missing_app_input_is_usage(
    omitted, message, tmp_path, monkeypatch, a_app_env, capsys
):
    bundle = a_bundle(tmp_path)
    key = a_app_key(tmp_path)
    inputs = {
        "--app-id": "123",
        "--app-installation-id": "456",
        "--app-private-key": str(key),
    }
    del inputs[omitted]
    flat = [part for pair in inputs.items() for part in pair]

    def bomb(*_args, **_kwargs):
        raise AssertionError("no discovery may run")

    monkeypatch.setattr(cli_main, "list_installation_repos", bomb)

    assert a_installed(bundle, *flat) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err


# Spec AC7: an unreadable private key is exit 2 and names the path.
def test_installed_unreadable_key_is_usage(tmp_path, a_app_env, capsys):
    bundle = a_bundle(tmp_path)
    missing = tmp_path / "missing.pem"

    assert (
        a_installed(
            bundle,
            "--app-id",
            "123",
            "--app-installation-id",
            "456",
            "--app-private-key",
            str(missing),
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read the app private key" in captured.err
    assert str(missing) in captured.err
    assert "Traceback" not in captured.err


INSTALLED_TOKEN = "ghs_installed_token"
INSTALLED_API_URL = "https://ghe.example/api/v3"


def a_installed_repos(*names, clone_url="https://example.test/acme/repo.git"):
    """Installation repos in API order, named owner/name for the report."""
    return tuple(InstalledRepo(name, clone_url) for name in names)


def a_installed_app(monkeypatch, repos, *, api_url=INSTALLED_API_URL):
    """Patch the app seam and the lister; record the mint count and lister call."""

    class Provider:
        mints = 0

        def token(self):
            Provider.mints += 1
            return INSTALLED_TOKEN

    provider = Provider()
    seen = []

    def lister(api, token):
        seen.append((api, token))
        return tuple(repos)

    monkeypatch.setattr(cli_main, "_app", lambda args: (provider, api_url))
    monkeypatch.setattr(cli_main, "list_installation_repos", lister)
    return provider, seen


def a_clone_source(tmp_path):
    """A local git repo seeded from proof-basic, cloneable by the real helper."""
    source = tmp_path / "source"
    shutil.copytree(
        PROOF_BASIC, source, ignore=shutil.ignore_patterns("__pycache__")
    )
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Tenon Tests"],
        ["git", "config", "user.email", "tenon@example.test"],
        ["git", "add", "."],
        ["git", "commit", "-m", "fixture"],
    ):
        subprocess.run(
            argv, cwd=source, check=True, capture_output=True, text=True
        )
    return source


def a_fake_installed_clone(monkeypatch, tmp_path, *, fail=()):
    """Yield a fresh proof-basic copy per repo; ``fail`` names raise first."""
    checkouts = []

    @contextmanager
    def clone(repo, token):
        if repo.full_name in fail:
            raise RemoteError(
                f"could not clone {repo.full_name}: {INSTALLED_TOKEN} boom"
            )
        path = tmp_path / f"clone-{len(checkouts)}"
        shutil.copytree(
            PROOF_BASIC, path, ignore=shutil.ignore_patterns("__pycache__")
        )
        checkouts.append((repo, token, path))
        yield path

    monkeypatch.setattr(cli_main, "clone_repo", clone)
    return checkouts


def a_real_clone_recorder(monkeypatch):
    """Record the repo/token each real clone receives, then clone for real."""
    calls = []

    def clone(repo, token):
        calls.append((repo, token))
        return real_clone_repo(repo, token)

    monkeypatch.setattr(cli_main, "clone_repo", clone)
    return calls


# Spec AC1/AC5: two installed repos clone with the real helper and pass on one token.
def test_installed_two_repos_clone_and_pass(tmp_path, monkeypatch, capsys):
    source = a_clone_source(tmp_path)
    bundle = a_bundle(tmp_path)
    repos = (
        InstalledRepo("acme/one", str(source)),
        InstalledRepo("acme/two", str(source)),
    )
    provider, seen = a_installed_app(monkeypatch, repos)
    clones = a_real_clone_recorder(monkeypatch)
    before = set(Path(tempfile.gettempdir()).glob("tenon-installed-*"))

    assert a_installed(bundle) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("provider: acme\nmigration: amount-cents\n\n")
    assert captured.out.count("repo: acme/") == 2
    assert captured.out.count("Proof: TESTS_PASSED") == 2
    assert captured.out.endswith("repos: 2, passed: 2, failed: 0\n")
    assert provider.mints == 1
    (api, token), = seen
    assert token == INSTALLED_TOKEN
    assert api._api_url == INSTALLED_API_URL
    assert [call[1] for call in clones] == [INSTALLED_TOKEN, INSTALLED_TOKEN]
    assert set(Path(tempfile.gettempdir()).glob("tenon-installed-*")) == before
    assert INSTALLED_TOKEN not in captured.out + captured.err


# Spec AC2: a clone error is one per-repo error; the other repo still runs.
def test_installed_clone_error_is_per_repo_and_the_other_runs(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    repos = a_installed_repos("acme/bad", "acme/one")
    a_installed_app(monkeypatch, repos)
    a_fake_installed_clone(monkeypatch, tmp_path, fail={"acme/bad"})

    assert a_installed(bundle, "--json") == 1

    out = capsys.readouterr().out
    payload = json.loads(out)
    bad, good = payload["repos"]
    assert bad["repo"] == "acme/bad"
    assert bad["results"] == []
    assert bad["exit"] == 1
    assert bad["error"] == "could not clone acme/bad: *** boom"
    assert good["repo"] == "acme/one"
    assert good["exit"] == 0
    assert good["results"][0]["proof"]["level"] == "TESTS_PASSED"
    assert payload["summary"] == {"repos": 2, "passed": 1, "failed": 1}
    assert INSTALLED_TOKEN not in out


# Spec AC3: the text has the provider header, owner/name blocks and the summary.
def test_installed_text_has_the_header_blocks_and_summary(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    a_installed_app(monkeypatch, a_installed_repos("acme/one", "acme/two"))
    a_fake_installed_clone(monkeypatch, tmp_path)

    assert a_installed(bundle) == 0

    out = capsys.readouterr().out
    assert out.startswith("provider: acme\nmigration: amount-cents\n\n")
    assert out.count("repo: acme/one\n") == 1
    assert out.count("repo: acme/two\n") == 1
    assert out.count("Proof: TESTS_PASSED") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")


# Spec AC3: the T10c fan-out envelope keyed by owner/name is byte-stable.
def test_installed_json_has_the_exact_envelope_and_is_byte_stable(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    a_installed_app(monkeypatch, a_installed_repos("acme/one", "acme/two"))
    a_fake_installed_clone(monkeypatch, tmp_path)

    assert a_installed(bundle, "--json") == 0
    first = capsys.readouterr().out
    payload = json.loads(first)
    assert set(payload) == {"command", "provider", "migration", "repos", "summary"}
    assert payload["command"] == "provider"
    assert payload["provider"] == "acme"
    assert payload["migration"] == "amount-cents"
    assert [repo["repo"] for repo in payload["repos"]] == ["acme/one", "acme/two"]
    for repo in payload["repos"]:
        assert set(repo) == {"repo", "results", "summary", "exit", "error"}
        (result,) = repo["results"]
        assert set(result) == {"change", "locate", "proposal", "proof", "pr"}
        assert result["proof"]["level"] == "TESTS_PASSED"
        assert repo["summary"]["passed"] == 1
        assert repo["exit"] == 0
        assert repo["error"] is None
    assert payload["summary"] == {"repos": 2, "passed": 2, "failed": 0}
    assert first.count("\n") == 1

    assert a_installed(bundle, "--json") == 0
    assert capsys.readouterr().out == first


# Spec AC5/AC6: one injected remote opens one PR per installed repo.
def test_installed_open_pr_writes_one_pr_per_repo_with_the_injected_remote(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    repos = a_installed_repos("acme/one", "acme/two")
    a_installed_app(monkeypatch, repos)
    clones = a_fake_installed_clone(monkeypatch, tmp_path)
    marker = object()
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_installed(bundle, "--open-pr", remote=marker) == 0

    assert [call["repo"] for call in calls] == [entry[2] for entry in clones]
    assert all(call["remote"] is marker for call in calls)
    assert [entry[1] for entry in clones] == [INSTALLED_TOKEN, INSTALLED_TOKEN]
    out = capsys.readouterr().out
    assert out.count("PR: https://github.com/example/repo/pull/7") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")
    assert INSTALLED_TOKEN not in out


# Spec S3/AC5: the dry run discovers and runs but never calls the writer.
def test_installed_dry_run_makes_no_pr_call(tmp_path, monkeypatch, capsys):
    bundle = a_bundle(tmp_path)
    a_installed_app(monkeypatch, a_installed_repos("acme/one"))
    a_fake_installed_clone(monkeypatch, tmp_path)
    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_installed(bundle) == 0

    assert calls == []
    assert "PR:" not in capsys.readouterr().out


# Spec AC5: --open-pr with no injected remote builds one app remote from the token.
def test_installed_open_pr_constructs_the_app_remote_once_from_the_token(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    repos = a_installed_repos("acme/one", "acme/two")
    provider, seen = a_installed_app(monkeypatch, repos)
    clones = a_fake_installed_clone(monkeypatch, tmp_path)
    remotes = []

    class Remote:
        def __init__(self, token_provider, api_url="https://api.github.com"):
            self.record = {"provider": token_provider, "api_url": api_url}
            remotes.append(self.record)

    write_pr, calls = a_recorder(a_pr)
    monkeypatch.setattr(cli_main, "GitHubAppRemote", Remote)
    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_installed(bundle, "--open-pr", "--remote", "app") == 0

    assert provider.mints == 1
    (remote,) = remotes
    assert isinstance(remote["provider"], StaticToken)
    assert remote["provider"].token() == INSTALLED_TOKEN
    assert remote["api_url"] == INSTALLED_API_URL
    assert all(call["remote"].record is remote for call in calls)
    assert [entry[1] for entry in clones] == [INSTALLED_TOKEN, INSTALLED_TOKEN]
    assert [entry[1] for entry in seen] == [INSTALLED_TOKEN]
    assert INSTALLED_TOKEN not in capsys.readouterr().out


# Spec AC6: a refused PR fails only that repo; the overall exit is 1.
def test_installed_refused_pr_makes_the_overall_exit_one(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    repos = a_installed_repos("acme/one", "acme/two")
    a_installed_app(monkeypatch, repos)
    a_fake_installed_clone(monkeypatch, tmp_path)

    def write_pr(proposal, proof, repo, **_kwargs):
        if repo.name == "clone-1":
            return a_pr(
                proof,
                status=PrStatus.REFUSED,
                refusal=PrRefusal.DIRTY_CHECKOUT,
            )
        return a_pr(proof)

    monkeypatch.setattr(cli_main, "write_pr", write_pr)

    assert a_installed(bundle, "--open-pr", remote=object()) == 1

    out = capsys.readouterr().out
    assert out.count("PR: https://github.com/example/repo/pull/7") == 1
    assert "PR refused: DIRTY_CHECKOUT" in out
    assert out.endswith("repos: 2, passed: 1, failed: 1\n")


# Spec AC6/AC7: --check overrides the bundle command for every installed repo.
def test_installed_check_flag_reaches_every_repo(tmp_path, monkeypatch, capsys):
    bundle = a_bundle(tmp_path, command=[])
    a_installed_app(monkeypatch, a_installed_repos("acme/one", "acme/two"))
    a_fake_installed_clone(monkeypatch, tmp_path)

    assert a_installed(bundle) == 1
    assert capsys.readouterr().out.count("Cause: NO_PROOF_COMMAND") == 2

    assert a_installed(bundle, "--check", shlex.join(PROVIDER_CHECK)) == 0
    out = capsys.readouterr().out
    assert out.count("Proof: TESTS_PASSED") == 2
    assert out.endswith("repos: 2, passed: 2, failed: 0\n")


# Spec AC6/AC7: --require overrides the bundle bar for every installed repo.
def test_installed_require_flag_reaches_every_repo(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path, command=[], require="UNVERIFIED")
    a_installed_app(monkeypatch, a_installed_repos("acme/one", "acme/two"))
    a_fake_installed_clone(monkeypatch, tmp_path)

    assert a_installed(bundle) == 0
    assert capsys.readouterr().out.count("Proof: UNVERIFIED") == 2

    assert a_installed(bundle, "--require", "TESTS_PASSED") == 1
    out = capsys.readouterr().out
    assert out.count("Proof: UNVERIFIED") == 2
    assert out.endswith("repos: 2, passed: 0, failed: 2\n")


# Spec AC7: a token or discovery failure is one named usage error, exit 2.
@pytest.mark.parametrize("where", ["token", "list"])
def test_installed_discovery_failure_exits_two(
    where, tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)

    class Provider:
        def token(self):
            if where == "token":
                raise RemoteError("ghs_test boom")
            return INSTALLED_TOKEN

    monkeypatch.setattr(
        cli_main, "_app", lambda args: (Provider(), INSTALLED_API_URL)
    )

    def lister(api, token):
        raise RemoteError("GET /installation/repositories failed: 401")

    if where == "list":
        monkeypatch.setattr(cli_main, "list_installation_repos", lister)

    assert a_installed(bundle) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "could not list installed repositories" in captured.err
    assert "Traceback" not in captured.err


# Spec AC7: the same discovery failure in --json mode is one object.
def test_installed_discovery_failure_json_is_one_object(
    tmp_path, monkeypatch, capsys
):
    bundle = a_bundle(tmp_path)
    a_installed_app(monkeypatch, ())

    def lister(api, token):
        raise RemoteError("GET /installation/repositories failed: 401")

    monkeypatch.setattr(cli_main, "list_installation_repos", lister)

    assert a_installed(bundle, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert "could not list installed repositories" in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC7: a shared spec refusal aborts the whole installed fan-out with exit 2.
def test_installed_shared_bad_spec_exits_two(tmp_path, monkeypatch, capsys):
    bundle = a_bundle(tmp_path, new_text="openapi: 2.0\n")
    a_installed_app(monkeypatch, a_installed_repos("acme/one", "acme/two"))
    a_fake_installed_clone(monkeypatch, tmp_path)

    assert a_installed(bundle) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tenon: spec:" in captured.err
    assert "UNSUPPORTED_VERSION" in captured.err
    assert "Traceback" not in captured.err


# Spec AC7: a missing app input in --json mode is one object.
@pytest.mark.parametrize(
    "omitted", ["--app-id", "--app-installation-id", "--app-private-key"]
)
def test_installed_missing_app_input_json_is_one_object(
    omitted, tmp_path, monkeypatch, a_app_env, capsys
):
    bundle = a_bundle(tmp_path)
    key = a_app_key(tmp_path)
    inputs = {
        "--app-id": "123",
        "--app-installation-id": "456",
        "--app-private-key": str(key),
    }
    del inputs[omitted]
    flat = [part for pair in inputs.items() for part in pair]

    def bomb(*_args, **_kwargs):
        raise AssertionError("no discovery may run")

    monkeypatch.setattr(cli_main, "list_installation_repos", bomb)

    assert a_installed(bundle, *flat, "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert omitted in payload["error"]["message"]
    assert captured.out.count("\n") == 1


# Spec AC4/AC7: --installed --remote gh in --json mode is one object.
def test_installed_remote_gh_json_is_one_object(tmp_path, capsys):
    bundle = a_bundle(tmp_path)

    assert a_installed(bundle, "--open-pr", "--remote", "gh", "--json") == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"error"}
    assert payload["error"]["kind"] == "usage"
    assert payload["error"]["message"] == "--installed requires --remote app"
    assert captured.out.count("\n") == 1


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

SERVE_TOKEN = "serve-api-token"


def a_serve_argv(tmp_path, *extra, bundles=None, db=None):
    return [
        "provider",
        "serve",
        "--bundles",
        str(bundles if bundles is not None else tmp_path / "bundles"),
        "--db",
        str(db if db is not None else tmp_path / "runs.db"),
        *extra,
    ]


def a_serve_args(tmp_path, *extra):
    return cli_main._parser().parse_args(
        a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, *extra)
    )


def a_fake_server(monkeypatch):
    """Patch the module's serve and return its recorded api, host and port."""
    seen = {}

    class Server:
        closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            Server.closed = True

    server = Server()

    def fake_serve(api, host, port):
        seen.update(api=api, host=host, port=port)
        return server

    monkeypatch.setattr(cli_main, "serve", fake_serve)
    return seen, server


def a_fake_workers(monkeypatch):
    """Patch the module's Worker and record every instance."""
    instances = []

    class FakeWorker:
        def __init__(self, store, execute, *, poll=1.0, retries=0):
            self.store = store
            self.execute = execute
            self.poll = poll
            self.retries = retries
            self.started = False
            self.stopped = False
            instances.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(cli_main, "Worker", FakeWorker)
    return instances


# Spec AC1: provider serve --help is a zero and lists every flag.
def test_provider_serve_help_lists_the_flags(capsys):
    assert main(["provider", "serve", "--help"]) == 0

    out = capsys.readouterr().out
    for flag in (
        "--bundles",
        "--db",
        "--api-token",
        "--webhook-secret",
        "--host",
        "--port",
        "--run-timeout",
        "--poll",
        "--workers",
        "--retries",
        "--dry-run",
        "--app-id",
        "--app-installation-id",
        "--app-private-key",
        "--api-url",
    ):
        assert flag in out


# Spec AC1: the serve defaults are the documented ones.
def test_provider_serve_defaults(tmp_path):
    args = a_serve_args(tmp_path)

    assert args.host == "127.0.0.1"
    assert args.port == 8080
    assert args.run_timeout == 3600
    assert args.poll == 1.0
    assert args.workers == 1
    assert args.retries == 0
    assert args.dry_run is False


# Spec AC3: a workers or retries value outside its bound is a named usage error.
@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--workers", "0", "--workers must be 1..16"),
        ("--workers", "17", "--workers must be 1..16"),
        ("--retries", "-1", "--retries must be 0..10"),
        ("--retries", "11", "--retries must be 0..10"),
    ],
)
def test_provider_serve_bounds_are_named_usage_errors(
    tmp_path, monkeypatch, capsys, flag, value, message
):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)
    bundles = tmp_path / "bundles"
    bundles.mkdir()

    assert (
        main(
            a_serve_argv(
                tmp_path, "--api-token", SERVE_TOKEN, flag, value, bundles=bundles
            )
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "runs.db").exists()


# Spec AC3: a non-integer flag value is an argparse parse error.
@pytest.mark.parametrize(
    ("flag", "value"), [("--workers", "abc"), ("--retries", "1.5")]
)
def test_provider_serve_flags_must_be_integers(tmp_path, capsys, flag, value):
    bundles = tmp_path / "bundles"
    bundles.mkdir()

    assert (
        main(
            a_serve_argv(
                tmp_path, "--api-token", SERVE_TOKEN, flag, value, bundles=bundles
            )
        )
        == 2
    )

    captured = capsys.readouterr()
    assert "invalid int value" in captured.err
    assert "Traceback" not in captured.err


# Spec AC1: a missing token is a named usage error, before any store opens.
def test_provider_serve_missing_token_is_usage(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)

    assert main(a_serve_argv(tmp_path)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--api-token or TENON_API_TOKEN" in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "runs.db").exists()


# Spec AC1: an empty token is the same named usage error.
def test_provider_serve_empty_token_is_usage(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)

    assert main(a_serve_argv(tmp_path, "--api-token", "")) == 2

    assert "--api-token or TENON_API_TOKEN" in capsys.readouterr().err


# Spec AC1: the token may come from TENON_API_TOKEN.
def test_provider_serve_reads_the_token_from_the_env(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TENON_API_TOKEN", SERVE_TOKEN)
    missing = tmp_path / "missing"

    assert main(a_serve_argv(tmp_path, bundles=missing)) == 2

    err = capsys.readouterr().err
    assert "not a directory" in err
    assert "TENON_API_TOKEN" not in err


# Spec AC1: --bundles must be an existing directory.
@pytest.mark.parametrize("kind", ["missing", "file"])
def test_provider_serve_bundles_must_be_a_directory(
    tmp_path, monkeypatch, capsys, kind
):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)
    bundles = tmp_path / "bundles"
    if kind == "file":
        bundles.write_text("not a directory")

    assert main(a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, bundles=bundles)) == 2

    err = capsys.readouterr().err
    assert "not a directory" in err
    assert "Traceback" not in err


# Spec AC1: a db whose parent is missing is a named usage error.
def test_provider_serve_bad_db_is_usage(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    db = tmp_path / "missing" / "runs.db"

    assert main(a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, bundles=bundles, db=db)) == 2

    err = capsys.readouterr().err
    assert "cannot open store" in err
    assert str(db) in err
    assert "Traceback" not in err


# Spec AC1: the serve parser never reaches the fix/migrate --remote guard and
# never reads an args.json that serve does not define.
def test_provider_serve_does_not_hit_the_remote_guard(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("TENON_API_TOKEN", raising=False)
    bundles = tmp_path / "missing"

    assert main(a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, bundles=bundles)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a directory" in captured.err
    assert "internal" not in captured.err
    assert "--remote" not in captured.err


# Spec AC4: the worker maps a run's bundle name to a confined path before the runner.
def test_serve_execute_resolves_the_bundle_name(tmp_path):
    from tenon.service import Run
    from tenon.service.runner import Outcome as RunOutcome

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    bundle = bundles / "demo.json"
    bundle.write_text("{}")
    seen = []

    class FakeRunner:
        def run(self, path, cancel=None):
            seen.append(path)
            return RunOutcome(0, {"command": "provider"}, None)

    execute = cli_main._serve_execute(FakeRunner(), bundles)
    done = execute(
        Run(id="a", bundle="demo.json", status="queued", created_at="t")
    )
    missing = execute(
        Run(id="b", bundle="../demo.json", status="queued", created_at="t")
    )

    assert seen == [bundle.resolve()]
    assert done.exit == 0
    assert missing.exit is None
    assert "not available" in missing.error


# Spec AC2: the service wires the store's cancel flag into the runner.
def test_serve_execute_passes_the_cancel_predicate(tmp_path):
    from tenon.service import Run
    from tenon.service.runner import Outcome as RunOutcome

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    (bundles / "demo.json").write_text("{}")
    requested = {"value": False}
    seen = {}

    class FakeRunner:
        def run(self, path, cancel=None):
            seen["cancel"] = cancel
            return RunOutcome(0, {}, None)

    execute = cli_main._serve_execute(
        FakeRunner(), bundles, lambda run_id: requested["value"]
    )
    done = execute(
        Run(id="a", bundle="demo.json", status="running", created_at="t")
    )

    assert done.exit == 0
    assert seen["cancel"]() is False
    requested["value"] = True
    assert seen["cancel"]() is True


# Spec AC1/AC4: the child argv runs the shipped installed fan-out and opens a PR.
def test_serve_command_builds_the_installed_migrate_argv(tmp_path):
    args = a_serve_args(tmp_path)
    bundle = tmp_path / "bundle.json"

    argv = cli_main._serve_command(args, bundle)

    assert argv == [
        sys.executable,
        "-c",
        "from tenon.cli import main; raise SystemExit(main())",
        "provider",
        "migrate",
        "--installed",
        "--bundle",
        str(bundle),
        "--json",
        "--open-pr",
        "--remote",
        "app",
    ]


# Spec AC1: a dry run omits both the PR flag and the remote.
def test_serve_command_omits_open_pr_for_a_dry_run(tmp_path):
    args = a_serve_args(tmp_path, "--dry-run")

    argv = cli_main._serve_command(args, tmp_path / "bundle.json")

    assert "--installed" in argv
    assert "--bundle" in argv
    assert "--json" in argv
    assert "--open-pr" not in argv
    assert "--remote" not in argv


# Spec AC1: the non-None app flags and api URL reach the child.
def test_serve_command_includes_the_app_flags(tmp_path):
    args = a_serve_args(
        tmp_path,
        "--app-id",
        "123",
        "--app-installation-id",
        "456",
        "--app-private-key",
        "/keys/app.pem",
        "--api-url",
        "https://ghe.example/api/v3",
    )

    argv = cli_main._serve_command(args, tmp_path / "bundle.json")

    for flag, value in (
        ("--app-id", "123"),
        ("--app-installation-id", "456"),
        ("--app-private-key", "/keys/app.pem"),
        ("--api-url", "https://ghe.example/api/v3"),
    ):
        assert argv[argv.index(flag) + 1] == value


# Spec AC1: omitted app flags are not invented for the child.
def test_serve_command_leaves_omitted_app_flags_out(tmp_path):
    args = a_serve_args(tmp_path)

    argv = cli_main._serve_command(args, tmp_path / "bundle.json")

    for flag in (
        "--app-id",
        "--app-installation-id",
        "--app-private-key",
        "--api-url",
    ):
        assert flag not in argv


# Spec AC1/AC6: serve builds the API, listens, and stops cleanly on SIGINT.
def test_provider_serve_starts_the_worker_and_stops_on_interrupt(
    tmp_path, monkeypatch, capsys
):
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    seen, server = a_fake_server(monkeypatch)

    assert main(a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, bundles=bundles)) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "tenon: provider serve: listening on http://127.0.0.1:8080\n"
    )
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8080
    assert seen["api"].handle("GET", "/health", {}, b"").status == 200
    assert server.closed is True
    assert SERVE_TOKEN not in captured.out + captured.err


# Spec AC5: serve recovers stranded runs and starts N workers with the flags.
def test_provider_serve_recovers_and_starts_n_workers(
    tmp_path, monkeypatch, capsys
):
    from tenon.service.store import RunStore

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    stranded = RunStore(tmp_path / "runs.db")
    run = stranded.create_run("bundle.json")
    stranded.claim_next()
    stranded.close()
    instances = a_fake_workers(monkeypatch)
    seen, server = a_fake_server(monkeypatch)

    assert (
        main(
            a_serve_argv(
                tmp_path,
                "--api-token",
                SERVE_TOKEN,
                "--workers",
                "3",
                "--retries",
                "2",
                bundles=bundles,
            )
        )
        == 0
    )

    assert len(instances) == 3
    assert all(worker.started and worker.stopped for worker in instances)
    assert {worker.retries for worker in instances} == {2}
    assert {worker.poll for worker in instances} == {1.0}
    assert seen["api"]._workers == 3
    assert server.closed is True
    recovered = RunStore(tmp_path / "runs.db")
    try:
        assert recovered.get(run.id).status == "queued"
    finally:
        recovered.close()


# Spec AC1/AC5: the webhook secret may come from TENON_WEBHOOK_SECRET.
def test_provider_serve_reads_the_webhook_secret_from_the_env(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TENON_WEBHOOK_SECRET", "hook-secret")
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    seen, _server = a_fake_server(monkeypatch)

    assert main(a_serve_argv(tmp_path, "--api-token", SERVE_TOKEN, bundles=bundles)) == 0

    response = seen["api"].handle("POST", "/webhooks/github", {}, b"{}")
    assert response.status == 401
    capsys.readouterr()
