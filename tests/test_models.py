"""Tests for Pydantic input models and ResponseFormat enum.

Validates correct construction, default values, field constraints
(min_length, max_length, ge, le), and extra="forbid" enforcement.
No mocks or stubs — these are pure data-model tests.
"""

import pytest
from pydantic import ValidationError

from x_search_mcp import (
    MAX_RESULTS_DEFAULT,
    ResponseFormat,
    XGetUserPostsInput,
    XSearchPostsInput,
    XTrendingInput,
)


# ===================================================================
# ResponseFormat enum
# ===================================================================


class TestResponseFormat:
    """Tests for the ResponseFormat enum."""

    def test_markdown_value(self) -> None:
        assert ResponseFormat.MARKDOWN == "markdown"

    def test_json_value(self) -> None:
        assert ResponseFormat.JSON == "json"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ResponseFormat.MARKDOWN, str)


# ===================================================================
# XSearchPostsInput
# ===================================================================


class TestXSearchPostsInput:
    """Tests for XSearchPostsInput model validation."""

    def test_minimal_valid(self) -> None:
        """Constructs with only the required `query` field."""
        m = XSearchPostsInput(query="AI news")
        assert m.query == "AI news"
        assert m.max_results == MAX_RESULTS_DEFAULT
        assert m.language is None
        assert m.from_date is None
        assert m.to_date is None
        assert m.response_format == ResponseFormat.MARKDOWN

    def test_all_fields(self) -> None:
        """Constructs with every field specified."""
        m = XSearchPostsInput(
            query="test",
            max_results=5,
            language="ja",
            from_date="2025-01-01",
            to_date="2025-12-31",
            response_format="json",
        )
        assert m.max_results == 5
        assert m.language == "ja"
        assert m.from_date == "2025-01-01"
        assert m.to_date == "2025-12-31"
        assert m.response_format == ResponseFormat.JSON

    def test_query_empty_string_rejected(self) -> None:
        """Empty query string violates min_length=1."""
        with pytest.raises(ValidationError, match="query"):
            XSearchPostsInput(query="")

    def test_query_too_long_rejected(self) -> None:
        """Query over 500 chars violates max_length."""
        with pytest.raises(ValidationError, match="query"):
            XSearchPostsInput(query="x" * 501)

    def test_max_results_zero_rejected(self) -> None:
        """max_results=0 violates ge=1."""
        with pytest.raises(ValidationError, match="max_results"):
            XSearchPostsInput(query="test", max_results=0)

    def test_max_results_too_large_rejected(self) -> None:
        """max_results=31 violates le=30."""
        with pytest.raises(ValidationError, match="max_results"):
            XSearchPostsInput(query="test", max_results=31)

    def test_extra_field_rejected(self) -> None:
        """Unknown fields are rejected due to extra='forbid'."""
        with pytest.raises(ValidationError, match="extra_field"):
            XSearchPostsInput(query="test", extra_field="oops")

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from query."""
        m = XSearchPostsInput(query="  hello  ")
        assert m.query == "hello"

    def test_max_results_boundary_1(self) -> None:
        """max_results=1 is accepted (lower bound)."""
        m = XSearchPostsInput(query="test", max_results=1)
        assert m.max_results == 1

    def test_max_results_boundary_30(self) -> None:
        """max_results=30 is accepted (upper bound)."""
        m = XSearchPostsInput(query="test", max_results=30)
        assert m.max_results == 30


# ===================================================================
# XGetUserPostsInput
# ===================================================================


class TestXGetUserPostsInput:
    """Tests for XGetUserPostsInput model validation."""

    def test_minimal_valid(self) -> None:
        """Constructs with only the required `username` field."""
        m = XGetUserPostsInput(username="elonmusk")
        assert m.username == "elonmusk"
        assert m.max_results == MAX_RESULTS_DEFAULT
        assert m.topic_filter is None
        assert m.from_date is None
        assert m.to_date is None
        assert m.response_format == ResponseFormat.MARKDOWN

    def test_all_fields(self) -> None:
        """Constructs with every field specified."""
        m = XGetUserPostsInput(
            username="OpenAI",
            max_results=20,
            topic_filter="AI",
            from_date="2025-06-01",
            to_date="2025-06-30",
            response_format="json",
        )
        assert m.username == "OpenAI"
        assert m.max_results == 20
        assert m.topic_filter == "AI"

    def test_username_empty_rejected(self) -> None:
        """Empty username violates min_length=1."""
        with pytest.raises(ValidationError, match="username"):
            XGetUserPostsInput(username="")

    def test_username_too_long_rejected(self) -> None:
        """Username over 50 chars violates max_length."""
        with pytest.raises(ValidationError, match="username"):
            XGetUserPostsInput(username="u" * 51)

    def test_extra_field_rejected(self) -> None:
        """Unknown fields are rejected."""
        with pytest.raises(ValidationError, match="unknown"):
            XGetUserPostsInput(username="test", unknown="bad")

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from username."""
        m = XGetUserPostsInput(username="  user  ")
        assert m.username == "user"

    def test_max_results_boundary_1(self) -> None:
        """max_results=1 is accepted (lower bound)."""
        m = XGetUserPostsInput(username="test", max_results=1)
        assert m.max_results == 1

    def test_max_results_boundary_30(self) -> None:
        """max_results=30 is accepted (upper bound)."""
        m = XGetUserPostsInput(username="test", max_results=30)
        assert m.max_results == 30

    def test_max_results_zero_rejected(self) -> None:
        """max_results=0 violates ge=1."""
        with pytest.raises(ValidationError, match="max_results"):
            XGetUserPostsInput(username="test", max_results=0)

    def test_max_results_too_large_rejected(self) -> None:
        """max_results=31 violates le=30."""
        with pytest.raises(ValidationError, match="max_results"):
            XGetUserPostsInput(username="test", max_results=31)


# ===================================================================
# XTrendingInput
# ===================================================================


class TestXTrendingInput:
    """Tests for XTrendingInput model validation."""

    def test_defaults_only(self) -> None:
        """Constructs with no required fields (all optional)."""
        m = XTrendingInput()
        assert m.region is None
        assert m.category is None
        assert m.response_format == ResponseFormat.MARKDOWN

    def test_all_fields(self) -> None:
        """Constructs with every field specified."""
        m = XTrendingInput(
            region="Japan",
            category="technology",
            response_format="json",
        )
        assert m.region == "Japan"
        assert m.category == "technology"
        assert m.response_format == ResponseFormat.JSON

    def test_extra_field_rejected(self) -> None:
        """Unknown fields are rejected."""
        with pytest.raises(ValidationError, match="nope"):
            XTrendingInput(nope="bad")
