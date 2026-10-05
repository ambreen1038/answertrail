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


# ====================================================================== chat log, feedback, analytics
from app import chatlog  # noqa: E402
from app.answer import Citation, Result  # noqa: E402


@pytest.fixture
def clean_chats():
    yield
    with psycopg.connect(LOCAL, autocommit=True) as c:
        c.execute("DELETE FROM conversations WHERE title LIKE 'itest-%'")


def _result(answered=True, text="Up to 10 MB."):
    cites = [Citation("02#1", "Uploading files", "File size limit", "Each file can be up to 10 MB.", 0.75)] if answered else []
    return Result(answered=answered, answer=text, reason="answered" if answered else "model_declined",
                  citations=cites, retrieved=cites, top_score=0.75, latency_ms=120)


def test_conversation_round_trip_with_history_and_cascade(clean_chats):
    cid = chatlog.create_conversation("itest-round-trip")
    assert chatlog.conversation_visible(cid, None)
    chatlog.add_turn(cid, "How big can a file be?", _result(), None)
    chatlog.add_turn(cid, "What about PDFs?", _result(text="Same limit."), "How big can a PDF be?")

    convo = chatlog.get_conversation(cid)
    assert [m["role"] for m in convo["messages"]] == ["user", "assistant", "user", "assistant"]
    first_reply = convo["messages"][1]
    assert first_reply["answered"] is True and first_reply["citations"][0]["heading"] == "File size limit"
    assert first_reply["rating"] is None
    assert convo["messages"][3]["rewritten_query"] == "How big can a PDF be?"

    recent = chatlog.recent_turns(cid, limit=3)
    assert [m["content"] for m in recent] == ["Up to 10 MB.", "What about PDFs?", "Same limit."]  # oldest first, capped

    assert chatlog.delete_conversation(cid) is True
    assert chatlog.get_conversation(cid) is None and chatlog.delete_conversation(cid) is False
    with psycopg.connect(LOCAL) as c:
        assert c.execute("SELECT count(*) FROM messages WHERE conversation_id = %s", (cid,)).fetchone()[0] == 0


def test_feedback_rules(clean_chats):
    a = chatlog.create_conversation("itest-feedback-a")
    b = chatlog.create_conversation("itest-feedback-b")
    mid = chatlog.add_turn(a, "Q?", _result(), None)
    with psycopg.connect(LOCAL) as c:
        user_msg = c.execute("SELECT id FROM messages WHERE conversation_id = %s AND role = 'user'", (a,)).fetchone()[0]

    assert chatlog.set_feedback(a, mid, -1, "too vague") is True
    assert chatlog.set_feedback(b, mid, 1, None) is False       # right message number, wrong conversation
    assert chatlog.set_feedback(a, user_msg, 1, None) is False  # you can only rate the assistant's replies
    assert chatlog.get_conversation(a)["messages"][1]["rating"] == -1

    assert chatlog.set_feedback(a, mid, 1, None) is True        # changing your mind replaces, not duplicates
    with psycopg.connect(LOCAL) as c:
        assert c.execute("SELECT count(*), min(rating), min(comment) FROM feedback WHERE message_id = %s", (mid,)).fetchone() == (1, 1, None)

    chatlog.delete_conversation(a)
    with psycopg.connect(LOCAL) as c:
        assert c.execute("SELECT count(*) FROM feedback WHERE message_id = %s", (mid,)).fetchone()[0] == 0


def test_analytics_counts_groups_unanswered_and_lists_downvotes(clean_chats):
    before = chatlog.analytics()["totals"]
    cid = chatlog.create_conversation("itest-analytics")
    chatlog.add_turn(cid, "Does it support Arabic?", _result(answered=False, text="I couldn't find that."), None)
    chatlog.add_turn(cid, "  does it SUPPORT arabic?  ", _result(answered=False, text="I couldn't find that."), None)
    chatlog.add_turn(cid, "How big can a file be?", _result(), None)
    bad = chatlog.add_turn(cid, "Is it free?", _result(text="Probably."), None)
    chatlog.set_feedback(cid, bad, -1, "invented a price")

    a = chatlog.analytics()
    t = a["totals"]
    assert t["questions"] - before["questions"] == 4
    assert t["answered"] - before["answered"] == 2 and t["refused"] - before["refused"] == 2
    assert t["thumbs_down"] - before["thumbs_down"] == 1
    assert t["median_latency_ms"] == 120 and t["answered_rate"] is not None

    gap = [g for g in a["unanswered"] if g["question"].strip().lower() == "does it support arabic?"]
    assert len(gap) == 1 and gap[0]["count"] == 2             # case and spacing differences are grouped together
    assert any(d["question"] == "Is it free?" and d["comment"] == "invented a price" for d in a["downvoted"])
    assert a["daily"][-1]["questions"] >= 4 and a["daily"][-1]["answered"] >= 2


# ====================================================================== hybrid search
@pytest.fixture(autouse=True)
def hybrid_on(monkeypatch):
    """Hybrid search is off by default; these tests exercise it, so switch it on for the whole module."""
    monkeypatch.setattr(settings, "hybrid_search", True)


def _hybrid_chunks(rare_at: int):
    """Six chunks; the one at index `rare_at` is the only one containing the made-up word 'zorblax'."""
    texts = [
        "Files up to 10 MB are accepted.",
        "Statuses move from queued to approved.",
        "Duplicates are flagged for review.",
        "Exports are available as CSV.",
        "Passwords can be reset by email.",
        "Notifications need the tab open.",
    ]
    texts[rare_at] = "The zorblax setting controls rounding."
    return [Chunk(f"{SLUG}#{i}", SLUG, "Integration test", f"H{i}", t) for i, t in enumerate(texts)]


def _store_six(rare_at: int):
    store.add_document(SLUG, "Doc", "a.md", "text/markdown", _hybrid_chunks(rare_at), np.stack([_vec(i) for i in range(6)]))


def test_hybrid_search_surfaces_an_exact_keyword_that_the_vectors_miss():
    q = _vec(0)  # "meaning" says: chunk 0
    worst = min(range(1, 6), key=lambda i: float(np.dot(q, _vec(i))))  # the chunk least similar to the query
    _store_six(rare_at=worst)  # (the local database also holds the real knowledge base; that is fine)

    vector_only = [h.id for h in store.search(q, 2)]
    hybrid = [h.id for h in store.search(q, 2, "what does zorblax do?")]

    assert vector_only[0] == f"{SLUG}#0" and f"{SLUG}#{worst}" not in vector_only
    assert set(hybrid) == {f"{SLUG}#0", f"{SLUG}#{worst}"}  # the best meaning match AND the exact-word match


def test_hybrid_scores_are_still_cosine_similarity():
    _store_six(rare_at=5)
    q = _vec(0)
    mine = [h for h in store.search(q, 70, "zorblax rounding") if h.doc_slug == SLUG]
    assert len(mine) >= 2  # (hybrid returns at most the candidate lists, not every chunk)
    for h in mine:
        idx = int(h.id.rsplit("#", 1)[1])
        assert h.score == pytest.approx(float(np.dot(q, _vec(idx))), abs=1e-4)


def test_hybrid_can_be_switched_off_and_falls_back_for_stop_word_only_questions(monkeypatch):
    _store_six(rare_at=5)
    q = _vec(0)
    plain = [h.id for h in store.search(q, 3)]
    monkeypatch.setattr(settings, "hybrid_search", False)
    assert [h.id for h in store.search(q, 3, "zorblax")] == plain
    monkeypatch.setattr(settings, "hybrid_search", True)
    assert [h.id for h in store.search(q, 3, "the and of")] == plain  # nothing to match on: same as vector-only


# ====================================================================== conversation ownership
U1, U2 = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000a2"


def test_an_owned_conversation_is_invisible_to_everyone_but_its_owner(clean_chats):
    cid = chatlog.create_conversation("itest-owned", U1)
    mid = chatlog.add_turn(cid, "Q?", _result(), None)

    assert chatlog.conversation_visible(cid, U1) is True
    assert chatlog.conversation_visible(cid, U2) is False
    assert chatlog.conversation_visible(cid, None) is False  # anonymous visitors cannot see it either
    assert chatlog.get_conversation(cid, U1) is not None
    assert chatlog.get_conversation(cid, U2) is None and chatlog.get_conversation(cid, None) is None

    assert chatlog.set_feedback(cid, mid, 1, None, U2) is False and chatlog.set_feedback(cid, mid, 1, None, None) is False
    assert chatlog.set_feedback(cid, mid, 1, None, U1) is True

    assert chatlog.delete_conversation(cid, U2) is False and chatlog.delete_conversation(cid, None) is False
    assert chatlog.get_conversation(cid, U1) is not None  # still there after the failed deletes
    assert chatlog.delete_conversation(cid, U1) is True


def test_an_anonymous_conversation_stays_open_to_anyone_holding_its_id(clean_chats):
    cid = chatlog.create_conversation("itest-anon")
    assert chatlog.conversation_visible(cid, None) and chatlog.conversation_visible(cid, U1)
    assert chatlog.get_conversation(cid, U2) is not None


def test_claiming_moves_only_unowned_conversations(clean_chats):
    anon = chatlog.create_conversation("itest-claim-anon")
    theirs = chatlog.create_conversation("itest-claim-theirs", U2)
    assert chatlog.claim_conversations(U1, [anon, theirs]) == 1
    assert chatlog.conversation_visible(anon, U1) and not chatlog.conversation_visible(anon, None)
    assert chatlog.conversation_visible(theirs, U2) and not chatlog.conversation_visible(theirs, U1)  # untouched
    assert chatlog.claim_conversations(U1, []) == 0


def test_list_and_delete_all_for_a_user(clean_chats):
    a = chatlog.create_conversation("itest-list-1", U1)
    chatlog.add_turn(a, "Q?", _result(), None)
    b = chatlog.create_conversation("itest-list-2", U1)
    chatlog.create_conversation("itest-list-other", U2)
    chatlog.add_turn(b, "Q?", _result(), None)  # b is now the most recently updated

    listed = chatlog.list_conversations(U1)
    assert [c["id"] for c in listed][:2] == [b, a] and all(c["title"].startswith("itest-list-") for c in listed)
    assert chatlog.delete_all_for_user(U1) >= 2
    assert chatlog.list_conversations(U1) == [] and len(chatlog.list_conversations(U2)) == 1


def test_a_word_found_in_most_chunks_is_ignored_by_the_keyword_ranking():
    texts = [f"The gadget handles case number {i}." for i in range(12)]  # "gadget" is in every chunk of this document
    chunks = [Chunk(f"{SLUG}#{i}", SLUG, "Integration test", f"H{i}", t) for i, t in enumerate(texts)]
    store.add_document(SLUG, "Doc", "a.md", "text/markdown", chunks, np.stack([_vec(i) for i in range(12)]))
    q = _vec(3)
    assert [h.id for h in store.search(q, 5, "gadget")] == [h.id for h in store.search(q, 5)]  # no rare word: pure vector order
