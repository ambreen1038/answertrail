"""Build the vector index from kb/*.md.  Run:  python -m app.ingest"""
from . import store
from .chunking import load_kb
from .config import settings
from .gemini import embed_texts


def main() -> None:
    chunks = load_kb(settings.kb_dir)
    if not chunks:
        raise SystemExit(f"No markdown files found in {settings.kb_dir}")
    print(f"Chunked {len(set(c.doc_slug for c in chunks))} articles into {len(chunks)} chunks")
    embeddings = embed_texts([c.embed_text for c in chunks], "RETRIEVAL_DOCUMENT")
    store.init_schema()
    store.replace_all(chunks, embeddings)
    print(f"Stored {store.count_chunks()} chunks ({settings.embed_dim}-dim, model {settings.embed_model})")


if __name__ == "__main__":
    main()
