import re

import pytest

from tenon.cli import CliConfig, load_cli_config, overrides, resolve_config_path
from tenon.locate import LocateConfig, TsLocateConfig
from tenon.prove import ProofLevel


def a_config(
    *,
    sdk_package="stripe",
    operations=None,
    fields=None,
    command=(),
    require=ProofLevel.TESTS_PASSED,
    breaking_only=False,
    language="python",
):
    locate_type = TsLocateConfig if language == "ts" else LocateConfig
    return CliConfig(
        locate=locate_type(
            sdk_package=sdk_package,
            operations=operations or {},
            fields=fields or {},
        ),
        command=command,
        require=require,
        breaking_only=breaking_only,
        language=language,
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


# Spec AC1: no language key and no argument is the shipped Python path.
def test_minimal_file_defaults_to_python(tmp_path):
    path = a_file(tmp_path, '[locate]\nsdk_package = "stripe"\n')

    config = load_cli_config(path)

    assert config.language == "python"
    assert isinstance(config.locate, LocateConfig)


# Spec AC2: the file selects TypeScript and still reads every [tenon] key.
def test_file_selects_ts_and_keeps_the_tenon_keys(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "ts"\nsdk_package = "stripe"\n'
        '\n[tenon]\ncommand = ["npm", "test"]\nrequire = "UNVERIFIED"\n'
        "breaking_only = true\n",
    )

    config = load_cli_config(path)

    assert config.language == "ts"
    assert config.locate == TsLocateConfig(sdk_package="stripe")
    assert config.command == ("npm", "test")
    assert config.require is ProofLevel.UNVERIFIED
    assert config.breaking_only is True


# Spec AC2: the language argument overrides the file in both directions.
@pytest.mark.parametrize(
    ("file_language", "argument", "expected_type"),
    [
        (None, "ts", TsLocateConfig),
        ("ts", "python", LocateConfig),
    ],
)
def test_language_argument_overrides_the_file(
    tmp_path, file_language, argument, expected_type
):
    language_line = "" if file_language is None else f'language = "{file_language}"\n'
    path = a_file(tmp_path, f'[locate]\n{language_line}sdk_package = "stripe"\n')

    config = load_cli_config(path, language=argument)

    assert config.language == argument
    assert isinstance(config.locate, expected_type)


# Spec AC2: the shared operation and field tables apply to TypeScript too.
def test_ts_config_keeps_the_operation_tables(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "ts"\nsdk_package = "stripe"\n'
        '\n[locate.operations]\n"POST /v1/charges" = "charges.create"\n'
        '\n[locate.fields]\n"Charge.amount" = "amount_cents"\n',
    )

    config = load_cli_config(path)

    assert dict(config.locate.operations) == {"POST /v1/charges": "charges.create"}
    assert dict(config.locate.fields) == {"Charge.amount": "amount_cents"}


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
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\ncommand = "pytest"\n',
            "command",
        ),
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


# Spec AC5: the language must be python or ts, named with its key.
@pytest.mark.parametrize("language", ["ruby", "TypeScript", ""])
def test_load_cli_config_rejects_an_unknown_file_language(tmp_path, language):
    path = a_file(
        tmp_path, f'[locate]\nlanguage = "{language}"\nsdk_package = "stripe"\n'
    )

    with pytest.raises(ValueError, match=re.escape("[locate] language")):
        load_cli_config(path)


def test_load_cli_config_rejects_an_unknown_language_argument(tmp_path):
    path = a_file(tmp_path, '[locate]\nsdk_package = "stripe"\n')

    with pytest.raises(ValueError, match=re.escape("[locate] language")):
        load_cli_config(path, language="ruby")


# Spec AC5: a TypeScript config validates the package as npm.
def test_load_cli_config_rejects_a_non_npm_package(tmp_path):
    path = a_file(
        tmp_path, '[locate]\nlanguage = "ts"\nsdk_package = "acme/client"\n'
    )

    with pytest.raises(ValueError, match="sdk_package"):
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


# Spec AC2: overrides keep the language unless the flag supplies one.
def test_overrides_keeps_ts_with_the_package_flag():
    config = a_config(language="ts", sdk_package="stripe")

    result = overrides(config, sdk_package="chargebee")

    assert result.language == "ts"
    assert isinstance(result.locate, TsLocateConfig)
    assert result.locate.sdk_package == "chargebee"


# Spec AC2: a language change rebuilds the config type from the same package.
def test_overrides_changes_the_language_from_the_existing_package():
    result = overrides(a_config(sdk_package="stripe"), language="ts")

    assert result.language == "ts"
    assert isinstance(result.locate, TsLocateConfig)
    assert result.locate.sdk_package == "stripe"

    result = overrides(a_config(language="ts"), language="python")

    assert result.language == "python"
    assert isinstance(result.locate, LocateConfig)
    assert result.locate.sdk_package == "stripe"


# Spec AC2: merging operations keeps a TS config TS.
def test_overrides_keeps_ts_when_merging_operations():
    result = overrides(a_config(language="ts"), operations=["a=b"])

    assert isinstance(result.locate, TsLocateConfig)
    assert dict(result.locate.operations) == {"a": "b"}


# Spec AC2/AC5: the package must be valid in the language it moves to.
def test_overrides_rejects_a_package_the_new_language_cannot_use():
    # Python's identifier rule accepts ``café``; npm's ASCII rule does not.
    config = a_config(sdk_package="café")

    with pytest.raises(ValueError, match="sdk_package"):
        overrides(config, language="ts")


def test_overrides_rejects_an_unknown_language():
    with pytest.raises(ValueError, match=re.escape("--language")):
        overrides(a_config(), language="ruby")


# Spec AC5: CliConfig itself refuses an unknown language.
def test_cli_config_rejects_an_unknown_language():
    with pytest.raises(ValueError, match="language"):
        CliConfig(locate=LocateConfig(sdk_package="stripe"), language="ruby")


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


# Spec AC6: --config wins even when the repo has its own tenon.toml.
def test_resolve_config_path_prefers_the_explicit_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tenon.toml").write_text('[locate]\nsdk_package = "stripe"\n')
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[locate]\nsdk_package = "chargebee"\n')

    assert resolve_config_path(repo, str(explicit)) == explicit


# Spec AC6: otherwise <repo>/tenon.toml is found when present.
def test_resolve_config_path_finds_the_repo_file(tmp_path):
    path = tmp_path / "tenon.toml"
    path.write_text('[locate]\nsdk_package = "stripe"\n')

    assert resolve_config_path(tmp_path, None) == path


# Spec AC6: an absent file returns None, not a crash.
def test_resolve_config_path_returns_none_when_absent(tmp_path):
    assert resolve_config_path(tmp_path, None) is None


# Spec AC6: the caller builds the empty config from --sdk-package.
def test_empty_config_uses_the_sdk_package_flag(tmp_path):
    assert resolve_config_path(tmp_path, None) is None

    assert CliConfig(locate=LocateConfig(sdk_package="stripe")) == a_config()


# Spec AC6: no file and no package from either source is a ValueError.
def test_empty_config_without_an_sdk_package_is_refused(tmp_path):
    assert resolve_config_path(tmp_path, None) is None

    with pytest.raises(ValueError, match="sdk_package"):
        CliConfig(locate=LocateConfig(sdk_package=""))
