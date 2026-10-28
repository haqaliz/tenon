from pathlib import Path

from tenon.locate.scan import _modules, scan

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"


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
