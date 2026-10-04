"""The Gemini client must survive slow/failed calls and always fail with GeminiError."""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import gemini  # noqa: E402
from app.config import settings  # noqa: E402


class FakeResponse:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body or {}, text

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _no_sleep_and_a_key(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)  # keep tests instant
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")


def _script(monkeypatch, outcomes):
    """Make httpx.post replay `outcomes` in order: an exception to raise, or a response to return."""
    calls = []

    def fake_post(*a, **kw):
        calls.append(kw.get("timeout"))
        out = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    return calls


def test_a_timeout_is_retried_and_then_succeeds(monkeypatch):
    calls = _script(monkeypatch, [httpx.ReadTimeout("stalled"), httpx.ConnectError("reset"), FakeResponse(200, {"ok": 1})])
    assert gemini._post("x", {}) == {"ok": 1}
    assert len(calls) == 3


def test_persistent_timeouts_end_in_a_clean_geminierror_not_a_raw_httpx_error(monkeypatch):
    calls = _script(monkeypatch, [httpx.ReadTimeout("stalled")])
    with pytest.raises(gemini.GeminiError, match="ReadTimeout"):
        gemini._post("x", {})
    assert len(calls) == 3  # bounded: it does not retry forever


def test_rate_limits_and_server_errors_are_retried(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse(429, text="slow down"), FakeResponse(503), FakeResponse(200, {"ok": 2})])
    assert gemini._post("x", {}) == {"ok": 2}
    assert len(calls) == 3


def test_a_client_error_is_not_retried(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse(400, text="bad request")])
    with pytest.raises(gemini.GeminiError, match="400"):
        gemini._post("x", {})
    assert len(calls) == 1


def test_missing_key_fails_fast_without_any_network_call(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse(200)])
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(gemini.GeminiError, match="GEMINI_API_KEY"):
        gemini._post("x", {})
    assert calls == []


def test_per_attempt_timeout_is_short_enough_to_retry_a_stalled_call(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse(200, {})])
    gemini._post("x", {})
    assert calls[0].read == 30.0  # not the old 60s that let one stalled call block for a minute+
