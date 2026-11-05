import re

import pytest

from tenon.cli import CliConfig, load_cli_config, overrides
from tenon.locate import LocateConfig
from tenon.prove import ProofLevel


def a_config(
    *,
    sdk_package="stripe",
    operations=None,
    fields=None,
    command=(),
    require=ProofLevel.TESTS_PASSED,
    breaking_only=False,
):
    return CliConfig(
        locate=LocateConfig(
            sdk_package=sdk_package,
            operations=operations or {},
            fields=fields or {},
        ),
        command=command,
        require=require,
        breaking_only=breaking_only,
    )


def a_file(tmp_path, text):
    path = tmp_path / "tenon.toml"
    path.write_text(text)
    return path


# Spec AC1: a minimal file loads the shipped defaults.
def test_minimal_file_uses_defaults(tmp_path):
    path = a_file(tmp_path, '[locate]\nsdk_package = "stripe"\n')

    assert load_cli_config(path) == CliConfig(
        locate=LocateConfig(sdk_package="stripe"),
        command=(),
        require=ProofLevel.TESTS_PASSED,
        breaking_only=False,
    )


# Spec AC2: every table and every [tenon] key round-trips.
def test_full_file_round_trips(tmp_path):
    path = a_file(
        tmp_path,
        "[locate]\n"
        'sdk_package = "stripe"\n'
        "\n[locate.operations]\n"
        '"DELETE /v1/charges/{id}" = "charges.delete"\n'
        "\n[locate.fields]\n"
        '"Charge.amount" = "amount_cents"\n'
        "\n[tenon]\n"
        'command = ["python", "-m", "pytest", "-q"]\n'
        'require = "UNVERIFIED"\n'
        "breaking_only = true\n",
    )

    assert load_cli_config(path) == CliConfig(
        locate=LocateConfig(
            sdk_package="stripe",
            operations={"DELETE /v1/charges/{id}": "charges.delete"},
            fields={"Charge.amount": "amount_cents"},
        ),
        command=("python", "-m", "pytest", "-q"),
        require=ProofLevel.UNVERIFIED,
        breaking_only=True,
    )


# Spec AC3: a malformed key is refused by name, not with a traceback.
@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[tenon]\ncommand = []\n", "[locate]"),
        ("[locate]\noperations = {}\n", "sdk_package"),
        ('locate = "stripe"\n', "[locate]"),
        (
            '[locate]\nsdk_package = "stripe"\noperations = ["x"]\n',
            "operations",
        ),
        ('[locate]\nsdk_package = "stripe"\nfields = ["x"]\n', "fields"),
        ('tenon = true\n[locate]\nsdk_package = "stripe"\n', "[tenon]"),
        ('[locate]\nsdk_package = "stripe"\n\n[tenon]\ncommand = "pytest"\n', "command"),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\ncommand = ["pytest", ""]\n',
            "command",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\ncommand = ["pytest", 1]\n',
            "command",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nbreaking_only = "yes"\n',
            "breaking_only",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nrequire = "BY_HAND"\n',
            "T7",
        ),
    ],
)
def test_load_cli_config_validates_a_malformed_key(tmp_path, text, key):
    path = a_file(tmp_path, text)

    with pytest.raises(ValueError, match=re.escape(key)):
        load_cli_config(path)


# Spec AC3: a bad file is one ValueError that names the path.
def test_load_cli_config_validates_a_parse_error(tmp_path):
    path = a_file(tmp_path, "[locate\n")

    with pytest.raises(ValueError, match=re.escape(str(path))):
        load_cli_config(path)


# Spec AC3: a missing file is one ValueError that names the path.
def test_load_cli_config_validates_a_missing_file(tmp_path):
    path = tmp_path / "tenon.toml"

    with pytest.raises(ValueError, match=re.escape(str(path))):
        load_cli_config(path)


# Spec AC4: --sdk-package replaces the package the file supplied.
def test_overrides_replaces_the_sdk_package():
    result = overrides(a_config(sdk_package="stripe"), sdk_package="chargebee")

    assert result.locate.sdk_package == "chargebee"
    assert result.command == ()
    assert result.require is ProofLevel.TESTS_PASSED


# Spec AC4: --operation and --field merge over the table, with flags winning.
def test_overrides_merges_operations_and_fields():
    config = a_config(
        operations={"a": "one", "b": "two"},
        fields={"Charge.amount": "amount_cents"},
    )

    result = overrides(
        config,
        operations=["b=changed", "c=three"],
        fields=["Charge.currency=currency"],
    )

    assert dict(result.locate.operations) == {"a": "one", "b": "changed", "c": "three"}
    assert dict(result.locate.fields) == {
        "Charge.amount": "amount_cents",
        "Charge.currency": "currency",
    }
    assert dict(config.locate.operations) == {"a": "one", "b": "two"}


# Spec AC4: KEY=VALUE splits on the first '=', so a value may contain '='.
def test_overrides_splits_a_pair_on_the_first_equals():
    result = overrides(a_config(), operations=["GET /v1/x?a=b=path"])

    assert dict(result.locate.operations) == {"GET /v1/x?a": "b=path"}


# Spec AC4: --check replaces the command and is split with shlex, not a shell.
def test_overrides_shlex_splits_the_check_command():
    result = overrides(a_config(command=("old",)), command="python -m pytest -q")

    assert result.command == ("python", "-m", "pytest", "-q")


# Spec AC4: --require replaces the proof level.
def test_overrides_replaces_the_require_level():
    result = overrides(a_config(), require="UNVERIFIED")

    assert result.require is ProofLevel.UNVERIFIED


# Spec AC4: --breaking-only and --no-breaking-only replace only when supplied.
@pytest.mark.parametrize(
    ("config", "flag", "expected"),
    [
        (a_config(breaking_only=True), False, False),
        (a_config(breaking_only=False), True, True),
        (a_config(breaking_only=True), None, True),
    ],
)
def test_overrides_replaces_breaking_only(config, flag, expected):
    result = overrides(config, breaking_only=flag)

    assert result.breaking_only is expected


# Spec AC5: a bad flag pair or a blank --check is a ValueError naming the flag.
@pytest.mark.parametrize(
    ("kwargs", "key"),
    [
        ({"operations": ["missing-equals"]}, "--operation"),
        ({"operations": ["=x"]}, "--operation"),
        ({"operations": ["x="]}, "--operation"),
        ({"fields": ["=x"]}, "--field"),
        ({"command": ""}, "--check"),
        ({"command": "   "}, "--check"),
        ({"require": "BY_HAND"}, "T7"),
    ],
)
def test_overrides_rejects_bad_flags(kwargs, key):
    with pytest.raises(ValueError, match=re.escape(key)):
        overrides(a_config(), **kwargs)
