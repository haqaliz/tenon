"""End-to-end typed-helper receiver inference through tenon check."""

from tenon.cli import main

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


def a_helper_repo(tmp_path):
    """A repo whose client is built by a same-file, return-annotated helper."""
    repo = tmp_path / "repo"
    (repo / "acme").mkdir(parents=True)
    (repo / "acme" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "acme" / "client.py").write_text(
        "class _Charges:\n"
        "    def create(self, **kwargs):\n"
        "        return kwargs\n"
        "\n"
        "\n"
        "class StripeClient:\n"
        "    def __init__(self):\n"
        "        self.charges = _Charges()\n",
        encoding="utf-8",
    )
    (repo / "acme" / "billing.py").write_text(
        "from acme.client import StripeClient\n"
        "\n"
        "\n"
        "def make_client() -> StripeClient:\n"
        "    return StripeClient()\n"
        "\n"
        "\n"
        'client = make_client()\n'
        "\n"
        "\n"
        "def create_charge(amount):\n"
        '    return client.charges.create(amount=amount, currency="usd")\n',
        encoding="utf-8",
    )
    return repo


# Spec AC1: a same-file helper with an SDK return annotation roots the receiver.
def test_a_typed_helper_roots_the_receiver(tmp_path, capsys):
    repo = a_helper_repo(tmp_path)
    old = tmp_path / "old.yaml"
    new = tmp_path / "new.yaml"
    old.write_text(OLD_SPEC, encoding="utf-8")
    new.write_text(NEW_SPEC, encoding="utf-8")

    code = main(
        [
            "check",
            str(repo),
            "--old",
            str(old),
            "--new",
            str(new),
            "--language",
            "python",
            "--sdk-package",
            "acme.client",
        ]
    )

    assert code == 1
    out = capsys.readouterr().out
    assert "amount -> amount_cents" in out
    assert "1 certain site" in out
