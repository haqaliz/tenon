"""The CLI entry point: parse, compose the stages, report and return a code."""

import subprocess
import sys

import pytest

from tenon.cli import main


# Spec AC1: help is a 0, and no SystemExit escapes main.
@pytest.mark.parametrize("argv", [["--help"], ["check", "--help"], ["fix", "--help"]])
def test_help_returns_zero(argv, capsys):
    assert main(argv) == 0
    assert "usage: tenon" in capsys.readouterr().out


# Spec AC1: --version prints the package version and returns 0.
def test_version_returns_zero(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("tenon ")
    assert out.strip().split(" ", 1)[1]


# Spec AC1: a missing or unknown subcommand is a usage error, not a traceback.
def test_no_subcommand_is_usage(capsys):
    assert main([]) == 2
    assert "usage: tenon" in capsys.readouterr().err


def test_unknown_subcommand_is_usage(capsys):
    assert main(["probe"]) == 2
    assert "usage: tenon" in capsys.readouterr().err


# Spec AC9: python -m tenon is a runnable module.
def test_module_help_subprocess():
    completed = subprocess.run(
        [sys.executable, "-m", "tenon", "--help"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "usage: tenon" in completed.stdout
