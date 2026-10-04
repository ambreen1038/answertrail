"""The rate limiter, driven by a fake clock so every window and reset can be tested instantly."""
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer, main  # noqa: E402
from app.ratelimit import DAY, RateLimiter  # noqa: E402


class Clock:
    def __init__(self, start=10 * DAY + 3600.0):  # 01:00 UTC on some day
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make(per_minute=3, per_day=100, global_day=1000, **kw):
    clock = Clock()
    return RateLimiter(per_minute, per_day, global_day, clock=clock, **kw), clock


# ---------------------------------------------------------------- per-minute window


def test_allows_up_to_the_limit_then_blocks_with_a_useful_wait_time():
    rl, clock = make(per_minute=3)
    assert all(rl.check("a").allowed for _ in range(3))
    d = rl.check("a")
    assert not d.allowed and d.scope == "minute"
    assert 1 <= d.retry_after <= 61
    assert str(d.retry_after) in d.message


def test_the_window_slides_so_waiting_the_stated_time_works():
    rl, clock = make(per_minute=2)
    rl.check("a")
    clock.advance(20)
    rl.check("a")
    d = rl.check("a")
    assert not d.allowed
    clock.advance(d.retry_after)  # do exactly what the message says
    assert rl.check("a").allowed


def test_a_refused_request_does_not_extend_the_block_or_use_up_allowance():
    rl, clock = make(per_minute=1, per_day=2)
    assert rl.check("a").allowed
    for _ in range(50):  # hammering while blocked...
        assert not rl.check("a").allowed
    clock.advance(61)
    assert rl.check("a").allowed          # ...did not lengthen the block
    clock.advance(61)
    assert not rl.check("a").allowed      # daily allowance of 2 is spent: the 50 refusals cost nothing, so exactly 2 were used
    assert rl.check("a").scope == "day"


def test_different_clients_are_limited_independently():
    rl, _ = make(per_minute=1)
    assert rl.check("a").allowed
    assert not rl.check("a").allowed
    assert rl.check("b").allowed


# ---------------------------------------------------------------- daily limits


def test_per_client_daily_cap_and_reset_at_utc_midnight():
    rl, clock = make(per_minute=100, per_day=3)
    assert all(rl.check("a").allowed for _ in range(3))
    d = rl.check("a")
    assert not d.allowed and d.scope == "day"
    assert d.retry_after == pytest.approx(DAY - (clock.now % DAY), abs=2)  # waits until midnight UTC
    clock.advance(d.retry_after)
    assert rl.check("a").allowed
    assert rl.check("b").allowed  # another client was never affected


def test_global_cap_blocks_everyone_and_resets_next_day():
    rl, clock = make(per_minute=100, per_day=100, global_day=4)
    for client in ("a", "b", "c", "d"):
        assert rl.check(client).allowed
    d = rl.check("brand-new-client")
    assert not d.allowed and d.scope == "global"
    assert "capacity" in d.message
    clock.advance(DAY)
    assert rl.check("brand-new-client").allowed


def test_a_per_minute_refusal_does_not_burn_the_global_budget():
    rl, _ = make(per_minute=1, global_day=2)
    assert rl.check("a").allowed
    for _ in range(20):
        rl.check("a")                     # all refused by the minute limit
    assert rl.check("b").allowed          # the second (and last) global slot is still there


# ---------------------------------------------------------------- memory and concurrency


def test_memory_is_bounded_by_dropping_the_stalest_clients():
    rl, _ = make(max_clients=100)
    for i in range(1000):
        rl.check(f"ip-{i}")
    assert len(rl._clients) == 100
    assert "ip-999" in rl._clients and "ip-0" not in rl._clients


def test_concurrent_requests_cannot_exceed_the_limit():
    rl, _ = make(per_minute=10, per_day=1000, global_day=1000)
    results = []

    def hit():
        results.append(rl.check("same-client").allowed)

    threads = [threading.Thread(target=hit) for _ in range(100)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 10


# ---------------------------------------------------------------- through the real endpoint


@pytest.fixture
def client(monkeypatch):
    rl, _ = make(per_minute=2)
    monkeypatch.setattr(main, "limiter", rl)
    calls = []

    class Fake:
        def to_dict(self):
            return {"answered": True, "answer": "ok", "reason": "answered", "citations": []}

    monkeypatch.setattr(answer, "ask", lambda q: calls.append(q) or Fake())
    monkeypatch.setattr(main.store, "count_chunks", lambda: 58)
    c = TestClient(main.app)
    c.calls = calls
    return c


def _ask(c):
    return c.post("/api/ask", json={"question": "How big can a file be?"})


def test_third_question_in_a_minute_gets_429_with_retry_after_and_never_reaches_gemini(client):
    assert _ask(client).status_code == 200
    assert _ask(client).status_code == 200
    r = _ask(client)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "too quickly" in r.json()["detail"]
    assert len(client.calls) == 2  # the refused request cost no Gemini quota


def test_health_check_is_not_rate_limited(client):
    for _ in range(20):
        assert client.get("/api/health").status_code == 200
