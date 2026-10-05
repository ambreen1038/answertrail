"""keyword_words prepares the words for hybrid search's keyword ranking. Offline: no database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.store import keyword_words  # noqa: E402


def test_words_are_lowercased_and_deduplicated_in_order():
    assert keyword_words("How big can a file be? File size!") == ["how", "big", "can", "a", "file", "be", "size"]


def test_numbers_are_kept():
    assert keyword_words("Limit 10MB, WebP") == ["limit", "10mb", "webp"]


def test_query_syntax_typed_by_the_visitor_cannot_get_through():
    words = keyword_words("'; DROP TABLE chunks; -- & !(a) <-> b :* c")
    assert words == ["drop", "table", "chunks", "a", "b", "c"]
    assert all(w.isalnum() for w in words)


def test_nothing_usable_means_no_words():
    assert keyword_words("?!  --  ...") == []
    assert keyword_words("") == []
