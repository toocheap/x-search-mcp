"""Tests for MCP tool functions (x_search_posts, x_get_user_posts, x_get_trending).

These tests focus on prompt construction logic and error handling within
each tool function.  The underlying API call (_call_responses_api) is
replaced via monkeypatch.setattr to isolate tool-specific behaviour.

Reason for monkeypatch: Tool functions' testable logic is prompt
construction (language filters, topic filters, region text, format
selection) and x_search_config assembly.  The HTTP transport is already
thoroughly tested in test_helpers.py, so duplicating that coverage here
would add no value.  This is the minimal intervention needed and is
documented here per project policy.
"""

import json
from typing import Optional

import pytest

import x_search_mcp
from x_search_mcp import (
    ResponseFormat,
    XGetUserPostsInput,
    XSearchPostsInput,
    XTrendingInput,
    x_get_trending,
    x_get_user_posts,
    x_search_posts,
)


# ---------------------------------------------------------------------------
# Helpers for capturing _call_responses_api calls
# ---------------------------------------------------------------------------


class ApiCallCapture:
    """Captures calls to _call_responses_api for assertion."""

    def __init__(self, return_value: str = "mock response") -> None:
        self.calls: list[dict] = []
        self.return_value = return_value

    async def __call__(
        self,
        user_prompt: str,
        *,
        x_search_config: Optional[dict] = None,
    ) -> str:
        self.calls.append({
            "prompt": user_prompt,
            "x_search_config": x_search_config,
        })
        return self.return_value


@pytest.fixture()
def capture_api(
    monkeypatch: pytest.MonkeyPatch, fake_api_key: str
) -> ApiCallCapture:
    """Replace _call_responses_api with a capturing fake."""
    cap = ApiCallCapture()
    monkeypatch.setattr(x_search_mcp, "_call_responses_api", cap)
    return cap


@pytest.fixture()
def failing_api(
    monkeypatch: pytest.MonkeyPatch, fake_api_key: str
) -> None:
    """Replace _call_responses_api with one that raises RuntimeError."""

    async def _fail(
        user_prompt: str,
        *,
        x_search_config: Optional[dict] = None,
    ) -> str:
        raise RuntimeError("API call failed")

    monkeypatch.setattr(x_search_mcp, "_call_responses_api", _fail)


# ===================================================================
# x_search_posts
# ===================================================================


class TestXSearchPosts:
    """Tests for the x_search_posts tool function."""

    async def test_basic_search_prompt(self, capture_api: ApiCallCapture) -> None:
        """Prompt includes the query and max_results."""
        params = XSearchPostsInput(query="AI news", max_results=5)
        result = await x_search_posts(params)

        assert result == "mock response"
        assert len(capture_api.calls) == 1
        prompt = capture_api.calls[0]["prompt"]
        assert "AI news" in prompt
        assert "5" in prompt

    async def test_language_filter_in_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Language filter text is appended to the prompt."""
        params = XSearchPostsInput(query="test", language="ja")
        await x_search_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "ja" in prompt

    async def test_no_language_filter(
        self, capture_api: ApiCallCapture
    ) -> None:
        """No language text appears when language is None."""
        params = XSearchPostsInput(query="test")
        await x_search_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "Filter to" not in prompt

    async def test_json_format(self, capture_api: ApiCallCapture) -> None:
        """JSON format is included in prompt when specified."""
        params = XSearchPostsInput(query="test", response_format="json")
        await x_search_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "JSON" in prompt

    async def test_markdown_format(self, capture_api: ApiCallCapture) -> None:
        """Markdown format is the default."""
        params = XSearchPostsInput(query="test")
        await x_search_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "markdown" in prompt

    async def test_date_filters_passed_to_config(
        self, capture_api: ApiCallCapture
    ) -> None:
        """from_date and to_date are passed to x_search_config."""
        params = XSearchPostsInput(
            query="test", from_date="2025-01-01", to_date="2025-12-31"
        )
        await x_search_posts(params)

        config = capture_api.calls[0]["x_search_config"]
        assert config is not None
        assert config["from_date"] == "2025-01-01"
        assert config["to_date"] == "2025-12-31"

    async def test_no_dates_gives_none_config(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Config is None when no dates are specified."""
        params = XSearchPostsInput(query="test")
        await x_search_posts(params)

        config = capture_api.calls[0]["x_search_config"]
        assert config is None

    async def test_error_returns_formatted_message(
        self, failing_api: None
    ) -> None:
        """Errors are caught and formatted via _handle_api_error."""
        params = XSearchPostsInput(query="test")
        result = await x_search_posts(params)

        parsed = json.loads(result)
        assert "error" in parsed
        assert "API call failed" in parsed["error"]


# ===================================================================
# x_get_user_posts
# ===================================================================


class TestXGetUserPosts:
    """Tests for the x_get_user_posts tool function."""

    async def test_basic_user_search_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Prompt includes the username with @ prefix."""
        params = XGetUserPostsInput(username="elonmusk", max_results=5)
        result = await x_get_user_posts(params)

        assert result == "mock response"
        prompt = capture_api.calls[0]["prompt"]
        assert "@elonmusk" in prompt
        assert "5" in prompt

    async def test_topic_filter_in_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Topic filter text is appended to the prompt."""
        params = XGetUserPostsInput(username="test", topic_filter="AI")
        await x_get_user_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "AI" in prompt

    async def test_no_topic_filter(
        self, capture_api: ApiCallCapture
    ) -> None:
        """No topic text when topic_filter is None."""
        params = XGetUserPostsInput(username="test")
        await x_get_user_posts(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "Focus on posts related to" not in prompt

    async def test_username_in_allowed_handles(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Username is passed as allowed_x_handles in config."""
        params = XGetUserPostsInput(username="elonmusk")
        await x_get_user_posts(params)

        config = capture_api.calls[0]["x_search_config"]
        assert config is not None
        assert config["allowed_x_handles"] == ["elonmusk"]

    async def test_date_filters_with_user(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Date filters and username are combined in config."""
        params = XGetUserPostsInput(
            username="user1",
            from_date="2025-06-01",
            to_date="2025-06-30",
        )
        await x_get_user_posts(params)

        config = capture_api.calls[0]["x_search_config"]
        assert config["from_date"] == "2025-06-01"
        assert config["to_date"] == "2025-06-30"
        assert config["allowed_x_handles"] == ["user1"]

    async def test_error_returns_formatted_message(
        self, failing_api: None
    ) -> None:
        """Errors are caught and formatted via _handle_api_error."""
        params = XGetUserPostsInput(username="test")
        result = await x_get_user_posts(params)

        parsed = json.loads(result)
        assert "error" in parsed


# ===================================================================
# x_get_trending
# ===================================================================


class TestXGetTrending:
    """Tests for the x_get_trending tool function."""

    async def test_global_trending_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Default prompt says 'globally' when no region is set."""
        params = XTrendingInput()
        result = await x_get_trending(params)

        assert result == "mock response"
        prompt = capture_api.calls[0]["prompt"]
        assert "globally" in prompt

    async def test_region_in_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Region text is included when specified."""
        params = XTrendingInput(region="Japan")
        await x_get_trending(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "Japan" in prompt
        assert "globally" not in prompt

    async def test_category_in_prompt(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Category filter text is appended to the prompt."""
        params = XTrendingInput(category="technology")
        await x_get_trending(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "technology" in prompt

    async def test_no_category(
        self, capture_api: ApiCallCapture
    ) -> None:
        """No category text when category is None."""
        params = XTrendingInput()
        await x_get_trending(params)

        prompt = capture_api.calls[0]["prompt"]
        assert "Focus on" not in prompt

    async def test_no_x_search_config(
        self, capture_api: ApiCallCapture
    ) -> None:
        """Trending does not pass x_search_config."""
        params = XTrendingInput()
        await x_get_trending(params)

        config = capture_api.calls[0]["x_search_config"]
        assert config is None

    async def test_error_returns_formatted_message(
        self, failing_api: None
    ) -> None:
        """Errors are caught and formatted via _handle_api_error."""
        params = XTrendingInput()
        result = await x_get_trending(params)

        parsed = json.loads(result)
        assert "error" in parsed
