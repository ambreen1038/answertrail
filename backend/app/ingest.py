"""Load the demo knowledge base from kb/*.md.

    python -m app.ingest            add or update every article in kb/ (other documents untouched)
    python -m app.ingest --reset    delete ALL documents first, then load kb/ (a clean, known state;
                                    use this before running the evaluation)
"""
import sys

from . import store
from .config import settings
from .documents import ingest_file


def main() -> None:
    reset = "--reset" in sys.argv[1:]
    files = sorted(settings.kb_dir.glob("*.md"))
    if not files:
        raise SystemExit(f"No markdown files found in {settings.kb_dir}")

    store.init_schema()
    if reset:
        print(f"--reset: removed {store.delete_all_documents()} existing document(s)")

    for path in files:
        doc = ingest_file(path.name, path.read_bytes())
        print(f"  {doc.filename}: {doc.n_chunks} chunks" + (" (updated)" if doc.replaced else ""))
    print(f"Done: {len(store.list_documents())} documents, {store.count_chunks()} chunks "
          f"({settings.embed_dim}-dim, model {settings.embed_model})")


if __name__ == "__main__":
    main()
