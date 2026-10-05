"""Conversations, messages, feedback and analytics.

Two kinds of conversation:
  * anonymous (user_id NULL): the unguessable UUID is the only key, as before;
  * owned (user_id set, by a signed-in customer): only that customer can read, delete or rate it.
    Anyone else, anonymous visitors included, gets "not found", exactly as if it didn't exist.
No IP address is stored either way. The assistant rows double as the question log that the admin
Analytics page reads.

Every function that touches one conversation takes `uid` (the signed-in customer's id, or None) and
applies the same rule, VISIBLE below, so there is one definition of "who may see this chat".
"""
from dataclasses import asdict
from typing import Any

from psycopg.types.json import Jsonb

from . import store
from .answer import Result


# `user_id = NULL` is never true, so with uid=None only anonymous conversations are visible.
VISIBLE = "(user_id IS NULL OR user_id = %s)"


def create_conversation(title: str, uid: str | None = None) -> str:
    return str(store._run(lambda c: c.execute(
        "INSERT INTO conversations (title, user_id) VALUES (%s, %s) RETURNING id", (title[:80], uid)
    ).fetchone()[0]))


def conversation_visible(cid: str, uid: str | None) -> bool:
    """Does this conversation exist AND may this visitor use it?"""
    return store._run(lambda c: c.execute(
        f"SELECT 1 FROM conversations WHERE id = %s AND {VISIBLE}", (cid, uid)
    ).fetchone() is not None)


def recent_turns(cid: str, limit: int = 6) -> list[dict[str, str]]:
    """The last few messages, oldest first, used to resolve follow-up questions like 'what about PDFs?'."""
    rows = store._run(lambda c: c.execute(
        "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY id DESC LIMIT %s", (cid, limit)
    ).fetchall())
    return [{"role": r, "content": t} for r, t in reversed(rows)]


def add_turn(cid: str, question: str, result: Result, rewritten: str | None) -> int:
    """Save the visitor's question and the assistant's reply together; returns the reply's id."""

    def work(conn) -> int:
        with conn.transaction():
            conn.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)", (cid, question))
            mid = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, question, rewritten_query, answered, reason,"
                " citations, top_score, latency_ms) VALUES (%s, 'assistant', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (cid, result.answer, question, rewritten, result.answered, result.reason,
                 Jsonb([asdict(c) for c in result.citations]), result.top_score, result.latency_ms),
            ).fetchone()[0]
            conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (cid,))
        return mid

    return store._run(work)


def get_conversation(cid: str, uid: str | None = None) -> dict[str, Any] | None:
    def work(conn):
        convo = conn.execute(
            f"SELECT id, title, created_at FROM conversations WHERE id = %s AND {VISIBLE}", (cid, uid)
        ).fetchone()
        if convo is None:
            return None
        rows = conn.execute(
            "SELECT m.id, m.role, m.content, m.answered, m.reason, m.citations, m.rewritten_query, f.rating "
            "FROM messages m LEFT JOIN feedback f ON f.message_id = m.id WHERE m.conversation_id = %s ORDER BY m.id",
            (cid,),
        ).fetchall()
        return {
            "id": str(convo[0]), "title": convo[1], "created_at": convo[2].isoformat(),
            "messages": [
                {"id": r[0], "role": r[1], "content": r[2], "answered": r[3], "reason": r[4],
                 "citations": r[5] or [], "rewritten_query": r[6], "rating": r[7]}
                for r in rows
            ],
        }

    return store._run(work)


def delete_conversation(cid: str, uid: str | None = None) -> bool:
    return store._run(lambda c: c.execute(
        f"DELETE FROM conversations WHERE id = %s AND {VISIBLE}", (cid, uid)
    ).rowcount > 0)


def set_feedback(cid: str, mid: int, rating: int, comment: str | None, uid: str | None = None) -> bool:
    """Record (or change) a thumbs up/down. Only succeeds if message `mid` is an assistant reply in
    conversation `cid` AND that conversation is visible to this visitor, so knowing a message number
    alone is not enough to rate someone's chat."""
    return store._run(lambda c: c.execute(
        "INSERT INTO feedback (message_id, rating, comment) "
        "SELECT m.id, %s, %s FROM messages m JOIN conversations v ON v.id = m.conversation_id "
        "WHERE m.id = %s AND m.conversation_id = %s AND m.role = 'assistant' "
        "AND (v.user_id IS NULL OR v.user_id = %s) "
        "ON CONFLICT (message_id) DO UPDATE SET rating = EXCLUDED.rating, comment = EXCLUDED.comment, created_at = now()",
        (rating, (comment or None), mid, cid, uid),
    ).rowcount > 0)


# ------------------------------------------------------------------ a signed-in customer's own chats


def list_conversations(uid: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = store._run(lambda c: c.execute(
        "SELECT id, title, updated_at FROM conversations WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
        (uid, limit),
    ).fetchall())
    return [{"id": str(i), "title": t, "updated_at": ts.isoformat()} for i, t, ts in rows]


def claim_conversations(uid: str, ids: list[str]) -> int:
    """Move anonymous conversations into an account (used right after signing in, to carry over chats
    started before logging in). Only conversations with no owner can be claimed, so this can never
    take a chat away from someone else. Holding an anonymous chat's id already grants full access to
    it, so claiming adds no new power."""
    if not ids:
        return 0
    return store._run(lambda c: c.execute(
        "UPDATE conversations SET user_id = %s WHERE id = ANY(%s::uuid[]) AND user_id IS NULL", (uid, ids)
    ).rowcount)


def delete_all_for_user(uid: str) -> int:
    return store._run(lambda c: c.execute("DELETE FROM conversations WHERE user_id = %s", (uid,)).rowcount)


def analytics(days: int = 14) -> dict[str, Any]:
    def work(conn):
        q = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE answered), count(DISTINCT conversation_id), "
            "avg(latency_ms), percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) "
            "FROM messages WHERE role = 'assistant'"
        ).fetchone()
        fb = conn.execute("SELECT count(*) FILTER (WHERE rating = 1), count(*) FILTER (WHERE rating = -1) FROM feedback").fetchone()
        daily = conn.execute(
            "SELECT created_at::date AS d, count(*), count(*) FILTER (WHERE answered) FROM messages "
            "WHERE role = 'assistant' AND created_at > now() - make_interval(days => %s) GROUP BY d ORDER BY d",
            (days,),
        ).fetchall()
        gaps = conn.execute(
            "SELECT min(question), count(*), max(created_at) FROM messages WHERE role = 'assistant' AND answered = false "
            "GROUP BY lower(trim(question)) ORDER BY count(*) DESC, max(created_at) DESC LIMIT 20"
        ).fetchall()
        down = conn.execute(
            "SELECT m.question, m.content, f.comment, f.created_at FROM feedback f JOIN messages m ON m.id = f.message_id "
            "WHERE f.rating = -1 ORDER BY f.created_at DESC LIMIT 20"
        ).fetchall()
        total, answered = q[0], q[1]
        return {
            "totals": {
                "questions": total, "answered": answered, "refused": total - answered,
                "answered_rate": round(answered / total, 3) if total else None,
                "conversations": q[2],
                "avg_latency_ms": round(q[3]) if q[3] is not None else None,
                "median_latency_ms": round(q[4]) if q[4] is not None else None,
                "thumbs_up": fb[0], "thumbs_down": fb[1],
            },
            "daily": [{"date": d.isoformat(), "questions": n, "answered": a} for d, n, a in daily],
            "unanswered": [{"question": t, "count": n, "last_seen": ts.isoformat()} for t, n, ts in gaps],
            "downvoted": [{"question": t, "answer": a, "comment": c, "at": ts.isoformat()} for t, a, c, ts in down],
        }

    return store._run(work)
