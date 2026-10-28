from pathlib import Path

import ast

from tenon.locate.scan import (
    Dynamic,
    DynamicKind,
    _aliases,
    _bindings,
    _modules,
    _Source,
    scan,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"


def parse(text):
    return ast.parse(text)


def source(text, path="m.py"):
    return _Source(path, tuple(text.split("\n")))


def rooted(text):
    tree = parse(text)
    roots, classes, class_paths = _bindings(tree, "stripe")
    return _aliases(tree, roots, class_paths, source(text), "stripe")


# Phase 1: walk, reachability, skipping.
def test_scan_walks_modules_that_reach_the_sdk():
    result = scan(SDK_BASIC, "stripe")

    assert result.modules == ("acme/billing.py", "acme/reporting.py")
    assert result.hits == ()
    assert result.dynamics == ()


def test_modules_skips_ignored_directories(tmp_path):
    for ignored in (".venv", "node_modules", "build", "dist", "__pycache__", ".git"):
        (tmp_path / ignored).mkdir()
        (tmp_path / ignored / "bad.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "good.py").write_text("x = 1\n", encoding="utf-8")

    found = [path.relative_to(tmp_path).as_posix() for path in _modules(tmp_path)]

    assert found == ["pkg/good.py"]


def test_syntax_errors_skip_the_file_and_keep_the_scan():
    result = scan(SDK_BASIC, "stripe")

    assert "acme/broken.py" not in result.modules
    assert "acme/billing.py" in result.modules
    assert "acme/reporting.py" in result.modules


def test_scan_result_is_deterministic():
    assert scan(SDK_BASIC, "stripe") == scan(SDK_BASIC, "stripe")


def test_scan_never_modifies_the_scanned_tree():
    def snapshot():
        return {
            path.relative_to(SDK_BASIC).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in SDK_BASIC.rglob("*")
            if path.is_file()
        }

    before = snapshot()

    scan(SDK_BASIC, "stripe")

    assert snapshot() == before


# Phase 2: import bindings and one-hop aliases.
def test_import_binds_the_sdk_package_name():
    roots, classes, class_paths = _bindings(parse("import stripe\n"), "stripe")

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()
    assert class_paths == set()


def test_import_as_binds_the_alias():
    roots, _, _ = _bindings(parse("import stripe as st\n"), "stripe")

    assert roots == {"st": ("stripe",)}


def test_from_import_binds_the_imported_name_as_a_class():
    roots, classes, class_paths = _bindings(
        parse("from stripe import Stripe\n"), "stripe"
    )

    assert roots == {"Stripe": ("stripe", "Stripe")}
    assert classes == {"Stripe"}
    assert class_paths == {("stripe", "Stripe")}


def test_from_submodule_import_keeps_the_dotted_chain():
    roots, _, _ = _bindings(parse("from stripe.charges import create\n"), "stripe")

    assert roots == {"create": ("stripe", "charges", "create")}


def test_unrelated_package_yields_no_rooted_names():
    roots, classes, class_paths = _bindings(
        parse("import requests\nfrom requests import get\n"), "stripe"
    )

    assert roots == {}
    assert classes == set()
    assert class_paths == set()


def test_importing_a_local_module_yields_no_rooted_names():
    roots, _, _ = _bindings(parse("from acme.billing import client\n"), "stripe")

    assert roots == {}


def test_alias_from_a_class_call_is_rooted():
    aliases, class_aliases, dynamics = rooted(
        "from stripe import Stripe\nclient = Stripe()\n"
    )

    assert aliases == {"client": ("stripe",)}
    assert class_aliases == {"client"}
    assert dynamics == []


def test_alias_from_an_sdk_attribute_call_is_rooted():
    aliases, class_aliases, dynamics = rooted("import stripe\nc = stripe.Stripe()\n")

    assert aliases == {"c": ("stripe",)}
    assert class_aliases == set()
    assert dynamics == []


def test_alias_of_a_rooted_import_is_rooted():
    aliases, _, _ = rooted("from stripe import charges\nc = charges\n")

    assert aliases == {"c": ("stripe", "charges")}


def test_alias_of_a_rooted_attribute_is_rooted():
    aliases, _, _ = rooted("import stripe\nc = stripe.charges\n")

    assert aliases == {"c": ("stripe", "charges")}


def test_alias_inside_a_function_is_rooted():
    aliases, _, _ = rooted(
        "from stripe import Stripe\n\ndef build():\n    c = Stripe()\n    return c\n"
    )

    assert aliases == {"c": ("stripe",)}


def test_alias_of_an_alias_is_a_dynamic():
    aliases, _, dynamics = rooted(
        "from stripe import Stripe\nclient = Stripe()\nd = client\n"
    )

    assert "d" not in aliases
    assert dynamics == [
        Dynamic("m.py", 3, 1, DynamicKind.ALIAS_CHAIN, symbol="d")
    ]


def test_unrooted_call_is_not_an_alias():
    aliases, class_aliases, dynamics = rooted("x = other()\n")

    assert aliases == {}
    assert class_aliases == set()
    assert dynamics == []
