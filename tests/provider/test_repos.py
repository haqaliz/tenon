import pytest

from tenon.provider.repos import load_repos


def a_repos(tmp_path, text):
    path = tmp_path / "repos.txt"
    path.write_text(text)
    return path


def a_named_error(path):
    with pytest.raises(ValueError) as error:
        load_repos(path)
    assert str(path) in str(error.value)


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


# Spec AC3: an empty list is a named error.
def test_empty_file_is_a_named_error(tmp_path):
    a_named_error(a_repos(tmp_path, ""))


# Spec AC3: a comment-only list is a named error.
def test_comment_only_file_is_a_named_error(tmp_path):
    a_named_error(a_repos(tmp_path, "# nothing\n\n   # still nothing\n"))


# Spec AC4: a missing file is a named error.
def test_missing_file_is_a_named_error(tmp_path):
    a_named_error(tmp_path / "missing.txt")


# Spec AC4: a directory is not a repos file.
def test_directory_is_a_named_error(tmp_path):
    path = tmp_path / "repos"
    path.mkdir()

    a_named_error(path)


# Spec AC4: non-UTF-8 bytes are a named error.
def test_non_utf8_file_is_a_named_error(tmp_path):
    path = tmp_path / "repos.txt"
    path.write_bytes(b"\xff\xfecheckout\n")

    a_named_error(path)


# Spec AC5: listed paths are not checked for existence or directory-ness.
def test_nonexistent_listed_path_is_returned(tmp_path):
    path = a_repos(tmp_path, "missing-checkout\n")

    assert load_repos(path) == ((tmp_path / "missing-checkout").resolve(),)


# Spec: the package surface exports the repos loader.
def test_package_exports_the_repos_loader(tmp_path):
    from tenon.provider import load_repos as exported

    path = a_repos(tmp_path, "checkout\n")

    assert exported(path) == ((tmp_path / "checkout").resolve(),)
