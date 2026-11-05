"""Fixtures for the CLI tests: a temp repo, spec pairs and a config file."""

import json
import shutil
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
PROOF_BASIC = FIXTURES / "proof-basic"

# The M0.3 rename; the fixture call is ``client.charges.create(amount=amount)``.
OLD_SPEC = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
"""

NEW_SPEC = OLD_SPEC.replace("amount:", "amount_cents:")

# The rename is gone too: a property removal the rule cannot propose.
REMOVED_SPEC = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        currency:
          type: string
"""

# One non-breaking addition and one breaking rename.
MIXED_SPEC = """\
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

# The fixture's ``client.charges.create`` is the inferred POST /v1/charges call.
ENDPOINT_OLD = """\
openapi: 3.1.0
paths:
  /v1/charges:
    post:
      responses:
        '200':
          description: ok
"""

ENDPOINT_NEW = "openapi: 3.1.0\npaths: {}\n"


def a_copy(destination: Path) -> Path:
    shutil.copytree(
        PROOF_BASIC, destination, ignore=shutil.ignore_patterns("__pycache__")
    )
    return destination


def a_config(command: bool = True) -> str:
    """A valid ``tenon.toml``; the check just imports the fixture package."""
    text = '[locate]\nsdk_package = "acme.client"\n'
    if command:
        argv = [sys.executable, "-c", "import acme.billing"]
        text += "\n[tenon]\ncommand = " + json.dumps(argv) + "\n"
    return text


def a_write_specs(directory: Path, old: str, new: str) -> tuple[Path, Path]:
    old_path = directory / "old.yaml"
    new_path = directory / "new.yaml"
    old_path.write_text(old)
    new_path.write_text(new)
    return old_path, new_path


@pytest.fixture
def a_repo(tmp_path):
    repo = a_copy(tmp_path / "repo")
    (repo / "tenon.toml").write_text(a_config())
    return repo


@pytest.fixture
def a_repo_without_config(tmp_path):
    return a_copy(tmp_path / "repo")


@pytest.fixture
def a_clean_repo(tmp_path):
    repo = a_copy(tmp_path / "repo")
    (repo / "acme" / "billing.py").write_text(
        "from acme.client import StripeClient\n\nclient = StripeClient()\n"
    )
    (repo / "tenon.toml").write_text(a_config())
    return repo


@pytest.fixture
def a_repo_without_sdk(tmp_path):
    repo = a_copy(tmp_path / "repo")
    (repo / "acme" / "billing.py").write_text(
        "def create_charge(amount):\n    return amount\n"
    )
    (repo / "tenon.toml").write_text(a_config())
    return repo


@pytest.fixture
def a_specs(tmp_path):
    return a_write_specs(tmp_path, OLD_SPEC, NEW_SPEC)


@pytest.fixture
def a_mixed_specs(tmp_path):
    return a_write_specs(tmp_path, OLD_SPEC, MIXED_SPEC)


@pytest.fixture
def a_endpoint_specs(tmp_path):
    return a_write_specs(tmp_path, ENDPOINT_OLD, ENDPOINT_NEW)


@pytest.fixture
def a_removed_specs(tmp_path):
    return a_write_specs(tmp_path, OLD_SPEC, REMOVED_SPEC)


@pytest.fixture
def a_same_specs(tmp_path):
    return a_write_specs(tmp_path, OLD_SPEC, OLD_SPEC)


@pytest.fixture
def a_no_command_config(tmp_path):
    path = tmp_path / "no-command.toml"
    path.write_text(a_config(command=False))
    return path


@pytest.fixture
def a_breaking_config(tmp_path):
    path = tmp_path / "breaking.toml"
    path.write_text(
        a_config().replace("[tenon]", "[tenon]\nbreaking_only = true")
    )
    return path


@pytest.fixture
def a_snapshot():
    def snapshot(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(Path(root).rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }

    return snapshot
