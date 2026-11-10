import json
from dataclasses import FrozenInstanceError

import pytest

from tenon.locate import (
    LocateConfig,
    McpLocateConfig,
    RustLocateConfig,
    TsLocateConfig,
)
from tenon.prove import ProofLevel
from tenon.provider.bundle import load_bundle


MISSING = object()


def a_spec(tmp_path, name):
    path = tmp_path / name
    path.write_text("{}")
    return path


def a_file(tmp_path, data):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(data))
    return path


def a_named_error(tmp_path, data, key):
    a_spec(tmp_path, "old.json")
    a_spec(tmp_path, "new.json")
    path = a_file(tmp_path, data)
    with pytest.raises(ValueError) as error:
        load_bundle(path)
    assert str(path) in str(error.value)
    assert key in str(error.value)
    return error


def a_data(**overrides):
    data = {
        "provider": "stripe",
        "migration": "v2500-v2596",
        "source": "openapi",
        "language": "python",
        "old": "old.json",
        "new": "new.json",
        "locate": {"sdk_package": "stripe"},
    }
    data.update(overrides)
    return data


def a_bundle(tmp_path, **overrides):
    a_spec(tmp_path, "old.json")
    a_spec(tmp_path, "new.json")
    return a_file(tmp_path, a_data(**overrides))


# Spec AC1: every bundle key lands on the dataclass.
def test_full_bundle_loads(tmp_path):
    path = a_bundle(
        tmp_path,
        command=["pytest", "tests/test_checkout.py"],
        build=["python", "-m", "build"],
        characterize=["python", "scripts/characterize.py"],
        replay=["python", "scripts/replay.py"],
        require="REPLAYED",
        breaking_only=True,
        locate={
            "sdk_package": "stripe",
            "operations": {"POST /v1/checkout/sessions": "checkout.Session.create"},
            "fields": {"amount": "amount_total"},
        },
    )

    bundle = load_bundle(path)

    assert bundle.provider == "stripe"
    assert bundle.migration == "v2500-v2596"
    assert bundle.source == "openapi"
    assert bundle.language == "python"
    assert bundle.locate == LocateConfig(
        sdk_package="stripe",
        operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
        fields={"amount": "amount_total"},
    )
    assert bundle.command == ("pytest", "tests/test_checkout.py")
    assert bundle.build == ("python", "-m", "build")
    assert bundle.characterize == ("python", "scripts/characterize.py")
    assert bundle.replay == ("python", "scripts/replay.py")
    assert bundle.require is ProofLevel.REPLAYED
    assert bundle.breaking_only is True


# Spec AC1: only the required keys are needed; the rest are shipped defaults.
def test_minimal_bundle_uses_defaults(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path))

    assert bundle.command == ()
    assert bundle.build == ()
    assert bundle.characterize == ()
    assert bundle.replay == ()
    assert bundle.require is ProofLevel.TESTS_PASSED
    assert bundle.breaking_only is False


# Spec AC1: an OpenAPI Python bundle builds a LocateConfig.
def test_openapi_python_bundle_uses_locate_config(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path))

    assert isinstance(bundle.locate, LocateConfig)


# Spec AC5: description/provider_url and unknown keys are ignored.
def test_unknown_keys_are_ignored(tmp_path):
    bundle = load_bundle(
        a_bundle(
            tmp_path,
            description="Stripe payment method rename",
            provider_url="https://stripe.example/migrations",
            future_key={"anything": True},
        )
    )

    assert bundle.provider == "stripe"
    assert not hasattr(bundle, "description")
    assert not hasattr(bundle, "future_key")


# Spec AC1: the bundle is an immutable, slotted value.
def test_bundle_is_frozen_and_slotted(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path))

    assert not hasattr(bundle, "__dict__")
    with pytest.raises(FrozenInstanceError):
        bundle.provider = "other"


# Spec AC2: relative specs resolve against the bundle's directory.
def test_relative_specs_resolve_against_the_bundle_dir(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path))

    assert bundle.old == (tmp_path / "old.json").resolve()
    assert bundle.new == (tmp_path / "new.json").resolve()


# Spec AC2: absolute spec paths work unchanged.
def test_absolute_spec_paths_work(tmp_path):
    old = a_spec(tmp_path, "old.json").resolve()
    new = a_spec(tmp_path, "new.json").resolve()
    path = a_bundle(tmp_path, old=str(old), new=str(new))

    bundle = load_bundle(path)

    assert bundle.old == old
    assert bundle.new == new


# Spec AC2: a missing spec is a named error.
@pytest.mark.parametrize("key", ["old", "new"])
def test_missing_spec_is_a_named_error(tmp_path, key):
    path = a_bundle(tmp_path, **{key: "missing.json"})

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert key in str(error.value)


# Spec AC3: the locate config follows source and language.
@pytest.mark.parametrize(
    ("source", "language", "sdk_package", "expected_type"),
    [
        ("openapi", "python", "stripe", LocateConfig),
        ("openapi", "ts", "stripe", TsLocateConfig),
        ("openapi", "rust", "stripe", RustLocateConfig),
        ("mcp", "python", "mcp", McpLocateConfig),
    ],
)
def test_locate_type_follows_source_and_language(
    tmp_path, source, language, sdk_package, expected_type
):
    path = a_bundle(
        tmp_path,
        source=source,
        language=language,
        locate={"sdk_package": sdk_package},
    )

    bundle = load_bundle(path)

    assert isinstance(bundle.locate, expected_type)


# Spec AC3: mcp is Python-only.
def test_mcp_with_ts_is_an_error(tmp_path):
    path = a_bundle(
        tmp_path, source="mcp", language="ts", locate={"sdk_package": "mcp"}
    )

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "mcp" in str(error.value)


# Spec AC3/AC4: mcp with Rust is the same named bundle error.
def test_mcp_with_rust_is_an_error(tmp_path):
    path = a_bundle(
        tmp_path, source="mcp", language="rust", locate={"sdk_package": "mcp"}
    )

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "mcp requires language python" in str(error.value)


# Spec AC4: a Rust bundle validates the crate identifier by name.
@pytest.mark.parametrize("crate", ["a::b", "a/b", ""])
def test_rust_bundle_with_a_bad_crate_is_an_error(tmp_path, crate):
    path = a_bundle(
        tmp_path, language="rust", locate={"sdk_package": crate}
    )

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "sdk_package" in str(error.value)
    if crate:
        assert "Rust crate" in str(error.value)


# Spec AC3: only the two shipped sources are accepted.
def test_unknown_source_is_an_error(tmp_path):
    path = a_bundle(tmp_path, source="graphql")

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "source" in str(error.value)


# Spec AC3: only the three shipped languages are accepted.
def test_unknown_language_is_an_error(tmp_path):
    path = a_bundle(tmp_path, language="go")

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "python, ts or rust" in str(error.value)


# Spec AC4: every required string key is present and non-blank.
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("provider", MISSING),
        ("provider", ""),
        ("provider", "   "),
        ("migration", MISSING),
        ("migration", ""),
        ("migration", "  "),
        ("source", MISSING),
        ("source", ""),
        ("language", MISSING),
        ("language", " "),
        ("old", MISSING),
        ("old", ""),
        ("new", MISSING),
        ("new", " "),
    ],
)
def test_missing_or_blank_key_is_a_named_error(tmp_path, key, value):
    data = a_data()
    if value is MISSING:
        del data[key]
    else:
        data[key] = value

    a_named_error(tmp_path, data, key)


# Spec AC4: locate must be an object.
@pytest.mark.parametrize("locate", [MISSING, None, "", []])
def test_bad_locate_is_a_named_error(tmp_path, locate):
    data = a_data()
    if locate is MISSING:
        del data["locate"]
    else:
        data["locate"] = locate

    a_named_error(tmp_path, data, "locate")


# Spec AC4: sdk_package is required, non-blank and a valid package.
@pytest.mark.parametrize("sdk_package", [MISSING, None, "", "   "])
def test_bad_sdk_package_is_a_named_error(tmp_path, sdk_package):
    locate = {}
    if sdk_package is not MISSING:
        locate["sdk_package"] = sdk_package

    a_named_error(tmp_path, a_data(locate=locate), "sdk_package")


def test_invalid_sdk_package_is_a_named_error(tmp_path):
    a_named_error(
        tmp_path, a_data(locate={"sdk_package": "not a package"}), "sdk_package"
    )


# Spec AC4: operations and fields are string mappings.
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("operations", ["a"]),
        ("operations", "a"),
        ("fields", {"amount": 1}),
        ("fields", []),
    ],
)
def test_non_string_mapping_is_a_named_error(tmp_path, key, value):
    a_named_error(
        tmp_path,
        a_data(locate={"sdk_package": "stripe", **{key: value}}),
        key,
    )


# Spec AC4: require is one of the five shipped proof levels.
@pytest.mark.parametrize("require", ["SOMETIMES", 3, []])
def test_bad_require_is_a_named_error(tmp_path, require):
    a_named_error(tmp_path, a_data(require=require), "require")


# Spec AC4: each stage command is an array, never a bare string.
@pytest.mark.parametrize("key", ["check", "command", "build", "characterize", "replay"])
@pytest.mark.parametrize("value", ["pytest", [""], ["pytest", 3], ["pytest", "  "]])
def test_bad_command_is_a_named_error(tmp_path, key, value):
    a_named_error(tmp_path, a_data(**{key: value}), key)


# Spec AC4: an empty command array is allowed; only its elements must be non-empty.
def test_empty_command_array_is_allowed(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path, command=[]))

    assert bundle.command == ()


# Spec AC1: the documented `check` key is the tests stage (the `command` alias
# remains for tenon.toml familiarity).
def test_check_key_loads_the_tests_command(tmp_path):
    bundle = load_bundle(a_bundle(tmp_path, check=["python", "-c", "pass"]))

    assert bundle.command == ("python", "-c", "pass")


# Spec AC4: breaking_only is a bool.
@pytest.mark.parametrize("value", ["true", 1, None])
def test_non_bool_breaking_only_is_a_named_error(tmp_path, value):
    a_named_error(tmp_path, a_data(breaking_only=value), "breaking_only")


# Spec AC5: malformed or empty JSON is a named error.
@pytest.mark.parametrize("text", ["{not json", ""])
def test_bad_json_is_a_named_error(tmp_path, text):
    path = tmp_path / "bundle.json"
    path.write_text(text)

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)


# Spec AC5: valid JSON that is not a bundle object is a named error.
def test_non_object_json_is_a_named_error(tmp_path):
    path = tmp_path / "bundle.json"
    path.write_text("[]")

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)


# Spec AC5: a missing bundle file is a named error.
def test_missing_bundle_file_is_a_named_error(tmp_path):
    path = tmp_path / "absent.json"

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)


# Spec: the package surface is the bundle and its loader.
def test_package_exports_the_bundle_and_loader(tmp_path):
    from tenon.provider import MigrationBundle, load_bundle

    bundle = load_bundle(a_bundle(tmp_path))

    assert isinstance(bundle, MigrationBundle)
