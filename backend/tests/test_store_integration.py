"""Integration tests that need a REAL Postgres with pgvector (the local Docker one).

Skipped by default. Run them with:   RUN_INTEGRATION=1 python -m pytest tests/test_store_integration.py
(PowerShell:  $env:RUN_INTEGRATION=1; python -m pytest tests/test_store_integration.py)

They only ever touch the LOCAL database and delete the one test document they create.
"""
import os
import sys
from pathlib import Path

import numpy as np
import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402
from app.chunking import Chunk  # noqa: E402
from app.config import settings  # noqa: E402

LOCAL = "postgresql://postgres:postgres@localhost:5433/support"
SLUG = "integration-test-doc"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run (needs the local Docker database)"
)


@pytest.fixture(autouse=True)
def local_db(monkeypatch):
    monkeypatch.setattr(settings, "database_url", LOCAL)  # never Supabase
    store.close_pool()
    store.init_schema()
    yield
    with psycopg.connect(LOCAL, autocommit=True) as c:
        c.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    store.close_pool()


def _vec(seed):
    v = np.random.default_rng(seed).normal(size=settings.embed_dim)
    return (v / np.linalg.norm(v)).astype(np.float32)


def _chunks(n):
    return [Chunk(f"{SLUG}#{i}", SLUG, "Integration test", f"H{i}", f"body {i}") for i in range(n)]


def test_a_failed_replacement_leaves_the_existing_document_intact():
    store.add_document(SLUG, "Original", "a.md", "text/markdown", _chunks(2), np.stack([_vec(1), _vec(2)]))
    wrong_size = np.ones(10, dtype=np.float32)  # the 3rd embedding is the wrong length, so its insert fails
    with pytest.raises(psycopg.Error):
        store.add_document(SLUG, "Replacement", "a.md", "text/markdown", _chunks(3), [_vec(3), _vec(4), wrong_size])

    docs = [d for d in store.list_documents() if d.slug == SLUG]
    assert [(d.title, d.n_chunks) for d in docs] == [("Original", 2)]  # old version survived whole
    with psycopg.connect(LOCAL) as c:
        assert c.execute("SELECT count(*) FROM chunks WHERE doc_slug = %s", (SLUG,)).fetchone()[0] == 2


def test_search_recovers_after_the_server_kills_a_pooled_connection():
    store.add_document(SLUG, "Doc", "a.md", "text/markdown", _chunks(1), np.stack([_vec(7)]))
    assert store.search(_vec(7), 1)[0].doc_slug == SLUG

    with store.get_pool().connection() as conn:
        pid = conn.info.backend_pid
    with psycopg.connect(LOCAL, autocommit=True) as killer:
        killer.execute("SELECT pg_terminate_backend(%s)", (pid,))  # the server drops the idle connection

    hits = store.search(_vec(7), 1)  # must transparently reconnect, not raise
    assert hits and hits[0].doc_slug == SLUG


def test_a_replacement_swaps_the_old_chunks_for_the_new_ones():
    store.add_document(SLUG, "v1", "a.md", "text/markdown", _chunks(3), np.stack([_vec(1), _vec(2), _vec(3)]))
    second = store.add_document(SLUG, "v2", "a.md", "text/markdown", _chunks(1), np.stack([_vec(9)]))
    assert second.replaced is True
    with psycopg.connect(LOCAL) as c:
        assert c.execute("SELECT count(*) FROM chunks WHERE doc_slug = %s", (SLUG,)).fetchone()[0] == 1
