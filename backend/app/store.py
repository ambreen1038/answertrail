"""Postgres + pgvector storage and similarity search.

Two tables: documents (one row per uploaded or ingested file) and chunks (the searchable pieces,
each with its embedding). Deleting a document deletes its chunks (ON DELETE CASCADE), so there is
no way to leave orphaned searchable text behind.

Connections come from a small pool. Opening a connection to a remote database is slow (a TLS
handshake and authentication, about 2 s from Lahore to a Sydney-hosted Supabase), and teaching each
new connection about the `vector` type costs several more round trips. Doing that per question made
every answer take ~9 s; reusing connections brings the database part down to ~0.4 s.
"""
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypeVar

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from .chunking import Chunk
from .config import settings

T = TypeVar("T")

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _configure(conn: psycopg.Connection) -> None:
    """Runs once per NEW connection, not once per query."""
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(
                settings.database_url,
                min_size=1,
                max_size=5,
                configure=_configure,
                # autocommit: a single statement is already atomic, and wrapping every read in
                # BEGIN/COMMIT costs two extra network round trips (~0.7 s to a remote database).
                # Multi-statement writes use an explicit `conn.transaction()` block instead.
                kwargs={"connect_timeout": 15, "autocommit": True},
                open=False,
            )
            _pool.open(wait=True, timeout=30)
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def _run(work: Callable[[psycopg.Connection], T]) -> T:
    """Run `work` on a pooled connection. A pooled connection can have been closed by the server
    while it sat idle; the pool discards it when that fails, so one retry on a fresh connection is
    enough. Retrying is safe: single statements are atomic, and multi-statement writes run inside
    `conn.transaction()`, which rolls back completely if the connection dies part-way."""
    for attempt in (1, 2):
        try:
            with get_pool().connection() as conn:
                return work(conn)
        except psycopg.OperationalError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def init_schema() -> None:
    # DDL runs on its own short-lived autocommit connection, once at start-up.
    # The extension must exist before register_vector can look up the type.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # One-off migration: the first version had a chunks table with no document link. Its
        # contents are fully rebuildable from kb/, so drop it rather than migrate row by row.
        has_chunks = conn.execute("SELECT to_regclass('public.chunks') IS NOT NULL").fetchone()[0]
        if has_chunks:
            linked = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'document_id'"
            ).fetchone()
            if not linked:
                conn.execute("DROP TABLE chunks")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id serial PRIMARY KEY,
                slug text UNIQUE NOT NULL,
                title text NOT NULL,
                filename text NOT NULL,
                content_type text NOT NULL,
                n_chunks integer NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id text PRIMARY KEY,
                document_id integer NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                doc_slug text NOT NULL,
                doc_title text NOT NULL,
                heading text NOT NULL,
                content text NOT NULL,
                embedding vector({settings.embed_dim}) NOT NULL
            )
            """
        )
        # SECURITY. On Supabase every table in the public schema is automatically exposed through
        # a REST API that anyone holding the (public) anon key can call. Without the lines below,
        # a stranger could read, edit or delete these tables directly and bypass the admin login.
        #   1. Row Level Security with NO policies = deny everything for API users. Our backend
        #      connects as the table owner (postgres), which is not subject to it.
        #   2. Also revoke the API roles' table privileges, as a second independent layer.
        # Harmless on a plain local Postgres, which has neither role.
        conn.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
        conn.execute("ALTER TABLE chunks ENABLE ROW LEVEL SECURITY")
        conn.execute(
            """
            DO $$
            DECLARE r text;
            BEGIN
                FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                        EXECUTE format('REVOKE ALL ON TABLE documents, chunks FROM %I', r);
                    END IF;
                END LOOP;
            END $$
            """
        )


@dataclass
class DocRecord:
    id: int
    slug: str
    title: str
    filename: str
    content_type: str
    n_chunks: int
    created_at: datetime
    replaced: bool = False


def add_document(
    slug: str,
    title: str,
    filename: str,
    content_type: str,
    chunks: list[Chunk],
    embeddings: np.ndarray,
) -> DocRecord:
    """Insert a document and its chunks in ONE transaction. If a document with the same slug
    exists it is replaced, so re-uploading a file updates it instead of duplicating it."""

    def work(conn: psycopg.Connection) -> DocRecord:
        with conn.transaction():  # all-or-nothing: the old version is only removed if the new one is stored
            replaced = conn.execute("DELETE FROM documents WHERE slug = %s", (slug,)).rowcount > 0
            doc_id, created_at = conn.execute(
                "INSERT INTO documents (slug, title, filename, content_type, n_chunks) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at",
                (slug, title, filename, content_type, len(chunks)),
            ).fetchone()
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (id, document_id, doc_slug, doc_title, heading, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [
                        (c.id, doc_id, c.doc_slug, c.doc_title, c.heading, c.content, e)
                        for c, e in zip(chunks, embeddings)
                    ],
                )
        return DocRecord(doc_id, slug, title, filename, content_type, len(chunks), created_at, replaced)

    return _run(work)


def list_documents() -> list[DocRecord]:
    rows = _run(
        lambda conn: conn.execute(
            "SELECT id, slug, title, filename, content_type, n_chunks, created_at "
            "FROM documents ORDER BY created_at DESC, id DESC"
        ).fetchall()
    )
    return [DocRecord(*r) for r in rows]


def delete_document(doc_id: int) -> bool:
    return _run(lambda conn: conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,)).rowcount > 0)


def delete_all_documents() -> int:
    """Remove every document (and, by cascade, every chunk). Used to rebuild from kb/."""
    return _run(lambda conn: conn.execute("DELETE FROM documents").rowcount)


@dataclass
class Hit:
    id: str
    doc_slug: str
    doc_title: str
    heading: str
    content: str
    score: float  # cosine similarity, higher is closer


def search(query_embedding: np.ndarray, k: int) -> list[Hit]:
    # No ANN index on purpose: at this size an exact scan is instant and has perfect recall.
    # Add an HNSW index (vector_cosine_ops) once the corpus is large enough for it to matter.
    rows = _run(
        lambda conn: conn.execute(
            "SELECT id, doc_slug, doc_title, heading, content, 1 - (embedding <=> %s) AS score "
            "FROM chunks ORDER BY embedding <=> %s LIMIT %s",
            (query_embedding, query_embedding, k),
        ).fetchall()
    )
    return [Hit(*r[:5], float(r[5])) for r in rows]


def count_chunks() -> int:
    return _run(lambda conn: conn.execute("SELECT count(*) FROM chunks").fetchone()[0])
