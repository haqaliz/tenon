"""The tree-sitter TS/JS scanner over committed fixture repositories."""

from pathlib import Path

from tenon.locate import SiteShape
from tenon.locate.scan import Dynamic, DynamicKind, Hit
from tenon.locate.ts_scan import scan_ts

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "ts-sdk-basic"

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
