"""Which address counts as 'the visitor' behind a proxy, including attempts to forge it. Offline."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, main  # noqa: E402
from app.clientip import client_ip  # noqa: E402
from app.config import settings  # noqa: E402


class Req:
    """The two things client_ip looks at."""

    def __init__(self, xff=None, host="10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}
        self.client = type("C", (), {"host": host})() if host else None


def with_hops(monkeypatch, n):
    monkeypatch.setattr(settings, "trusted_proxy_hops", n)


def test_default_ignores_the_header_entirely(monkeypatch):
    with_hops(monkeypatch, 0)
    assert client_ip(Req("1.2.3.4")) == "10.0.0.9"  # nobody can spoof anything when no proxy is trusted


def test_one_trusted_proxy_uses_the_last_entry(monkeypatch):
    with_hops(monkeypatch, 1)
    assert client_ip(Req("203.0.113.7")) == "203.0.113.7"


def test_a_forged_entry_on_the_left_is_ignored(monkeypatch):
    with_hops(monkeypatch, 1)
    # the visitor sent "6.6.6.6"; our proxy appended the address it really saw
    assert client_ip(Req("6.6.6.6, 203.0.113.7")) == "203.0.113.7"


def test_two_trusted_proxies_skip_the_inner_one(monkeypatch):
    with_hops(monkeypatch, 2)
    assert client_ip(Req("6.6.6.6, 203.0.113.7, 172.70.1.1")) == "203.0.113.7"


def test_a_short_or_missing_header_falls_back_to_the_connection(monkeypatch):
    with_hops(monkeypatch, 2)
    assert client_ip(Req("203.0.113.7")) == "10.0.0.9"
    assert client_ip(Req(None)) == "10.0.0.9"


def test_no_connection_info_at_all(monkeypatch):
    with_hops(monkeypatch, 0)
    assert client_ip(Req(None, host=None)) == "unknown"


def test_whitespace_and_empty_parts_are_tolerated(monkeypatch):
    with_hops(monkeypatch, 1)
    assert client_ip(Req(" 6.6.6.6 ,  203.0.113.7 ,")) == "203.0.113.7"


def test_the_admin_diagnostic_endpoint_reports_what_the_limiter_will_use(monkeypatch):
    with_hops(monkeypatch, 1)
    main.app.dependency_overrides[auth.require_admin] = lambda: auth.AdminUser(id="u", email="a@b.c")
    try:
        r = TestClient(main.app).get("/api/admin/client-info", headers={"x-forwarded-for": "6.6.6.6, 203.0.113.7"})
    finally:
        main.app.dependency_overrides.clear()
    body = r.json()
    assert r.status_code == 200
    assert body["used_for_rate_limits"] == "203.0.113.7" and body["trusted_proxy_hops"] == 1
    assert body["forwarded_for"] == ["6.6.6.6", "203.0.113.7"]


def test_the_diagnostic_endpoint_needs_an_admin():
    assert TestClient(main.app).get("/api/admin/client-info").status_code in (401, 503)
