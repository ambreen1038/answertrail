"""The ingestion pipeline: file bytes -> text -> chunks -> embeddings -> database."""
from pathlib import PurePath

from . import store
from .chunking import Chunk, chunk_markdown, chunk_pages, chunk_plain
from .config import settings
from .extract import ExtractionError, extract, slugify
from .gemini import embed_texts

CONTENT_TYPES = {"pdf": "application/pdf", "markdown": "text/markdown", "text": "text/plain"}


def ingest_file(filename: str, data: bytes, title: str | None = None) -> store.DocRecord:
    """Ingest one file. Raises ExtractionError for anything we can't turn into searchable text.

    Embedding happens BEFORE anything is written, and the write is a single transaction, so a
    failed upload (bad file, Gemini outage) never leaves a half-ingested document behind.
    """
    filename = PurePath(filename).name  # never trust a client-supplied path
    extracted = extract(filename, data)
    slug = slugify(filename)
    doc_title = (title or "").strip() or extracted.title

    chunks: list[Chunk]
    if extracted.kind == "pdf":
        chunks = chunk_pages(slug, doc_title, extracted.pages)
    elif extracted.kind == "markdown":
        chunks = chunk_markdown(slug, extracted.pages[0], title=doc_title)
    else:
        chunks = chunk_plain(slug, extracted.pages[0], title=doc_title)

    if not chunks:
        raise ExtractionError("No searchable text was found in the file.")
    if len(chunks) > settings.max_chunks_per_document:
        raise ExtractionError(
            f"The document is too large ({len(chunks)} chunks; the limit is "
            f"{settings.max_chunks_per_document})."
        )

    embeddings = embed_texts([c.embed_text for c in chunks], "RETRIEVAL_DOCUMENT")
    return store.add_document(slug, doc_title, filename, CONTENT_TYPES[extracted.kind], chunks, embeddings)
