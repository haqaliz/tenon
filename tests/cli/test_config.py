import re

import pytest

from tenon.cli import CliConfig, load_cli_config, overrides, resolve_config_path
from tenon.locate import (
    CSharpLocateConfig,
    GoLocateConfig,
    LocateConfig,
    McpLocateConfig,
    RustLocateConfig,
    TsLocateConfig,
)
from tenon.prove import ProofLevel

LOCATE_TYPES = {
    "python": LocateConfig,
    "ts": TsLocateConfig,
    "rust": RustLocateConfig,
    "go": GoLocateConfig,
    "csharp": CSharpLocateConfig,
}

PACKAGES = {
    "python": "stripe",
    "ts": "stripe",
    "rust": "stripe",
    "go": "github.com/stripe/stripe-go/v76",
    "csharp": "Stripe",
}


def a_config(
    *,
    sdk_package="stripe",
    operations=None,
    fields=None,
    receivers=None,
    command=(),
    build=(),
    characterize=(),
    replay=(),
    require=ProofLevel.TESTS_PASSED,
    breaking_only=False,
    language="python",
    source="openapi",
    package_name=None,
):
    if source == "mcp":
        locate = McpLocateConfig(client_package=sdk_package)
    elif language == "go":
        locate = GoLocateConfig(
            sdk_package=sdk_package,
            package_name=package_name,
            operations=operations or {},
            fields=fields or {},
            receivers=receivers or {},
        )
    else:
        locate = LOCATE_TYPES[language](
            sdk_package=sdk_package,
            operations=operations or {},
            fields=fields or {},
            receivers=receivers or {},
        )
    return CliConfig(
        locate=locate,
        command=command,
        build=build,
        characterize=characterize,
        replay=replay,
        require=require,
        breaking_only=breaking_only,
        language=language,
        source=source,
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


# Spec AC1/AC3: the file selects Rust and keeps the shared mappings.
def test_file_selects_rust_and_keeps_the_operation_tables(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "rust"\nsdk_package = "stripe"\n'
        '\n[locate.operations]\n"POST /v1/charges" = "Charge.create"\n'
        '\n[locate.fields]\n"Charge.amount" = "amount_cents"\n',
    )

    config = load_cli_config(path)

    assert config.language == "rust"
    assert config.locate == RustLocateConfig(
        sdk_package="stripe",
        operations={"POST /v1/charges": "Charge.create"},
        fields={"Charge.amount": "amount_cents"},
    )


# Spec AC3: a Rust crate is one identifier; a path or a blank is named.
@pytest.mark.parametrize("crate", ["a::b", "a/b", ""])
def test_load_cli_config_rejects_a_bad_rust_crate(tmp_path, crate):
    path = a_file(
        tmp_path, f'[locate]\nlanguage = "rust"\nsdk_package = "{crate}"\n'
    )

    with pytest.raises(ValueError) as raised:
        load_cli_config(path)

    assert "sdk_package" in str(raised.value)
    assert "Rust crate" in str(raised.value)


# Spec AC3: MCP stays Python-only for the file's Rust language.
def test_mcp_source_rejects_rust_in_the_file(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nlanguage = "rust"\nsdk_package = "stripe"\n',
    )

    with pytest.raises(ValueError, match="mcp.*python"):
        load_cli_config(path)


# Spec AC3: the file selects Go and reads the optional package name.
def test_file_selects_go_and_keeps_the_package_name(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "go"\n'
        'sdk_package = "github.com/stripe/stripe-go/v76"\n'
        'package_name = "stripe"\n'
        '\n[locate.fields]\n"ChargeParams.AmountCents" = "AmountCents"\n',
    )

    config = load_cli_config(path)

    assert config.language == "go"
    assert config.locate == GoLocateConfig(
        sdk_package="github.com/stripe/stripe-go/v76",
        package_name="stripe",
        fields={"ChargeParams.AmountCents": "AmountCents"},
    )


# Spec AC3: a bad Go package name from the file is a named error.
def test_load_cli_config_rejects_a_bad_go_package_name(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "go"\n'
        'sdk_package = "github.com/stripe/stripe-go/v76"\n'
        'package_name = "not-a-name"\n',
    )

    with pytest.raises(ValueError, match="package_name"):
        load_cli_config(path)


# Spec AC2: [locate.receivers] reaches the Rust config.
def test_file_selects_rust_and_keeps_the_receiver_mapping(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "rust"\nsdk_package = "stripe"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = "Client"\n',
    )

    config = load_cli_config(path)

    assert isinstance(config.locate, RustLocateConfig)
    assert dict(config.locate.receivers) == {"stripe.NewClient": "Client"}


# Spec AC2: [locate.receivers] reaches the Go config.
def test_file_selects_go_and_keeps_the_receiver_mapping(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "go"\n'
        'sdk_package = "github.com/stripe/stripe-go/v76"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = "Client"\n',
    )

    config = load_cli_config(path)

    assert isinstance(config.locate, GoLocateConfig)
    assert dict(config.locate.receivers) == {"stripe.NewClient": "Client"}


# Spec AC2: a non-string receiver entry is a named error for every language.
@pytest.mark.parametrize("language", list(LOCATE_TYPES))
def test_load_cli_config_rejects_a_non_string_receiver(tmp_path, language):
    path = a_file(
        tmp_path,
        f'[locate]\nlanguage = "{language}"\n'
        f'sdk_package = "{PACKAGES[language]}"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = 1\n',
    )

    with pytest.raises(ValueError, match="receivers"):
        load_cli_config(path)


# Spec AC2: receivers is a table, not an array, for every language.
@pytest.mark.parametrize("language", list(LOCATE_TYPES))
def test_load_cli_config_rejects_a_non_table_receiver_mapping(tmp_path, language):
    path = a_file(
        tmp_path,
        f'[locate]\nlanguage = "{language}"\n'
        f'sdk_package = "{PACKAGES[language]}"\n'
        'receivers = ["stripe.NewClient"]\n',
    )

    with pytest.raises(ValueError, match="receivers"):
        load_cli_config(path)


# Spec AC2: [locate.receivers] reaches the Python, TS and C# configs too.
@pytest.mark.parametrize("language", ["python", "ts", "csharp"])
def test_file_keeps_the_receiver_mapping_for_every_language(tmp_path, language):
    path = a_file(
        tmp_path,
        f'[locate]\nlanguage = "{language}"\n'
        f'sdk_package = "{PACKAGES[language]}"\n'
        '\n[locate.receivers]\n"stripe.NewClient" = "Client"\n',
    )

    config = load_cli_config(path)

    assert isinstance(config.locate, LOCATE_TYPES[language])
    assert dict(config.locate.receivers) == {"stripe.NewClient": "Client"}


# Spec AC3: the file selects C# and keeps the shared operation/field tables.
def test_file_selects_csharp_and_keeps_the_mappings(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nlanguage = "csharp"\nsdk_package = "Stripe"\n'
        '\n[locate.operations]\n"POST /v1/charges" = "ChargeService.Create"\n'
        '\n[locate.fields]\n'
        '"ChargeCreateOptions.AmountCents" = "AmountCents"\n',
    )

    config = load_cli_config(path)

    assert config.language == "csharp"
    assert config.locate == CSharpLocateConfig(
        sdk_package="Stripe",
        operations={"POST /v1/charges": "ChargeService.Create"},
        fields={"ChargeCreateOptions.AmountCents": "AmountCents"},
    )


# Spec AC3: a C# namespace root is dotted names; a blank, path or `::` is named.
@pytest.mark.parametrize("root", ["", "a/b", "a::b"])
def test_load_cli_config_rejects_a_bad_csharp_namespace(tmp_path, root):
    path = a_file(
        tmp_path, f'[locate]\nlanguage = "csharp"\nsdk_package = "{root}"\n'
    )

    with pytest.raises(ValueError, match="sdk_package") as raised:
        load_cli_config(path)

    assert "C# namespace" in str(raised.value)


# Spec AC3: MCP stays Python-only for the file's C# language.
def test_mcp_source_rejects_csharp_in_the_file(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nlanguage = "csharp"\nsdk_package = "Stripe"\n',
    )

    with pytest.raises(ValueError, match="mcp.*python"):
        load_cli_config(path)


# Spec AC3: MCP stays Python-only for the file's Go language.
def test_mcp_source_rejects_go_in_the_file(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nlanguage = "go"\nsdk_package = "stripe"\n',
    )

    with pytest.raises(ValueError, match="mcp.*python"):
        load_cli_config(path)


# Spec AC2: the language argument overrides the file in both directions.
@pytest.mark.parametrize(
    ("file_language", "argument", "expected_type"),
    [
        (None, "ts", TsLocateConfig),
        ("ts", "python", LocateConfig),
        (None, "rust", RustLocateConfig),
        ("rust", "python", LocateConfig),
        (None, "go", GoLocateConfig),
        ("go", "python", LocateConfig),
        (None, "csharp", CSharpLocateConfig),
        ("csharp", "python", LocateConfig),
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


# Spec AC1: no source key and no flag is the shipped OpenAPI path.
def test_minimal_file_defaults_to_the_openapi_source(tmp_path):
    path = a_file(tmp_path, '[locate]\nsdk_package = "stripe"\n')

    config = load_cli_config(path)

    assert config.source == "openapi"
    assert isinstance(config.locate, LocateConfig)


# Spec AC2: the file selects MCP and builds the MCP locate config.
def test_file_selects_mcp_and_builds_the_mcp_config(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nsdk_package = "mcp"\n',
    )

    config = load_cli_config(path)

    assert config.source == "mcp"
    assert config.language == "python"
    assert config.locate == McpLocateConfig(client_package="mcp")


# Spec AC2/AC5: the MCP client package defaults to mcp.
def test_mcp_source_defaults_the_client_package_to_mcp(tmp_path):
    path = a_file(tmp_path, '[locate]\nsource = "mcp"\n')

    assert load_cli_config(path).locate == McpLocateConfig()


# Spec AC2: --source overrides the file in both directions.
@pytest.mark.parametrize(
    ("file_text", "argument", "expected_type"),
    [
        ('[locate]\nsdk_package = "stripe"\n', "mcp", McpLocateConfig),
        (
            '[locate]\nsource = "mcp"\nsdk_package = "mcp"\n',
            "openapi",
            LocateConfig,
        ),
    ],
)
def test_source_argument_overrides_the_file(
    tmp_path, file_text, argument, expected_type
):
    path = a_file(tmp_path, file_text)

    config = load_cli_config(path, source=argument)

    assert config.source == argument
    assert isinstance(config.locate, expected_type)


# Spec AC5: MCP is Python-only, named with the source key.
def test_mcp_source_rejects_ts_in_the_file(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nlanguage = "ts"\nsdk_package = "mcp"\n',
    )

    with pytest.raises(ValueError, match="mcp.*python"):
        load_cli_config(path)


def test_mcp_source_rejects_the_ts_argument(tmp_path):
    path = a_file(tmp_path, '[locate]\nsource = "mcp"\nsdk_package = "mcp"\n')

    with pytest.raises(ValueError, match="mcp.*python"):
        load_cli_config(path, language="ts")


# Spec AC2: an unknown source is refused by name.
@pytest.mark.parametrize("source", ["graphql", "OpenAPI", ""])
def test_load_cli_config_rejects_an_unknown_source(tmp_path, source):
    path = a_file(
        tmp_path, f'[locate]\nsource = "{source}"\nsdk_package = "stripe"\n'
    )

    with pytest.raises(ValueError, match=re.escape("[locate] source")):
        load_cli_config(path)


def test_load_cli_config_rejects_an_unknown_source_argument(tmp_path):
    path = a_file(tmp_path, '[locate]\nsdk_package = "stripe"\n')

    with pytest.raises(ValueError, match=re.escape("[locate] source")):
        load_cli_config(path, source="graphql")


# Spec AC2: the OpenAPI-only tables are accepted and ignored in MCP mode.
def test_mcp_source_ignores_the_operation_tables(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsource = "mcp"\nsdk_package = "mcp"\n'
        '\n[locate.operations]\n"POST /v1/charges" = "charges.create"\n'
        '\n[locate.fields]\n"Charge.amount" = "amount_cents"\n',
    )

    assert load_cli_config(path).locate == McpLocateConfig(client_package="mcp")


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


# Spec AC1: [tenon] carries one array per proof stage next to command.
def test_file_loads_every_stage_command(tmp_path):
    path = a_file(
        tmp_path,
        '[locate]\nsdk_package = "stripe"\n'
        "\n[tenon]\n"
        'command = ["pytest"]\n'
        'build = ["python", "-c", "import acme"]\n'
        'characterize = ["python", "-c", "characterize"]\n'
        'replay = ["python", "-c", "replay"]\n',
    )

    config = load_cli_config(path)

    assert config.command == ("pytest",)
    assert config.build == ("python", "-c", "import acme")
    assert config.characterize == ("python", "-c", "characterize")
    assert config.replay == ("python", "-c", "replay")


# Spec AC2: every ladder level is a valid [tenon] require.
@pytest.mark.parametrize("level", list(ProofLevel))
def test_file_accepts_every_proof_level(tmp_path, level):
    path = a_file(
        tmp_path,
        f'[locate]\nsdk_package = "stripe"\n\n[tenon]\nrequire = "{level.value}"\n',
    )

    assert load_cli_config(path).require is level


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
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nbuild = "python"\n',
            "build",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\ncharacterize = [""]\n',
            "characterize",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nreplay = [1]\n',
            "replay",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nbreaking_only = "yes"\n',
            "breaking_only",
        ),
        (
            '[locate]\nsdk_package = "stripe"\n\n[tenon]\nrequire = "BY_HAND"\n',
            "TYPES_BUILD_ONLY",
        ),
    ],
)
def test_load_cli_config_validates_a_malformed_key(tmp_path, text, key):
    path = a_file(tmp_path, text)

    with pytest.raises(ValueError, match=re.escape(key)):
        load_cli_config(path)


# Spec AC5: the language must be python, ts, rust, go or csharp, named with its key.
@pytest.mark.parametrize("language", ["ruby", "TypeScript", ""])
def test_load_cli_config_rejects_an_unknown_file_language(tmp_path, language):
    path = a_file(
        tmp_path, f'[locate]\nlanguage = "{language}"\nsdk_package = "stripe"\n'
    )

    with pytest.raises(ValueError, match=re.escape("[locate] language")) as raised:
        load_cli_config(path)

    assert "python, ts, rust, go or csharp" in str(raised.value)


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


# Spec AC2/AC3: the language flag builds the Rust config from the same package.
def test_overrides_changes_the_language_to_rust():
    result = overrides(a_config(sdk_package="stripe"), language="rust")

    assert result.language == "rust"
    assert isinstance(result.locate, RustLocateConfig)
    assert result.locate.sdk_package == "stripe"


# Spec AC2: merging operations keeps a Rust config Rust.
def test_overrides_keeps_rust_when_merging_operations():
    result = overrides(a_config(language="rust"), operations=["a=b"])

    assert isinstance(result.locate, RustLocateConfig)
    assert dict(result.locate.operations) == {"a": "b"}


# Spec AC1/AC2: --language go builds the Go config and keeps --package-name.
def test_overrides_changes_the_language_to_go():
    result = overrides(
        a_config(sdk_package="stripe"), language="go", package_name="stripe"
    )

    assert result.language == "go"
    assert isinstance(result.locate, GoLocateConfig)
    assert result.locate.sdk_package == "stripe"
    assert result.locate.package_name == "stripe"


# Spec AC2/AC3: --language csharp builds the C# config from the same package.
def test_overrides_changes_the_language_to_csharp():
    result = overrides(a_config(sdk_package="Stripe"), language="csharp")

    assert result.language == "csharp"
    assert isinstance(result.locate, CSharpLocateConfig)
    assert result.locate.sdk_package == "Stripe"


# Spec AC2: merging operations keeps a C# config C#.
def test_overrides_keeps_csharp_when_merging_operations():
    config = a_config(language="csharp", sdk_package="Stripe")

    result = overrides(config, operations=["a=b"])

    assert isinstance(result.locate, CSharpLocateConfig)
    assert dict(result.locate.operations) == {"a": "b"}


# Spec AC2: merging operations keeps a Go config and its package name.
def test_overrides_keeps_go_when_merging_operations():
    config = a_config(
        language="go",
        sdk_package="github.com/stripe/stripe-go/v76",
        package_name="stripe",
    )

    result = overrides(config, operations=["a=b"])

    assert isinstance(result.locate, GoLocateConfig)
    assert result.locate.package_name == "stripe"
    assert dict(result.locate.operations) == {"a": "b"}


# Spec AC4: --receiver merges over the config, with flags winning.
def test_overrides_merges_receivers_with_flags_winning():
    config = a_config(language="rust", receivers={"a": "One", "b": "Two"})

    result = overrides(config, receivers=["b=Changed", "c=Three"])

    assert isinstance(result.locate, RustLocateConfig)
    assert dict(result.locate.receivers) == {
        "a": "One",
        "b": "Changed",
        "c": "Three",
    }
    assert dict(config.locate.receivers) == {"a": "One", "b": "Two"}


# Spec AC4: a Go receiver merge keeps the package name.
def test_overrides_keeps_go_when_merging_receivers():
    config = a_config(
        language="go",
        sdk_package="github.com/stripe/stripe-go/v76",
        package_name="stripe",
        receivers={"a": "One"},
    )

    result = overrides(config, receivers=["b=Two"])

    assert isinstance(result.locate, GoLocateConfig)
    assert result.locate.package_name == "stripe"
    assert dict(result.locate.receivers) == {"a": "One", "b": "Two"}


# Spec AC4: --language rust carries the receiver flag into the new config.
def test_overrides_changes_the_language_to_rust_with_receivers():
    result = overrides(
        a_config(sdk_package="stripe"), language="rust", receivers=["a=b"]
    )

    assert isinstance(result.locate, RustLocateConfig)
    assert dict(result.locate.receivers) == {"a": "b"}


# Spec AC4: --receiver merges into every OpenAPI language's config.
@pytest.mark.parametrize("language", ["python", "ts", "csharp"])
def test_overrides_merges_receivers_for_every_language(language):
    config = a_config(language=language, receivers={"a": "One"})

    result = overrides(config, receivers=["b=Two"])

    assert isinstance(result.locate, LOCATE_TYPES[language])
    assert dict(result.locate.receivers) == {"a": "One", "b": "Two"}
    assert dict(config.locate.receivers) == {"a": "One"}


# Spec AC4: a flag receiver wins over a config receiver for every language.
@pytest.mark.parametrize("language", ["python", "ts", "csharp"])
def test_overrides_receiver_flags_win_for_every_language(language):
    config = a_config(language=language, receivers={"a": "File"})

    result = overrides(config, receivers=["a=Flag"])

    assert dict(result.locate.receivers) == {"a": "Flag"}


# Spec AC3: a bad --package-name is one named error.
def test_overrides_rejects_a_bad_package_name():
    with pytest.raises(ValueError, match="package_name"):
        overrides(a_config(language="go"), package_name="not-a-name")


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
    with pytest.raises(ValueError, match=re.escape("--language")) as raised:
        overrides(a_config(), language="ruby")

    assert "python, ts, rust, go or csharp" in str(raised.value)


# Spec AC2: a source change rebuilds the locate config and keeps the package.
def test_overrides_changes_the_source_to_mcp():
    result = overrides(a_config(sdk_package="stripe"), source="mcp")

    assert result.source == "mcp"
    assert result.locate == McpLocateConfig(client_package="stripe")


def test_overrides_changes_the_source_back_to_openapi():
    result = overrides(
        a_config(sdk_package="acme.mcp", source="mcp"), source="openapi"
    )

    assert result.source == "openapi"
    assert result.locate == LocateConfig(sdk_package="acme.mcp")


# Spec AC2: --sdk-package names the MCP client package.
def test_overrides_replaces_the_mcp_client_package():
    result = overrides(a_config(source="mcp"), sdk_package="acme.mcp")

    assert result.locate == McpLocateConfig(client_package="acme.mcp")


# Spec AC5: MCP with TypeScript is one named error.
def test_overrides_rejects_mcp_with_ts():
    with pytest.raises(ValueError, match="mcp.*python"):
        overrides(a_config(), source="mcp", language="ts")


# Spec AC3: MCP with Rust is the same named error.
def test_overrides_rejects_mcp_with_rust():
    with pytest.raises(ValueError, match="mcp.*python"):
        overrides(a_config(), source="mcp", language="rust")


# Spec AC3: MCP with Go is the same named error.
def test_overrides_rejects_mcp_with_go():
    with pytest.raises(ValueError, match="mcp.*python"):
        overrides(a_config(), source="mcp", language="go")


# Spec AC3: MCP with C# is the same named error.
def test_overrides_rejects_mcp_with_csharp():
    with pytest.raises(ValueError, match="mcp.*python"):
        overrides(a_config(), source="mcp", language="csharp")


# Spec AC2: an unknown --source names the flag.
def test_overrides_rejects_an_unknown_source():
    with pytest.raises(ValueError, match=re.escape("--source")):
        overrides(a_config(), source="graphql")


# Spec AC1: CliConfig accepts rust and its config type.
def test_cli_config_accepts_rust():
    config = CliConfig(
        locate=RustLocateConfig(sdk_package="stripe"), language="rust"
    )

    assert config.language == "rust"
    assert isinstance(config.locate, RustLocateConfig)


# Spec AC1: CliConfig accepts go and its config type.
def test_cli_config_accepts_go():
    config = CliConfig(
        locate=GoLocateConfig(sdk_package="github.com/stripe/stripe-go/v76"),
        language="go",
    )

    assert config.language == "go"
    assert isinstance(config.locate, GoLocateConfig)


# Spec AC1: CliConfig accepts csharp and its config type.
def test_cli_config_accepts_csharp():
    config = CliConfig(
        locate=CSharpLocateConfig(sdk_package="Stripe"), language="csharp"
    )

    assert config.language == "csharp"
    assert isinstance(config.locate, CSharpLocateConfig)


# Spec AC5: CliConfig itself refuses an unknown language, naming all five.
def test_cli_config_rejects_an_unknown_language():
    with pytest.raises(ValueError, match="language") as raised:
        CliConfig(locate=LocateConfig(sdk_package="stripe"), language="ruby")

    assert "python, ts, rust, go or csharp" in str(raised.value)


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


# Spec AC1: the stage flags are split with shlex and replace their stage.
def test_overrides_shlex_splits_the_stage_commands():
    result = overrides(
        a_config(),
        build="python -c 'import acme'",
        characterize="python -c characterize",
        replay="python -c replay",
    )

    assert result.build == ("python", "-c", "import acme")
    assert result.characterize == ("python", "-c", "characterize")
    assert result.replay == ("python", "-c", "replay")


# Spec AC1: a missing stage flag falls back to the config, and an empty stage stays empty.
def test_overrides_keeps_the_configured_stage_commands():
    config = a_config(build=("b",), characterize=(), replay=("r",))

    result = overrides(config, build="changed")

    assert result.build == ("changed",)
    assert result.characterize == ()
    assert result.replay == ("r",)


# Spec AC2: --require accepts every ladder level.
@pytest.mark.parametrize("level", list(ProofLevel))
def test_overrides_accepts_every_proof_level(level):
    assert overrides(a_config(), require=level.value).require is level


# Spec AC2: an unknown level names all five so the message teaches the ladder.
def test_an_unknown_level_error_names_all_five():
    with pytest.raises(ValueError) as raised:
        overrides(a_config(), require="BY_HAND")

    for level in ProofLevel:
        assert level.value in str(raised.value)


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
        ({"receivers": ["missing-equals"]}, "--receiver"),
        ({"receivers": ["=x"]}, "--receiver"),
        ({"receivers": ["x="]}, "--receiver"),
        ({"command": ""}, "--check"),
        ({"command": "   "}, "--check"),
        ({"build": ""}, "--build"),
        ({"characterize": "   "}, "--characterize"),
        ({"replay": ""}, "--replay"),
        ({"require": "BY_HAND"}, "TYPES_BUILD_ONLY"),
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
