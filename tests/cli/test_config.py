from tenon.cli import CliConfig, load_cli_config
from tenon.locate import LocateConfig
from tenon.prove import ProofLevel


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
