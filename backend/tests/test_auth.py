"""Admin login: every branch of the authorization decision, with Supabase faked."""
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, main, store  # noqa: E402
from app.config import settings  # noqa: E402

ADMIN = {"id": "u-1", "email": "Admin@Example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com, other@example.com")
    monkeypatch.setattr(store, "list_documents", lambda: [])
    main.app.dependency_overrides.clear()  # the real auth dependency must run in this file


def client(monkeypatch, fetch):
    monkeypatch.setattr(auth, "_fetch_user", fetch)
    return TestClient(main.app)


def get(c, header="Bearer good-token"):
    headers = {"authorization": header} if header is not None else {}
    return c.get("/api/admin/documents", headers=headers)


# ---------------------------------------------------------------- fails closed


@pytest.mark.parametrize("missing", ["supabase_url", "supabase_anon_key", "admin_emails"])
def test_any_missing_setting_disables_the_admin_api(monkeypatch, missing):
    monkeypatch.setattr(settings, missing, "")
    c = client(monkeypatch, lambda t: ADMIN)
    assert get(c).status_code == 503


def test_supabase_being_unreachable_is_503_never_a_way_in(monkeypatch):
    def down(t):
        raise auth.AuthUnavailable("ConnectError")

    assert get(client(monkeypatch, down)).status_code == 503


# ---------------------------------------------------------------- not signed in -> 401


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer   ", "Basic abc123", "good-token"])
def test_missing_or_malformed_authorization_header_is_401(monkeypatch, header):
    called = []
    c = client(monkeypatch, lambda t: called.append(t) or ADMIN)
    assert get(c, header).status_code == 401
    assert not called  # we do not even ask Supabase about junk


def test_invalid_or_expired_token_is_401(monkeypatch):
    def reject(t):
        raise auth.InvalidToken()

    assert get(client(monkeypatch, reject)).status_code == 401


# ---------------------------------------------------------------- signed in but not allowed -> 403


def test_signed_in_user_not_on_the_allowlist_is_403(monkeypatch):
    stranger = {"id": "u-2", "email": "stranger@example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}
    assert get(client(monkeypatch, lambda t: stranger)).status_code == 403


def test_allowlisted_email_that_is_not_confirmed_is_403(monkeypatch):
    # Someone must not be able to claim an admin address they don't own.
    unconfirmed = {"id": "u-3", "email": "admin@example.com", "email_confirmed_at": None}
    assert get(client(monkeypatch, lambda t: unconfirmed)).status_code == 403


def test_user_without_an_email_is_403(monkeypatch):
    assert get(client(monkeypatch, lambda t: {"id": "u-4", "email_confirmed_at": "x"})).status_code == 403


# ---------------------------------------------------------------- allowed


def test_confirmed_allowlisted_admin_gets_in_and_email_match_ignores_case(monkeypatch):
    seen = []
    c = client(monkeypatch, lambda t: seen.append(t) or ADMIN)  # ADMIN has "Admin@Example.com"
    assert get(c, "bearer   good-token  ").status_code == 200
    assert seen == ["good-token"]  # the scheme is case-insensitive and the token is trimmed


def test_public_chat_endpoints_do_not_require_login(monkeypatch):
    monkeypatch.setattr(store, "count_chunks", lambda: 58)
    c = TestClient(main.app)
    assert c.get("/api/health").status_code == 200


# ---------------------------------------------------------------- the Supabase call itself


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._b = status, body or {}

    def json(self):
        return self._b


def test_fetch_user_sends_the_right_request_and_returns_the_user(monkeypatch):
    sent = {}

    def fake_get(url, headers, timeout):
        sent.update(url=url, headers=headers)
        return Resp(200, {"id": "u-1", "email": "a@b.c"})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    assert auth._fetch_user("tok")["email"] == "a@b.c"
    assert sent["url"] == "https://example.supabase.co/auth/v1/user"
    assert sent["headers"] == {"apikey": "anon-key", "Authorization": "Bearer tok"}


@pytest.mark.parametrize("status", [401, 403])
def test_fetch_user_maps_rejection_to_invalidtoken(monkeypatch, status):
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: Resp(status))
    with pytest.raises(auth.InvalidToken):
        auth._fetch_user("tok")


def test_fetch_user_maps_timeouts_and_server_errors_to_unavailable(monkeypatch):
    def timeout(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(auth.httpx, "get", timeout)
    with pytest.raises(auth.AuthUnavailable):
        auth._fetch_user("tok")
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: Resp(500))
    with pytest.raises(auth.AuthUnavailable):
        auth._fetch_user("tok")
