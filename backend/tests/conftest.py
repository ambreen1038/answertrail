"""Safety net: offline tests must never reach a database.

The .env file points the app at the real (Supabase) database, so a test that forgets to fake one
function can silently write real rows. That happened once (an endpoint test created empty
conversations on every run). Now any attempt to get a database connection in an offline test raises
immediately and names the test. The integration tests (which use the local Docker database on
purpose, and only when RUN_INTEGRATION=1) are exempt.
"""
import pytest

from app import store


@pytest.fixture(autouse=True)
def no_real_database(request, monkeypatch):
    if request.module.__name__.endswith("test_store_integration"):
        return

    def refuse():
        raise RuntimeError(
            f"{request.node.nodeid} tried to open a database connection. Offline tests must fake "
            "the store/chatlog functions they trigger (see tests/conftest.py)."
        )

    monkeypatch.setattr(store, "get_pool", refuse)
