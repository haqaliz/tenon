"""The tree-sitter TS/JS scanner over committed fixture repositories."""

from pathlib import Path

from tenon.locate import SiteShape
from tenon.locate.scan import Dynamic, DynamicKind, Hit
from tenon.locate.ts_scan import (
    _bindings,
    _grammar,
    _parser,
    _resolve_relative,
    scan_ts,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "ts-sdk-basic"
SDK_CJS = FIXTURES / "ts-cjs"
SDK_JS = FIXTURES / "ts-js"
SDK_TSX = FIXTURES / "ts-tsx"
SDK_DECOY = FIXTURES / "ts-decoy"
SDK_NO_SDK = FIXTURES / "ts-no-sdk"

IGNORED_DIRECTORIES = (
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "out",
    "coverage",
    ".turbo",
    "__pycache__",
)
EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


def parse_ts(text, suffix=".ts"):
    return _parser(_grammar(suffix)).parse(text.encode("utf-8"))


def bindings(text, sdk_package="stripe"):
    return _bindings(parse_ts(text), sdk_package)


# Phase 1: discovery, grammar selection and skipped files.
def test_scan_ts_discovers_modules_that_import_the_sdk():
    result = scan_ts(SDK_BASIC, "stripe")

    assert "src/billing.ts" in result.modules
    assert "src/unrelated.ts" not in result.modules


def test_scan_ts_parses_every_extension(tmp_path):
    for extension in EXTENSIONS:
        (tmp_path / f"file{extension}").write_text(
            'import Stripe from "stripe";\nconst client = new Stripe();\n',
            encoding="utf-8",
        )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == tuple(sorted(f"file{extension}" for extension in EXTENSIONS))


def test_scan_ts_skips_ignored_directories(tmp_path):
    for ignored in IGNORED_DIRECTORIES + (".hidden",):
        (tmp_path / ignored).mkdir()
        (tmp_path / ignored / "bad.ts").write_text(
            'import Stripe from "stripe";\n', encoding="utf-8"
        )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "good.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("pkg/good.ts",)


def test_scan_ts_skips_a_parse_error_file():
    result = scan_ts(SDK_BASIC, "stripe")

    assert "src/broken.ts" not in result.modules
    assert "src/billing.ts" in result.modules


def test_scan_ts_skips_an_undecodable_file(tmp_path):
    (tmp_path / "bad.ts").write_bytes(b'\xff\xfeimport Stripe from "stripe";\n')
    (tmp_path / "good.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("good.ts",)


# Phase 2: import bindings and reachability.
def test_default_import_binds_the_constructor():
    roots, classes = bindings('import Stripe from "stripe";\n')

    assert roots == {"Stripe": ("stripe", "Stripe")}
    assert classes == {"Stripe"}


def test_named_imports_bind_their_names_and_aliases():
    roots, classes = bindings('import { Stripe, charges as api } from "stripe";\n')

    assert roots == {"Stripe": ("stripe", "Stripe"), "api": ("stripe", "charges")}
    assert classes == {"Stripe", "api"}


def test_namespace_import_binds_the_module():
    roots, classes = bindings('import * as stripe from "stripe";\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_import_equals_binds_the_module():
    roots, classes = bindings('import stripe = require("stripe");\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_required_module_binds_the_module():
    roots, classes = bindings('const stripe = require("stripe");\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_required_object_destructuring_binds_its_members():
    roots, classes = bindings(
        'const { Stripe, charges: c } = require("stripe");\n'
    )

    assert roots == {"Stripe": ("stripe", "Stripe"), "c": ("stripe", "charges")}
    assert classes == {"Stripe", "c"}


def test_subpath_import_keeps_the_relative_chain():
    roots, classes = bindings('import { create } from "stripe/charges";\n')

    assert roots == {"create": ("stripe", "charges", "create")}
    assert classes == {"create"}


def test_scoped_package_and_its_subpath_match():
    roots, _ = bindings(
        'import { X } from "@acme/sdk/sub";\n', sdk_package="@acme/sdk"
    )

    assert roots == {"X": ("@acme", "sdk", "sub", "X")}


def test_type_only_imports_bind_nothing():
    roots, _ = bindings(
        'import type { Stripe } from "stripe";\n'
        'import type Stripe from "stripe";\n'
        'import { type Charge, Session } from "stripe";\n'
    )

    assert roots == {"Session": ("stripe", "Session")}


def test_bare_import_binds_nothing():
    assert bindings('import "stripe";\n') == ({}, set())


def test_bare_require_call_binds_nothing():
    assert bindings('require("stripe");\n') == ({}, set())


def test_non_sdk_and_relative_imports_bind_nothing():
    assert bindings(
        'import x from "other";\nimport y from "./local";\n'
        'const z = require(name);\n'
    ) == ({}, set())


def test_scan_ts_reaches_transitive_importers():
    result = scan_ts(SDK_BASIC, "stripe")

    assert result.modules == ("src/billing.ts", "src/reporting.ts")


def test_resolve_relative_prefers_exact_then_extension_then_index():
    files = {"src/exact.ts", "src/a.ts", "src/b.tsx", "src/dir/index.js"}

    assert _resolve_relative("src/app.ts", "./exact.ts", files) == "src/exact.ts"
    assert _resolve_relative("src/app.ts", "./a", files) == "src/a.ts"
    assert _resolve_relative("src/app.ts", "./b", files) == "src/b.tsx"
    assert _resolve_relative("src/app.ts", "./dir", files) == "src/dir/index.js"
    assert _resolve_relative("src/app.ts", "./missing", files) is None


def test_scan_ts_reaches_a_module_that_imports_the_sdk_importer(tmp_path):
    (tmp_path / "hub.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )
    (tmp_path / "app.ts").write_text('import { x } from "./hub";\n', encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "report.mts").write_text(
        'import { x } from "../hub";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("app.ts", "hub.ts", "lib/report.mts")


def test_scan_ts_ignores_an_unresolvable_relative_import(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\nimport "./missing";\n', encoding="utf-8"
    )

    assert scan_ts(tmp_path, "stripe").modules == ("app.ts",)


def test_scan_ts_has_no_modules_without_an_sdk_import():
    assert scan_ts(SDK_NO_SDK, "stripe").modules == ()


def test_scan_ts_ignores_type_only_imports_for_reachability(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import type { Stripe } from "stripe";\ntype Client = Stripe;\n',
        encoding="utf-8",
    )

    assert scan_ts(tmp_path, "stripe").modules == ()


def test_scan_ts_reaches_modules_imported_by_require():
    result = scan_ts(SDK_CJS, "stripe")

    assert result.modules == (
        "app.cjs",
        "lib/client.cjs",
        "lib/import-equals.cts",
        "lib/named.cjs",
    )


def test_scan_ts_finds_js_and_tsx_modules():
    assert scan_ts(SDK_JS, "stripe").modules == (
        "app.mjs",
        "component.jsx",
        "lib/util.js",
    )
    assert scan_ts(SDK_TSX, "stripe").modules == ("src/app.tsx",)


def test_scan_ts_reaches_the_sdk_importer_but_not_an_unrelated_module():
    result = scan_ts(SDK_DECOY, "stripe")

    assert result.modules == ("src/sdk.ts",)
    assert "src/unrelated.ts" not in result.modules
    assert "src/format.ts" not in result.modules
