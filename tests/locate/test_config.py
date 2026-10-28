import re
from pathlib import Path

import pytest

from tenon.locate import LocateConfig, load_config

FIXTURE = Path(__file__).parent.parent / "fixtures" / "tenon.toml"


# Spec AC7: all three tables round-trip from a fixture tenon.toml.
def test_load_config_reads_all_three_tables():
    assert load_config(FIXTURE) == LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.delete"},
        fields={"Charge.amount": "amount_cents"},
    )


# Spec AC7: a bad file is refused with the missing key named.
@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[other]\nx = 1\n", "[locate]"),
        ("[locate]\noperations = {}\n", "sdk_package"),
    ],
)
def test_load_config_names_the_missing_key(tmp_path, text, key):
    path = tmp_path / "tenon.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=re.escape(key)):
        load_config(path)
