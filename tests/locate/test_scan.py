from pathlib import Path

import ast

from tenon.locate import SiteShape
from tenon.locate.scan import (
    Dynamic,
    DynamicKind,
    Hit,
    _aliases,
    _bindings,
    _modules,
    _Source,
    _Visitor,
    scan,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
SDK_DECOY = FIXTURES / "sdk-decoy"
SDK_DYNAMIC = FIXTURES / "sdk-dynamic"
SDK_MULTIPLE = FIXTURES / "sdk-multiple"
SDK_SRC_LAYOUT = FIXTURES / "sdk-src-layout"
SDK_UNICODE = FIXTURES / "sdk-unicode"


def parse(text):
    return ast.parse(text)


def source(text, path="m.py"):
    return _Source(path, tuple(text.split("\n")))


def rooted(text):
    tree = parse(text)
    roots, classes, class_paths = _bindings(tree, "stripe")
    return _aliases(tree, roots, class_paths, source(text), "stripe")


def hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


# Phase 1: walk, reachability, skipping.
def test_scan_walks_modules_that_reach_the_sdk():
    result = scan(SDK_BASIC, "stripe")

    assert result.modules == ("acme/billing.py", "acme/reporting.py")


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


# Phase 3: the visitor.
def test_rooted_calls_and_keywords_are_reported():
    result = scan(SDK_BASIC, "stripe")

    assert result.hits == (
        hit(SDK_BASIC, "acme/billing.py", 3, 10, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_BASIC, "acme/billing.py", 5, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(SDK_BASIC, "acme/billing.py", 5, 23, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
        hit(SDK_BASIC, "acme/billing.py", 5, 38, SiteShape.KEYWORD, "currency", ("charges", "create"), True),
        hit(SDK_BASIC, "acme/billing.py", 6, 16, SiteShape.CALL, "delete", ("charges", "delete"), True),
        hit(SDK_BASIC, "acme/reporting.py", 3, 16, SiteShape.CALL, "list", ("charges", "list"), False),
        hit(SDK_BASIC, "acme/reporting.py", 3, 21, SiteShape.KEYWORD, "limit", (), False),
    )
    assert result.dynamics == ()


def test_decoy_keyword_is_unrooted_and_never_rooted():
    result = scan(SDK_DECOY, "stripe")

    assert result.hits == (
        hit(SDK_DECOY, "acme/mixed.py", 3, 10, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_DECOY, "acme/mixed.py", 10, 8, SiteShape.KEYWORD, "amount", (), False),
        hit(SDK_DECOY, "acme/mixed.py", 11, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(SDK_DECOY, "acme/mixed.py", 11, 23, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
    )
    assert [(h.line, h.rooted) for h in result.hits if h.symbol == "amount"] == [
        (10, False),
        (11, True),
    ]


def test_dict_keys_and_unrooted_attributes_are_reported():
    result = scan(SDK_DYNAMIC, "stripe")

    assert result.hits == (
        hit(SDK_DYNAMIC, "acme/flows.py", 3, 17, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_DYNAMIC, "acme/flows.py", 7, 27, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(SDK_DYNAMIC, "acme/flows.py", 15, 11, SiteShape.CALL, "delete", ("charges", "delete"), False),
        hit(SDK_DYNAMIC, "acme/flows.py", 17, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(SDK_DYNAMIC, "acme/flows.py", 17, 24, SiteShape.DICT_KEY, "amount", ("charges", "create"), True),
        hit(SDK_DYNAMIC, "acme/flows.py", 17, 37, SiteShape.DICT_KEY, "currency", ("charges", "create"), True),
        hit(SDK_DYNAMIC, "acme/flows.py", 19, 6, SiteShape.ATTRIBUTE, "amount", ("amount",), False),
    )


def test_star_arguments_getattr_and_alias_chains_are_dynamics():
    result = scan(SDK_DYNAMIC, "stripe")

    assert result.dynamics == (
        Dynamic("acme/flows.py", 7, 34, DynamicKind.STAR_KWARGS),
        Dynamic("acme/flows.py", 11, 12, DynamicKind.GETATTR, "delete"),
        Dynamic("acme/flows.py", 11, 46, DynamicKind.STAR_ARGS),
        Dynamic("acme/flows.py", 14, 1, DynamicKind.ALIAS_CHAIN, "c"),
    )
    assert [hit for hit in result.hits if hit.line == 15 and hit.symbol == "delete"] == [
        hit(SDK_DYNAMIC, "acme/flows.py", 15, 11, SiteShape.CALL, "delete", ("charges", "delete"), False)
    ]


def test_src_layout_is_scanned():
    result = scan(SDK_SRC_LAYOUT, "stripe")

    assert result.modules == ("src/acme/app.py",)
    assert result.hits == (
        hit(SDK_SRC_LAYOUT, "src/acme/app.py", 3, 5, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_SRC_LAYOUT, "src/acme/app.py", 4, 11, SiteShape.CALL, "delete", ("charges", "delete"), True),
    )


def test_multiple_sdk_methods_are_reported():
    result = scan(SDK_MULTIPLE, "stripe")

    assert result.hits == (
        hit(SDK_MULTIPLE, "acme/clients.py", 3, 10, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_MULTIPLE, "acme/clients.py", 5, 18, SiteShape.CALL, "get", ("customers", "get"), True),
        hit(SDK_MULTIPLE, "acme/clients.py", 6, 18, SiteShape.CALL, "retrieve", ("customers", "retrieve"), True),
    )


def test_attribute_on_an_sdk_class_and_its_instance_is_rooted():
    text = (
        "from stripe import Stripe\n"
        "client = Stripe()\n"
        "Stripe.amount\n"
        "client.amount\n"
    )
    tree = parse(text)
    roots, classes, class_paths = _bindings(tree, "stripe")
    alias_roots, class_aliases, _ = _aliases(
        tree, roots, class_paths, source(text), "stripe"
    )
    visitor = _Visitor(
        source(text), "stripe", {**roots, **alias_roots}, classes | class_aliases
    )

    visitor.visit(tree)

    assert visitor.hits == [
        Hit("m.py", 2, 10, SiteShape.CALL, "Stripe", ("Stripe",), True, "client = Stripe()"),
        Hit("m.py", 3, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True, "Stripe.amount"),
        Hit("m.py", 4, 8, SiteShape.ATTRIBUTE, "amount", ("amount",), True, "client.amount"),
    ]


def test_call_to_a_from_submodule_import_is_rooted():
    text = "from stripe.charges import create\ncreate(amount=1)\n"
    tree = parse(text)
    roots, classes, _ = _bindings(tree, "stripe")

    visitor = _Visitor(source(text), "stripe", roots, classes)
    visitor.visit(tree)

    assert visitor.hits == [
        Hit("m.py", 2, 1, SiteShape.CALL, "create", ("charges", "create"), True, "create(amount=1)"),
        Hit("m.py", 2, 8, SiteShape.KEYWORD, "amount", ("charges", "create"), True, "create(amount=1)"),
    ]


def test_getattr_with_a_non_literal_name_has_no_symbol():
    text = "import stripe\nclient = stripe.Client()\ngetattr(client, name)\n"
    tree = parse(text)
    roots, classes, class_paths = _bindings(tree, "stripe")
    alias_roots, class_aliases, _ = _aliases(
        tree, roots, class_paths, source(text), "stripe"
    )
    visitor = _Visitor(
        source(text), "stripe", {**roots, **alias_roots}, classes | class_aliases
    )

    visitor.visit(tree)

    assert visitor.dynamics == [Dynamic("m.py", 3, 1, DynamicKind.GETATTR, None)]


def test_star_arguments_in_an_unrooted_call_are_ignored():
    text = "other(*args, **row)\n"
    visitor = _Visitor(source(text), "stripe", {}, set())

    visitor.visit(parse(text))

    assert visitor.hits == []
    assert visitor.dynamics == []


def test_undecodable_module_is_skipped(tmp_path):
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "ok.py").write_text("import stripe\n", encoding="utf-8")

    result = scan(tmp_path, "stripe")

    assert result.modules == ("pkg/ok.py",)


# Phase 4: character columns.
def test_columns_are_characters_not_utf8_bytes():
    result = scan(SDK_UNICODE, "stripe")

    assert result.hits == (
        hit(SDK_UNICODE, "acme/unicode_demo.py", 3, 10, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_UNICODE, "acme/unicode_demo.py", 4, 31, SiteShape.CALL, "delete", ("charges", "delete"), True),
    )
    line = (SDK_UNICODE / "acme/unicode_demo.py").read_text(encoding="utf-8").split(
        "\n"
    )[3]
    delete = result.hits[1]
    character_column = line.index("delete") + 1
    byte_column = len(line[: line.index("delete")].encode("utf-8")) + 1
    assert delete.column == character_column
    assert delete.column != byte_column
    assert delete.line_text == line
