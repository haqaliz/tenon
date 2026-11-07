import json
from dataclasses import FrozenInstanceError

import pytest

from tenon.locate import LocateConfig
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
