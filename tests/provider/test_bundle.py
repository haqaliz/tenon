import json
from dataclasses import FrozenInstanceError

import pytest

from tenon.locate import LocateConfig, McpLocateConfig, TsLocateConfig
from tenon.prove import ProofLevel
from tenon.provider.bundle import MigrationBundle, load_bundle


def a_spec(tmp_path, name):
    path = tmp_path / name
    path.write_text("{}")
    return path


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
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(a_data(**overrides)))
    return path


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


# Spec AC3: only the two shipped sources are accepted.
def test_unknown_source_is_an_error(tmp_path):
    path = a_bundle(tmp_path, source="graphql")

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "source" in str(error.value)


# Spec AC3: only the two shipped languages are accepted.
def test_unknown_language_is_an_error(tmp_path):
    path = a_bundle(tmp_path, language="rust")

    with pytest.raises(ValueError) as error:
        load_bundle(path)

    assert str(path) in str(error.value)
    assert "language" in str(error.value)
