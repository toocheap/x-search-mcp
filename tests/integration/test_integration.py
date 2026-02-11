"""Integration tests for x_search_mcp — real xAI API calls.

These tests hit the live xAI Responses API and are only run when
XAI_API_KEY is available.  They are marked with @pytest.mark.integration
and are designed to be run in a subprocess with a timeout to handle
hangs or unresponsive API.

Usage:
    XAI_API_KEY="xai-xxx" pytest tests/integration/ -m integration --timeout=30

Skip behaviour:
    When XAI_API_KEY is not set, all tests in this module are automatically
    skipped.
"""

import os

import pytest

from x_search_mcp import (
    XGetUserPostsInput,
    XSearchPostsInput,
    XTrendingInput,
    x_get_trending,
    x_get_user_posts,
    x_search_posts,
)

# Skip entire module when API key is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("XAI_API_KEY"),
        reason="XAI_API_KEY not set — skipping integration tests",
    ),
]


@pytest.mark.timeout(60)
class TestSearchPostsIntegration:
    """Integration tests for x_search_posts with real API."""

    async def test_basic_search_returns_text(self) -> None:
        """A simple search returns a non-empty string response."""
        params = XSearchPostsInput(query="Python programming", max_results=3)
        result = await x_search_posts(params)

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_search_with_language_filter(self) -> None:
        """Search with language filter returns results."""
        params = XSearchPostsInput(
            query="AI", max_results=3, language="en"
        )
        result = await x_search_posts(params)

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_search_json_format(self) -> None:
        """Search with JSON format returns parseable content."""
        params = XSearchPostsInput(
            query="technology", max_results=3, response_format="json"
        )
        result = await x_search_posts(params)

        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.timeout(60)
class TestGetUserPostsIntegration:
    """Integration tests for x_get_user_posts with real API."""

    async def test_get_user_posts_returns_text(self) -> None:
        """Fetching a well-known user's posts returns results."""
        params = XGetUserPostsInput(username="xaborsa", max_results=3)
        result = await x_get_user_posts(params)

        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.timeout(60)
class TestGetTrendingIntegration:
    """Integration tests for x_get_trending with real API."""

    async def test_global_trending_returns_text(self) -> None:
        """Global trending topics returns a non-empty response."""
        params = XTrendingInput()
        result = await x_get_trending(params)

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_regional_trending(self) -> None:
        """Regional trending with Japan filter returns results."""
        params = XTrendingInput(region="Japan")
        result = await x_get_trending(params)

        assert isinstance(result, str)
        assert len(result) > 0
