"""Integration tests for the xurl backend — real xurl CLI / X API v2 calls.

These shell out to the real `xurl` binary and hit the live X API, so they run
only when xurl is installed and OAuth2-authenticated. They are marked with
@pytest.mark.integration and skip automatically otherwise.

Usage:
    pytest tests/integration/ -m integration --timeout=30

Note: these make a small number of real (billable) X API requests. The
autouse `default_xai_backend` fixture from tests/conftest.py is overridden
here by setting X_SEARCH_BACKEND=xurl per test.
"""

import json

import pytest

import xurl_client
from x_search_mcp import (
    ResponseFormat,
    XGetUserPostsInput,
    XSearchPostsInput,
    x_auth_status,
    x_get_user_posts,
    x_search_posts,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not xurl_client.available(),
        reason="xurl not installed/authenticated — skipping xurl integration",
    ),
]


@pytest.fixture()
def force_xurl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_SEARCH_BACKEND", "xurl")


@pytest.mark.timeout(30)
class TestXurlIntegration:
    async def test_auth_status_reports_xurl(self, force_xurl) -> None:
        out = json.loads(await x_auth_status())
        assert out["xurl_available"] is True
        assert out["effective_backend"] == "xurl"

    async def test_user_posts_real(self, force_xurl) -> None:
        params = XGetUserPostsInput(username="xai", max_results=2)
        result = await x_get_user_posts(params)
        assert isinstance(result, str)
        assert len(result) > 0
        # Markdown output carries a post URL.
        assert "x.com/" in result or "No posts found." in result

    async def test_search_json_real(self, force_xurl) -> None:
        params = XSearchPostsInput(
            query="from:xai",
            max_results=2,
            response_format=ResponseFormat.JSON,
        )
        result = await x_search_posts(params)
        data = json.loads(result)
        assert isinstance(data, list)
        if data:
            assert "id" in data[0]
            assert "url" in data[0]
