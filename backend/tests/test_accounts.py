"""Customer accounts: who counts as signed in, who is an admin, and which endpoints need which. Supabase is faked."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer, auth, chatlog, main  # noqa: E402
from app.answer import Result  # noqa: E402
from app.config import settings  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402

CID = "11111111-1111-1111-1111-111111111111"
CUSTOMER = {"id": "c-1", "email": "Customer@Example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}
ADMIN = {"id": "a-1", "email": "admin@example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}
UNCONFIRMED_ADMIN_EMAIL = {"id": "x-1", "email": "admin@example.com", "email_confirmed_at": None}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    monkeypatch.setattr(main, "limiter", RateLimiter(1000, 1000, 1000))
    main.app.dependency_overrides.clear()
    auth.clear_token_cache()
    yield
    auth.clear_token_cache()


class Fake:
    """Stands in for Supabase and the chat log, and records what the endpoints asked of them."""

    def __init__(self, monkeypatch, users):
        self.users, self.fetches = users, 0
        self.created, self.visible_checks, self.listed = [], [], []
        self.claims, self.wiped = [], []
        self.visible = True
        monkeypatch.setattr(auth, "_fetch_user", self._fetch)
        monkeypatch.setattr(answer, "ask", lambda q: Result(True, "Up to 10 MB.", "answered", [], [], 0.8, 5))
        monkeypatch.setattr(chatlog, "create_conversation", lambda title, uid=None: self.created.append(uid) or CID)
        monkeypatch.setattr(chatlog, "conversation_visible", lambda cid, uid: self.visible_checks.append(uid) or self.visible)
        monkeypatch.setattr(chatlog, "recent_turns", lambda cid: [])
        monkeypatch.setattr(chatlog, "add_turn", lambda *a: 1)
        monkeypatch.setattr(chatlog, "list_conversations", lambda uid: self.listed.append(uid) or [{"id": CID, "title": "t", "updated_at": "x"}])
        monkeypatch.setattr(chatlog, "claim_conversations", lambda uid, ids: self.claims.append((uid, ids)) or len(ids))
        monkeypatch.setattr(chatlog, "delete_all_for_user", lambda uid: self.wiped.append(uid) or 3)

    def _fetch(self, token):
        self.fetches += 1
        if token not in self.users:
            raise auth.InvalidToken()
        return self.users[token]


@pytest.fixture
def fake(monkeypatch):
    return Fake(monkeypatch, {"customer-token": CUSTOMER, "admin-token": ADMIN, "unconfirmed-token": UNCONFIRMED_ADMIN_EMAIL})


@pytest.fixture
def client():
    return TestClient(main.app)


def bearer(token):
    return {"authorization": f"Bearer {token}"}


def ask(client, headers=None, **extra):
    return client.post("/api/ask", json={"question": "How big can a file be?", **extra}, headers=headers or {})


# ---------------------------------------------------------------- asking, anonymous or signed in


def test_an_anonymous_question_creates_an_unowned_conversation_and_never_calls_supabase(fake, client):
    assert ask(client).status_code == 200
    assert fake.created == [None] and fake.fetches == 0


def test_a_signed_in_question_creates_a_conversation_owned_by_that_customer(fake, client):
    assert ask(client, bearer("customer-token")).status_code == 200
    assert fake.created == ["c-1"]


def test_another_customers_conversation_is_treated_as_unknown_so_a_new_one_starts(fake, client):
    fake.visible = False
    r = ask(client, bearer("customer-token"), conversation_id=CID)
    assert r.status_code == 200 and fake.visible_checks == ["c-1"] and fake.created == ["c-1"]


def test_a_bad_token_is_rejected_not_silently_treated_as_anonymous(fake, client):
    r = ask(client, bearer("forged"))
    assert r.status_code == 401 and fake.created == []


def test_supabase_down_means_503_for_a_token_holder_but_anonymous_asking_still_works(fake, client, monkeypatch):
    def down(t):
        raise auth.AuthUnavailable("ConnectError")

    monkeypatch.setattr(auth, "_fetch_user", down)
    assert ask(client, bearer("customer-token")).status_code == 503
    assert ask(client).status_code == 200


def test_a_token_when_sign_in_is_not_configured_is_503(fake, client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    assert ask(client, bearer("customer-token")).status_code == 503


def test_a_verified_token_is_remembered_briefly_to_save_a_round_trip(fake, client):
    ask(client, bearer("customer-token"))
    ask(client, bearer("customer-token"))
    assert fake.fetches == 1
    ask(client, bearer("admin-token"))
    assert fake.fetches == 2


def test_the_token_cache_never_stores_the_token_itself(fake, client):
    ask(client, bearer("customer-token"))
    assert auth._cache and all("customer-token" not in key for key in auth._cache)


# ---------------------------------------------------------------- admin is separate from signed-in


def test_a_customer_account_cannot_use_the_admin_api(fake, client):
    assert client.get("/api/admin/documents", headers=bearer("customer-token")).status_code == 403
    assert client.get("/api/admin/analytics", headers=bearer("customer-token")).status_code == 403


def test_an_unconfirmed_account_on_the_admin_email_is_not_an_admin(fake, client):
    assert client.get("/api/admin/analytics", headers=bearer("unconfirmed-token")).status_code == 403


@pytest.mark.parametrize("token, expected", [("customer-token", False), ("admin-token", True), ("unconfirmed-token", False)])
def test_me_reports_admin_only_for_a_confirmed_allowlisted_account(fake, client, token, expected):
    r = client.get("/api/me", headers=bearer(token))
    assert r.status_code == 200 and r.json()["is_admin"] is expected and r.headers["cache-control"] == "no-store"


def test_me_lowercases_the_email(fake, client):
    assert client.get("/api/me", headers=bearer("customer-token")).json()["email"] == "customer@example.com"


# ---------------------------------------------------------------- /api/me endpoints


@pytest.mark.parametrize("method, path", [("get", "/api/me"), ("get", "/api/me/conversations"),
                                          ("post", "/api/me/claim"), ("delete", "/api/me/conversations")])
def test_account_endpoints_need_a_signed_in_user(fake, client, method, path):
    kwargs = {"json": {"ids": []}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401
    assert getattr(client, method)(path, headers=bearer("forged"), **kwargs).status_code == 401


def test_my_conversations_lists_only_the_callers_chats(fake, client):
    r = client.get("/api/me/conversations", headers=bearer("customer-token"))
    assert r.status_code == 200 and r.json()[0]["id"] == CID and fake.listed == ["c-1"]


def test_claim_passes_the_callers_id_and_validates_the_ids(fake, client):
    ok = client.post("/api/me/claim", json={"ids": [CID]}, headers=bearer("customer-token"))
    assert ok.status_code == 200 and ok.json() == {"claimed": 1} and fake.claims == [("c-1", [CID])]
    assert client.post("/api/me/claim", json={"ids": ["nope"]}, headers=bearer("customer-token")).status_code == 422
    too_many = [f"00000000-0000-0000-0000-{i:012d}" for i in range(31)]
    assert client.post("/api/me/claim", json={"ids": too_many}, headers=bearer("customer-token")).status_code == 422


def test_delete_all_my_chats(fake, client):
    assert client.delete("/api/me/conversations", headers=bearer("customer-token")).status_code == 204
    assert fake.wiped == ["c-1"]


def test_conversation_routes_pass_the_signed_in_id_down_to_the_ownership_check(fake, client, monkeypatch):
    seen = []
    monkeypatch.setattr(chatlog, "get_conversation", lambda cid, uid=None: seen.append(uid))
    assert client.get(f"/api/conversations/{CID}", headers=bearer("customer-token")).status_code == 404
    assert client.get(f"/api/conversations/{CID}").status_code == 404
    assert seen == ["c-1", None]
