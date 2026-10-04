"""Offline tests for chunking strategies, text extraction and the admin upload API.

No network, database or API key: Gemini and the store are replaced with in-memory fakes.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, documents, main, store  # noqa: E402
from app.chunking import chunk_markdown, chunk_pages, chunk_plain, load_kb, pack  # noqa: E402
from app.config import settings  # noqa: E402
from app.extract import ExtractionError, extract, slugify  # noqa: E402
from app.gemini import GeminiError  # noqa: E402
from pdf_util import make_pdf  # noqa: E402

LONG_TEXT = " ".join(f"Sentence number {i} says something useful about uploads." for i in range(120))


# ---------------------------------------------------------------- chunking


def test_pack_respects_size_and_overlaps_neighbours():
    sentences = [f"This is sentence {i}." for i in range(40)]
    chunks = pack(sentences, max_chars=200, overlap=45)
    assert len(chunks) > 1
    assert all(len(c) <= 200 + 45 for c in chunks)  # soft cap: overlap may add a little
    # the last sentence of one chunk is repeated in the next, so a boundary can't cut a fact in half
    last_sentence = re.findall(r"This is sentence \d+\.", chunks[0])[-1]
    assert last_sentence in chunks[1]


def test_pack_hard_splits_a_unit_with_no_punctuation():
    chunks = pack(["word " * 500], max_chars=100, overlap=0)
    assert len(chunks) > 5 and all(len(c) <= 100 for c in chunks)


def test_pdf_pages_become_page_headed_chunks():
    chunks = chunk_pages("manual", "Manual", ["Short page one.", "", "Short page three."])
    assert [c.heading for c in chunks] == ["Page 1", "Page 3"]  # the blank page is skipped
    assert [c.id for c in chunks] == ["manual#0", "manual#1"]


def test_a_long_pdf_page_is_split_into_parts():
    chunks = chunk_pages("manual", "Manual", [LONG_TEXT])
    assert len(chunks) > 3
    assert chunks[0].heading == "Page 1 (part 1)"


def test_markdown_without_headings_falls_back_to_plain_packing():
    chunks = chunk_markdown("notes", "# Notes\n\n" + LONG_TEXT)
    assert len(chunks) > 3 and chunks[0].heading == "Part 1"
    assert chunks[0].doc_title == "Notes"


def test_oversized_markdown_section_is_split_but_short_ones_are_not():
    body = "# Guide\n\n## Short\n\nTiny.\n\n## Huge\n\n" + LONG_TEXT
    headings = [c.heading for c in chunk_markdown("guide", body)]
    assert headings[0] == "Short"
    assert headings[1].startswith("Huge (part ")


def test_plain_text_chunks_get_part_headings():
    assert chunk_plain("t", LONG_TEXT)[0].heading == "Part 1"


def test_existing_knowledge_base_chunking_is_unchanged():
    # The evaluation numbers are only valid if kb/ is chunked exactly as it was when measured.
    chunks = load_kb(settings.kb_dir)
    assert len(chunks) == 58
    assert max(len(c.content) for c in chunks) <= settings.section_max_chars


# ---------------------------------------------------------------- extraction


def test_extracts_text_per_page_from_a_real_pdf():
    ex = extract("Refund Policy.pdf", make_pdf(["Refunds are allowed within 30 days of purchase.", "Shipping takes 3 to 5 business days."]))
    assert ex.kind == "pdf" and len(ex.pages) == 2
    assert "30 days" in ex.pages[0] and "business days" in ex.pages[1]
    assert ex.title == "Refund Policy"


def test_scanned_pdf_with_no_text_gets_a_clear_error():
    with pytest.raises(ExtractionError, match="scanned"):
        extract("scan.pdf", make_pdf(["", ""]))


def test_file_named_pdf_that_is_not_a_pdf_is_rejected():
    with pytest.raises(ExtractionError, match="isn't a PDF"):
        extract("fake.pdf", b"just some text pretending to be a pdf")


def test_damaged_pdf_is_rejected_cleanly():
    with pytest.raises(ExtractionError, match="couldn't be read"):
        extract("broken.pdf", b"%PDF-1.4\nthis is not a real pdf body at all")


def test_pdf_page_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_pages", 2)
    with pytest.raises(ExtractionError, match="limit is 2"):
        extract("big.pdf", make_pdf(["Some real text on this page here."] * 3))


def test_unsupported_extension_empty_file_and_bad_encoding():
    with pytest.raises(ExtractionError, match="Only PDF"):
        extract("sheet.xlsx", b"x" * 100)
    with pytest.raises(ExtractionError, match="empty"):
        extract("a.txt", b"")
    with pytest.raises(ExtractionError, match="UTF-8"):
        extract("a.txt", b"\xff\xfe\x00bad" * 40)


def test_markdown_title_comes_from_the_heading_else_the_filename():
    assert extract("x.md", ("# Real Title\n\n" + LONG_TEXT).encode()).title == "Real Title"
    assert extract("my-help_guide.txt", LONG_TEXT.encode()).title == "My Help Guide"


def test_slugify():
    assert slugify("Refund Policy (v2).PDF") == "refund-policy-v2"
    assert slugify("!!!.pdf") == "document"


# ---------------------------------------------------------------- admin API


class FakeStore:
    """In-memory stand-in for the database, recording what the API asked it to do."""

    def __init__(self):
        self.docs: dict[int, store.DocRecord] = {}
        self.calls = 0

    def add_document(self, slug, title, filename, content_type, chunks, embeddings):
        self.calls += 1
        replaced = any(d.slug == slug for d in self.docs.values())
        self.docs = {i: d for i, d in self.docs.items() if d.slug != slug}
        doc = store.DocRecord(self.calls, slug, title, filename, content_type, len(chunks),
                              __import__("datetime").datetime(2026, 10, 4), replaced)
        self.docs[doc.id] = doc
        return doc

    def list_documents(self):
        return list(self.docs.values())

    def delete_document(self, doc_id):
        return self.docs.pop(doc_id, None) is not None


@pytest.fixture
def api(monkeypatch):
    fake = FakeStore()
    for name in ("add_document", "list_documents", "delete_document"):
        monkeypatch.setattr(store, name, getattr(fake, name))
    monkeypatch.setattr(documents, "embed_texts", lambda texts, task: np.ones((len(texts), settings.embed_dim), dtype=np.float32))
    # Login is covered in test_auth.py; here we only test what an authenticated admin can do.
    main.app.dependency_overrides[auth.require_admin] = lambda: auth.AdminUser(id="u1", email="admin@example.com")
    client = TestClient(main.app)  # no `with`, so the start-up hook (real DB) does not run
    client.fake = fake
    yield client
    main.app.dependency_overrides.clear()


def _pdf_upload(name="policy.pdf", pages=("Customers may request a refund within 30 days of the purchase date.",)):
    return {"file": (name, make_pdf(list(pages)), "application/pdf")}


def test_upload_list_replace_and_delete_round_trip(api):
    r = api.post("/api/admin/documents", files=_pdf_upload())
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "policy" and body["n_chunks"] == 1 and body["replaced"] is False

    # same filename again replaces the document instead of duplicating it
    again = api.post("/api/admin/documents", files=_pdf_upload()).json()
    assert again["replaced"] is True
    assert len(api.get("/api/admin/documents").json()) == 1

    assert api.delete(f"/api/admin/documents/{again['id']}").status_code == 204
    assert api.delete(f"/api/admin/documents/{again['id']}").status_code == 404
    assert api.get("/api/admin/documents").json() == []


def test_upload_rejects_bad_files_with_a_useful_message_and_stores_nothing(api):
    scanned = api.post("/api/admin/documents", files=_pdf_upload(pages=("", "")))
    assert scanned.status_code == 422 and "scanned" in scanned.json()["detail"]
    wrong_type = api.post("/api/admin/documents", files={"file": ("a.docx", b"x" * 100, "application/octet-stream")})
    assert wrong_type.status_code == 422
    assert api.fake.calls == 0


def test_upload_too_large(api, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    r = api.post("/api/admin/documents", files=_pdf_upload())
    assert r.status_code == 413


def test_embedding_outage_returns_502_and_saves_nothing(api, monkeypatch):
    def boom(texts, task):
        raise GeminiError("quota")

    monkeypatch.setattr(documents, "embed_texts", boom)
    r = api.post("/api/admin/documents", files=_pdf_upload())
    assert r.status_code == 502 and "Nothing was saved" in r.json()["detail"]
    assert api.fake.calls == 0


def test_a_too_big_document_is_rejected_before_any_embedding_cost(api, monkeypatch):
    monkeypatch.setattr(settings, "max_chunks_per_document", 1)
    called = []
    monkeypatch.setattr(documents, "embed_texts", lambda t, k: called.append(1))
    r = api.post("/api/admin/documents", files=_pdf_upload(pages=(LONG_TEXT,)))
    assert r.status_code == 422 and "too large" in r.json()["detail"]
    assert not called  # we never paid for embeddings we were going to throw away
