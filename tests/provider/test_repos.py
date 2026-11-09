import pytest

from tenon.provider.repos import load_repos


def a_repos(tmp_path, text):
    path = tmp_path / "repos.txt"
    path.write_text(text)
    return path


# Spec AC1: comments, blanks and surrounding whitespace are ignored.
def test_parse_ignores_comments_blanks_and_whitespace(tmp_path):
    path = a_repos(
        tmp_path,
        "# a customer\n"
        "\n"
        "  checkout-a  \n"
        "   # another customer\n"
        "\tcheckout-b\t\n"
        "\n",
    )

    assert load_repos(path) == (
        (tmp_path / "checkout-a").resolve(),
        (tmp_path / "checkout-b").resolve(),
    )


# Spec AC1: file order and duplicates are preserved.
def test_parse_preserves_order_and_duplicates(tmp_path):
    path = a_repos(tmp_path, "b\na\nb\n")

    assert load_repos(path) == (
        (tmp_path / "b").resolve(),
        (tmp_path / "a").resolve(),
        (tmp_path / "b").resolve(),
    )


# Spec AC1: only whole-line comments are stripped; an inline # is a path.
def test_parse_keeps_inline_hash_in_the_path(tmp_path):
    path = a_repos(tmp_path, "checkout#1\n")

    assert load_repos(path) == ((tmp_path / "checkout#1").resolve(),)


# Spec AC2: relative paths resolve against the repos file's parent.
def test_resolve_relative_against_the_file_parent(tmp_path):
    lists = tmp_path / "lists"
    lists.mkdir()
    path = a_repos(lists, "checkout\n")

    assert load_repos(path) == ((lists / "checkout").resolve(),)


# Spec AC2: absolute paths stay absolute.
def test_resolve_absolute_paths_stay(tmp_path):
    checkout = (tmp_path / "checkout").resolve()
    path = a_repos(tmp_path, f"{checkout}\n")

    assert load_repos(path) == (checkout,)


# Spec AC2: ~ expands from the user's home.
def test_resolve_expands_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    path = a_repos(tmp_path, "~/checkout\n")

    assert load_repos(path) == ((home / "checkout").resolve(),)


# Spec AC2: a nested relative path keeps its parts.
def test_resolve_nested_relative_path(tmp_path):
    path = a_repos(tmp_path, "customers/acme/checkout\n")

    assert load_repos(path) == ((tmp_path / "customers/acme/checkout").resolve(),)
