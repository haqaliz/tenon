import pytest

from tenon.corpus.record import CorpusRecord, Outcome, record_id
from tenon.corpus.store import CorpusError, append_records, load_corpus

REPO = "https://github.com/o/r"
CHANGE = {"kind": "signature", "path": "app.py", "symbol": "handler"}
PROPOSAL = {"diff": "--- a/app.py\n+++ b/app.py\n", "summary": "one edit"}
PROOF = {"level": "TESTS_PASSED", "cause": None}


def a_record(commit="commit-one", **overrides):
    values = {
        "repo": REPO,
        "commit": commit,
        "change": CHANGE,
        "proposal": PROPOSAL,
        "proof": PROOF,
        "pr": None,
        "outcome": Outcome.PENDING,
        "recorded": "2026-11-07",
    }
    values.update(overrides)
    if "id" not in values:
        values["id"] = record_id(
            values["repo"], values["commit"], values["change"], values["proposal"]
        )
    return CorpusRecord(**values)


def write_lines(path, *lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Spec AC4: a two-line file loads two records in file order.
def test_load_returns_the_records_in_file_order(tmp_path):
    first = a_record(commit="commit-one")
    second = a_record(commit="commit-two")
    path = tmp_path / "corpus.jsonl"
    write_lines(path, first.to_json(), second.to_json())

    records = load_corpus(path)

    assert records == (first, second)


# Spec AC4: the load result is an immutable tuple.
def test_load_returns_a_tuple(tmp_path):
    path = tmp_path / "corpus.jsonl"
    write_lines(path, a_record().to_json())

    assert isinstance(load_corpus(path), tuple)


# Spec AC4: blank lines are not records.
def test_load_ignores_blank_lines(tmp_path):
    first = a_record(commit="commit-one")
    second = a_record(commit="commit-two")
    path = tmp_path / "corpus.jsonl"
    write_lines(path, "", first.to_json(), "", "   ", second.to_json(), "")

    assert load_corpus(path) == (first, second)


# Spec AC4: a missing file is an error on load; append is what creates it.
def test_load_missing_file_is_a_corpus_error(tmp_path):
    with pytest.raises(CorpusError, match="missing.jsonl"):
        load_corpus(tmp_path / "missing.jsonl")


# Spec AC4: a malformed line is a named error, not a skip.
def test_load_malformed_json_names_the_line(tmp_path):
    path = tmp_path / "corpus.jsonl"
    write_lines(path, a_record().to_json(), "{not json", a_record(commit="x").to_json())

    with pytest.raises(CorpusError, match=r"line 2"):
        load_corpus(path)


# Spec AC4: a valid JSON value that is not an object is still malformed.
def test_load_a_non_object_line_names_the_line(tmp_path):
    path = tmp_path / "corpus.jsonl"
    write_lines(path, "[]")

    with pytest.raises(CorpusError) as caught:
        load_corpus(path)
    assert "line 1" in str(caught.value)
    assert "corpus.jsonl" in str(caught.value)


# Spec AC5: a new file gets one canonical line per record.
def test_append_creates_the_file_with_canonical_lines(tmp_path):
    first = a_record(commit="commit-one")
    second = a_record(commit="commit-two")
    path = tmp_path / "corpus.jsonl"

    append_records(path, [first, second])

    assert path.read_text(encoding="utf-8") == (
        first.to_json() + "\n" + second.to_json() + "\n"
    )
    assert load_corpus(path) == (first, second)


# Spec AC5: appending keeps the records already in the file.
def test_append_keeps_existing_records(tmp_path):
    first = a_record(commit="commit-one")
    second = a_record(commit="commit-two")
    path = tmp_path / "corpus.jsonl"

    append_records(path, [first])
    append_records(path, [second])

    assert load_corpus(path) == (first, second)
    assert path.read_text(encoding="utf-8").startswith(first.to_json() + "\n")


# Spec AC5: a missing parent directory is created, not an error.
def test_append_creates_a_missing_parent_directory(tmp_path):
    path = tmp_path / "nested" / "deeper" / "corpus.jsonl"
    record = a_record()

    append_records(path, [record])

    assert load_corpus(path) == (record,)
