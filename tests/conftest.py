"""Shared fixtures for x_search_mcp tests.

Fixtures provide environment variable isolation for all tests.
Reusable response builders and transport factories are in tests/helpers.py.
"""

import pytest


# ---------------------------------------------------------------------------
# Environment variable fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def default_xai_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the backend to 'xai' by default for determinism.

    Without this, 'auto' would shell out to the real `xurl` CLI during unit
    tests (whose result varies by machine: authenticated dev box vs. clean
    CI). Tests that exercise the xurl path override X_SEARCH_BACKEND
    explicitly. This keeps the existing xAI-path tests meaningful everywhere.
    """
    monkeypatch.setenv("X_SEARCH_BACKEND", "xai")


@pytest.fixture()
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set a fake XAI_API_KEY and return the value."""
    key = "xai-test-key-for-unit-tests"
    monkeypatch.setenv("XAI_API_KEY", key)
    return key


@pytest.fixture()
def clear_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure XAI_API_KEY is not set."""
    monkeypatch.delenv("XAI_API_KEY", raising=False)
