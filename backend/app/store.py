"""Postgres + pgvector storage and similarity search."""
from dataclasses import dataclass

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from .config import settings
from .chunking import Chunk


def _connect(autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url, autocommit=autocommit)
    return conn


def init_schema() -> None:
    # The extension must exist before register_vector can look up the type.
    with _connect(autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id text PRIMARY KEY,
                doc_slug text NOT NULL,
                doc_title text NOT NULL,
                heading text NOT NULL,
                content text NOT NULL,
                embedding vector({settings.embed_dim}) NOT NULL
            )
            """
        )


def replace_all(chunks: list[Chunk], embeddings: np.ndarray) -> None:
    """Idempotent re-ingest: the knowledge base is small, so we rebuild it from scratch."""
    with _connect() as conn:
        register_vector(conn)
        conn.execute("TRUNCATE chunks")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (id, doc_slug, doc_title, heading, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (c.id, c.doc_slug, c.doc_title, c.heading, c.content, e)
                    for c, e in zip(chunks, embeddings)
                ],
            )


@dataclass
class Hit:
    id: str
    doc_slug: str
    doc_title: str
    heading: str
    content: str
    score: float  # cosine similarity, higher is closer


def search(query_embedding: np.ndarray, k: int) -> list[Hit]:
    # No ANN index on purpose: with ~60 chunks an exact scan is instant and has perfect recall.
    # Add an HNSW index (vector_cosine_ops) once the corpus is large enough for it to matter.
    with _connect() as conn:
        register_vector(conn)
        rows = conn.execute(
            "SELECT id, doc_slug, doc_title, heading, content, 1 - (embedding <=> %s) AS score "
            "FROM chunks ORDER BY embedding <=> %s LIMIT %s",
            (query_embedding, query_embedding, k),
        ).fetchall()
    return [Hit(*r[:5], float(r[5])) for r in rows]


def count_chunks() -> int:
    with _connect() as conn:
        return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
