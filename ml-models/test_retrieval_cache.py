"""Guard the retrieval cache key against serving answers that predate an upload."""

from __future__ import annotations

from pipeline import _documents_fingerprint, _with_document_evidence


def _doc(reference: str, text: str) -> dict[str, str]:
    return {"source_reference": reference, "text": text, "source_type": "user_upload"}


def test_new_upload_changes_the_fingerprint() -> None:
    """Uploading after an evaluation must not reuse the earlier cached answer."""
    first = [_doc("title.txt", "clear title deed")]
    assert _documents_fingerprint(first) == _documents_fingerprint(list(first))
    assert _documents_fingerprint(first) != _documents_fingerprint(first + [_doc("ec.pdf", "no encumbrance")])


def test_edited_document_changes_the_fingerprint() -> None:
    assert _documents_fingerprint([_doc("title.txt", "before")]) != _documents_fingerprint([_doc("title.txt", "after")])


def test_fingerprint_is_order_independent() -> None:
    a, b = _doc("a.txt", "one"), _doc("b.txt", "two")
    assert _documents_fingerprint([a, b]) == _documents_fingerprint([b, a])


def test_reference_and_text_boundaries_do_not_collide() -> None:
    """Concatenation must not let two different corpora hash the same."""
    assert _documents_fingerprint([_doc("ab", "c")]) != _documents_fingerprint([_doc("a", "bc")])


def test_stale_upload_rows_are_dropped_when_nothing_is_attached() -> None:
    existing = [{"source_type": "satellite"}, {"source_type": "user_upload", "source_reference": "gone.txt"}]
    assert _with_document_evidence(existing, None) == [{"source_type": "satellite"}]


def test_each_attached_document_gets_one_row() -> None:
    rows = _with_document_evidence([], [_doc("title.txt", "a b c"), _doc("title.txt", "duplicate")])
    assert [row["source_reference"] for row in rows] == ["title.txt"]
    assert rows[0]["freshness"] == "user_upload"
    assert "3 words" in rows[0]["summary"]


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_"):
            function()
    print("retrieval cache checks passed")
