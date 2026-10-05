"""Postgres + pgvector storage and similarity search.

Two tables: documents (one row per uploaded or ingested file) and chunks (the searchable pieces,
each with its embedding). Deleting a document deletes its chunks (ON DELETE CASCADE), so there is
no way to leave orphaned searchable text behind.

Connections come from a small pool. Opening a connection to a remote database is slow (a TLS
handshake and authentication, about 2 s from Lahore to a Sydney-hosted Supabase), and teaching each
new connection about the `vector` type costs several more round trips. Doing that per question made
every answer take ~9 s; reusing connections brings the database part down to ~0.4 s.
"""
import re
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
        # Keyword index for hybrid search: a full-text vector kept in sync by Postgres itself (a
        # generated column), so nothing in the ingestion code has to remember to fill it in.
        conn.execute(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('english', heading || ' ' || content)) STORED"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv)")
        # Chat history, feedback and (via the messages table) the question log. A conversation is
        # either anonymous (user_id is NULL: its random UUID is the only key to it) or owned by a
        # signed-in customer (user_id = their Supabase auth user id; only they can open it). No IP
        # addresses are stored. user_id deliberately has no foreign key: the auth schema belongs to
        # Supabase and is not something this app should depend on.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                title text NOT NULL DEFAULT '',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id bigserial PRIMARY KEY,
                conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role text NOT NULL CHECK (role IN ('user', 'assistant')),
                content text NOT NULL,
                question text,            -- assistant rows: the visitor's original question
                rewritten_query text,     -- assistant rows: the standalone question searched, if rewritten
                answered boolean,
                reason text,
                citations jsonb,
                top_score real,
                latency_ms integer,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id uuid")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS conversations_user_idx ON conversations (user_id, updated_at DESC) "
            "WHERE user_id IS NOT NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS messages_assistant_created_idx ON messages (created_at) WHERE role = 'assistant'"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                message_id bigint PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                rating smallint NOT NULL CHECK (rating IN (-1, 1)),
                comment text,
                created_at timestamptz NOT NULL DEFAULT now()
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
        for table in ("documents", "chunks", "conversations", "messages", "feedback"):
            conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        conn.execute(
            """
            DO $$
            DECLARE r text;
            BEGIN
                FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                        EXECUTE format('REVOKE ALL ON TABLE documents, chunks, conversations, messages, feedback FROM %I', r);
                        EXECUTE format('REVOKE ALL ON SEQUENCE documents_id_seq, messages_id_seq FROM %I', r);
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


_WORD = re.compile(r"[a-z0-9]+")


def keyword_words(text: str) -> list[str]:
    """The distinct lowercase words of a question, for the keyword ranking. Only letters and digits
    survive, so nothing the visitor types can be read as query syntax. (Stop words such as "how" or
    "the" are dropped later by Postgres, and over-common words by the rarity filter in search().)"""
    return list(dict.fromkeys(_WORD.findall(text.lower())))


def search(query_embedding: np.ndarray, k: int, query_text: str | None = None) -> list[Hit]:
    """The k best chunks for a question.

    Vector search alone (query_text=None) ranks by meaning. With query_text and hybrid search on, a
    second ranking by keyword match is merged in with reciprocal rank fusion: each chunk scores
    1/(60+rank) in every list it appears in, and the scores add up. A chunk that both rankings like
    wins; a chunk holding an exact rare word that the embedding blurred can still make it in.

    The keyword ranking is deliberately conservative, because a measured naive version made results
    worse: it only uses DISTINCTIVE words (in at most `hybrid_max_term_share` of the chunks) and, by
    default, only counts a chunk that contains ALL of them. Common words match almost everything, and
    "any rare word" matches junk on a small corpus. If nothing qualifies, the result is exactly the
    vector ranking.

    Either way `score` stays the cosine similarity, which is what the refusal gate and the UI use.

    No ANN index on purpose: at this size an exact scan is instant and has perfect recall. Add an
    HNSW index (vector_cosine_ops) once the corpus is large enough for it to matter.
    """
    words = keyword_words(query_text) if (query_text and settings.hybrid_search) else []
    if not words:
        rows = _run(
            lambda conn: conn.execute(
                "SELECT id, doc_slug, doc_title, heading, content, 1 - (embedding <=> %s) AS score "
                "FROM chunks ORDER BY embedding <=> %s LIMIT %s",
                (query_embedding, query_embedding, k),
            ).fetchall()
        )
        return [Hit(*r[:5], float(r[5])) for r in rows]

    n = max(settings.hybrid_candidates, k)
    rows = _run(
        lambda conn: conn.execute(
            """
            WITH terms AS (  -- how many chunks contain each word (0 for stop words)
                SELECT w, (SELECT count(*) FROM chunks WHERE tsv @@ to_tsquery('english', w)) AS df
                FROM unnest(%(words)s::text[]) AS w
            ), kwq AS (      -- keep only the distinctive words
                SELECT to_tsquery('english', string_agg(w, %(sep)s)) AS q FROM terms
                WHERE df > 0 AND df <= %(share)s * (SELECT count(*) FROM chunks)
            ), vec AS (
                SELECT id, row_number() OVER (ORDER BY embedding <=> %(e)s) AS r
                FROM chunks ORDER BY embedding <=> %(e)s LIMIT %(n)s
            ), kw AS (
                SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, kwq.q) DESC, c.id) AS r
                FROM chunks c, kwq WHERE kwq.q IS NOT NULL AND c.tsv @@ kwq.q
                ORDER BY ts_rank_cd(c.tsv, kwq.q) DESC, c.id LIMIT %(n)s
            ), fused AS (
                SELECT id, sum(1.0 / (%(rrf)s + r)) AS rrf FROM (SELECT * FROM vec UNION ALL SELECT * FROM kw) t GROUP BY id
            )
            SELECT c.id, c.doc_slug, c.doc_title, c.heading, c.content, 1 - (c.embedding <=> %(e)s) AS score
            FROM fused f JOIN chunks c ON c.id = f.id
            ORDER BY f.rrf DESC, score DESC, c.id LIMIT %(k)s
            """,
            {"e": query_embedding, "n": n, "words": words, "share": settings.hybrid_max_term_share,
             "sep": " & " if settings.hybrid_match_all else " | ", "rrf": settings.rrf_k, "k": k},
        ).fetchall()
    )
    return [Hit(*r[:5], float(r[5])) for r in rows]


def count_chunks() -> int:
    return _run(lambda conn: conn.execute("SELECT count(*) FROM chunks").fetchone()[0])
