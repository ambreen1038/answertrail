"""Conversation memory, follow-up rewriting, feedback and analytics access: all offline (fakes only)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer, auth, chatlog, main  # noqa: E402
from app.answer import Result  # noqa: E402
from app.gemini import GeminiError  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402

CID = "11111111-1111-1111-1111-111111111111"


def fake_result(text="Up to 10 MB."):
    return Result(answered=True, answer=text, reason="answered", citations=[], retrieved=[], top_score=0.8, latency_ms=5)


class Env:
    """Records every call so the tests can assert what the endpoint did, and in what order."""

    def __init__(self):
        self.asked, self.rewrote, self.added, self.created = [], [], [], []
        self.history, self.exists = [], True


@pytest.fixture
def env(monkeypatch):
    e = Env()
    monkeypatch.setattr(main, "limiter", RateLimiter(1000, 1000, 1000))
    monkeypatch.setattr(answer, "ask", lambda q: e.asked.append(q) or fake_result())
    monkeypatch.setattr(answer, "rewrite_question", lambda h, q: e.rewrote.append((h, q)) or "How big can PDF files be?")
    monkeypatch.setattr(chatlog, "recent_turns", lambda cid: e.history)
    monkeypatch.setattr(chatlog, "conversation_visible", lambda cid, uid: e.exists)
    monkeypatch.setattr(chatlog, "create_conversation", lambda title, uid=None: e.created.append(title) or CID)
    monkeypatch.setattr(chatlog, "add_turn", lambda cid, q, r, rw: e.added.append((cid, q, rw)) or 42)
    return e


@pytest.fixture
def client():
    return TestClient(main.app)


def ask(client, question="How big can a file be?", cid=None):
    body = {"question": question}
    if cid:
        body["conversation_id"] = cid
    return client.post("/api/ask", json=body)


# ---------------------------------------------------------------- asking


def test_first_question_creates_a_conversation_and_is_not_rewritten(env, client):
    r = ask(client)
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"] == CID and body["message_id"] == 42 and body["rewritten_query"] is None
    assert env.created == ["How big can a file be?"] and env.rewrote == []
    assert env.asked == ["How big can a file be?"]


def test_a_follow_up_is_rewritten_and_the_rewritten_text_is_what_gets_searched(env, client):
    env.history = [{"role": "user", "content": "How big can a file be?"}, {"role": "assistant", "content": "Up to 10 MB."}]
    r = ask(client, "What about PDFs?", CID).json()
    assert env.rewrote and env.rewrote[0][1] == "What about PDFs?"
    assert env.asked == ["How big can PDF files be?"]
    assert r["rewritten_query"] == "How big can PDF files be?"
    # what is saved against the turn is the visitor's own wording plus the rewrite, not just the rewrite
    assert env.added == [(CID, "What about PDFs?", "How big can PDF files be?")]
    assert env.created == []  # same conversation continues


def test_a_failed_rewrite_falls_back_to_the_original_question(env, client, monkeypatch):
    env.history = [{"role": "user", "content": "x"}]

    def boom(h, q):
        raise GeminiError("down")

    monkeypatch.setattr(answer, "rewrite_question", boom)
    r = ask(client, "What about PDFs?", CID)
    assert r.status_code == 200 and env.asked == ["What about PDFs?"] and r.json()["rewritten_query"] is None


def test_an_unknown_or_deleted_conversation_starts_a_fresh_one(env, client):
    env.history, env.exists = [], False
    r = ask(client, cid=CID).json()
    assert env.created and r["conversation_id"] == CID


def test_a_chat_log_outage_never_stops_the_answer(env, client, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("database unavailable")

    for name in ("conversation_visible", "create_conversation", "add_turn"):
        monkeypatch.setattr(chatlog, name, down)
    r = ask(client, cid=CID)
    assert r.status_code == 200
    body = r.json()
    assert body["answered"] is True and body["conversation_id"] is None and body["message_id"] is None


def test_gemini_outage_on_the_answer_is_a_clean_502_and_nothing_is_saved(env, client, monkeypatch):
    def boom(q):
        raise GeminiError("quota")

    monkeypatch.setattr(answer, "ask", boom)
    assert ask(client).status_code == 502
    assert env.added == [] and env.created == []


def test_a_malformed_conversation_id_is_rejected(env, client):
    assert ask(client, cid="not-a-uuid").status_code == 422


# ---------------------------------------------------------------- rewrite_question itself


def test_rewrite_makes_no_ai_call_when_there_is_no_history():
    called = []
    assert answer.rewrite_question([], "hello there", lambda *a: called.append(1)) == "hello there"
    assert not called


def test_rewrite_sends_the_recent_conversation_and_returns_the_standalone_question():
    seen = {}

    def gen(system, prompt, schema):
        seen["prompt"] = prompt
        return {"standalone": "  How large can a PDF be?  "}

    hist = [{"role": "user", "content": "What file types work?"}, {"role": "assistant", "content": "PDF, PNG, JPEG, WebP."}]
    assert answer.rewrite_question(hist, "and how large?", gen) == "How large can a PDF be?"
    assert "Customer: What file types work?" in seen["prompt"] and "Assistant: PDF, PNG" in seen["prompt"]
    assert seen["prompt"].endswith("Latest customer message: and how large?")


def test_rewrite_falls_back_to_the_original_when_the_model_returns_nothing():
    assert answer.rewrite_question([{"role": "user", "content": "x"}], "and PDFs?", lambda *a: {"standalone": "  "}) == "and PDFs?"


def test_rewrite_output_is_length_capped():
    out = answer.rewrite_question([{"role": "user", "content": "x"}], "q", lambda *a: {"standalone": "a" * 1000})
    assert len(out) == 300


# ---------------------------------------------------------------- conversations and feedback routes


def test_get_and_delete_conversation(monkeypatch, client):
    monkeypatch.setattr(chatlog, "get_conversation", lambda cid, uid=None: {"id": cid, "messages": []} if cid == CID else None)
    monkeypatch.setattr(chatlog, "delete_conversation", lambda cid, uid=None: cid == CID)
    ok = client.get(f"/api/conversations/{CID}")
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    assert client.get("/api/conversations/22222222-2222-2222-2222-222222222222").status_code == 404
    assert client.get("/api/conversations/not-a-uuid").status_code == 422
    assert client.delete(f"/api/conversations/{CID}").status_code == 204
    assert client.delete("/api/conversations/22222222-2222-2222-2222-222222222222").status_code == 404


def test_feedback_accepts_only_thumbs_up_or_down_and_only_for_a_real_message(monkeypatch, client):
    saved = []
    monkeypatch.setattr(chatlog, "set_feedback", lambda cid, mid, rating, comment, uid=None: saved.append((cid, mid, rating, comment)) or mid == 42)
    url = f"/api/conversations/{CID}/messages/%s/feedback"
    assert client.post(url % 42, json={"rating": -1, "comment": "wrong"}).status_code == 204
    assert saved == [(CID, 42, -1, "wrong")]
    assert client.post(url % 7, json={"rating": 1}).status_code == 404       # not found in this conversation
    assert client.post(url % 42, json={"rating": 5}).status_code == 422       # only +1 / -1
    assert client.post(url % 42, json={"rating": 1, "comment": "x" * 501}).status_code == 422


# ---------------------------------------------------------------- analytics is admin-only


def test_analytics_requires_an_admin_and_returns_the_data_when_allowed(monkeypatch, client):
    monkeypatch.setattr(chatlog, "analytics", lambda: {"totals": {"questions": 3}})
    assert client.get("/api/admin/analytics").status_code in (401, 503)       # not signed in / not configured

    main.app.dependency_overrides[auth.require_admin] = lambda: auth.AdminUser(id="u", email="a@b.c")
    try:
        r = client.get("/api/admin/analytics")
        assert r.status_code == 200 and r.json()["totals"]["questions"] == 3 and r.headers["cache-control"] == "no-store"
    finally:
        main.app.dependency_overrides.clear()
