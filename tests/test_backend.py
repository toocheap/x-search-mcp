"""Tests for backend selection and the xurl routing path in x_search_mcp.

The tool functions delegate to xurl_client's module-level functions, which we
replace via monkeypatch.setattr with small fakes. Reason for monkeypatch:
these tests verify routing and fallback logic (which backend runs, what
happens on xurl failure) — not subprocess mechanics, which test_xurl_client.py
covers via the injectable Runner. Replacing the high-level xurl_client
functions is the minimal intervention to isolate routing, per project policy.
"""

import json

import pytest

import x_search_mcp
import xurl_client
from x_search_mcp import (
    ResponseFormat,
    XGetUserPostsInput,
    XSearchPostsInput,
    _get_backend,
    _handle_xurl_error,
    _should_use_xurl,
    x_auth_status,
    x_get_user_posts,
    x_search_posts,
)


SEARCH_PAYLOAD = {
    "data": [
        {
            "id": "1001",
            "text": "hello grok world",
            "author_id": "42",
            "created_at": "2026-05-29T16:32:46.000Z",
            "public_metrics": {"like_count": 5, "retweet_count": 2, "reply_count": 1},
        }
    ],
    "includes": {"users": [{"id": "42", "username": "alice", "name": "Alice"}]},
}


# ===================================================================
# _get_backend
# ===================================================================


class TestGetBackend:
    def test_default_is_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("X_SEARCH_BACKEND", raising=False)
        assert _get_backend() == "auto"

    @pytest.mark.parametrize("val", ["auto", "xurl", "xai"])
    def test_valid_values(self, monkeypatch: pytest.MonkeyPatch, val) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", val)
        assert _get_backend() == val

    def test_unknown_falls_back_to_auto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "bogus")
        assert _get_backend() == "auto"

    def test_case_and_whitespace_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "  XURL  ")
        assert _get_backend() == "xurl"


# ===================================================================
# _should_use_xurl
# ===================================================================


class TestShouldUseXurl:
    def test_forced_xurl(self) -> None:
        assert _should_use_xurl("xurl") is True

    def test_forced_xai(self) -> None:
        assert _should_use_xurl("xai") is False

    def test_auto_delegates_to_available_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(xurl_client, "available", lambda: True)
        assert _should_use_xurl("auto") is True

    def test_auto_delegates_to_available_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(xurl_client, "available", lambda: False)
        assert _should_use_xurl("auto") is False


# ===================================================================
# _handle_xurl_error
# ===================================================================


class TestHandleXurlError:
    def test_auth_error(self) -> None:
        out = json.loads(_handle_xurl_error(xurl_client.XurlAuthError("x")))
        assert out["source"] == "xurl"
        assert "not authenticated" in out["error"]

    def test_rate_limit(self) -> None:
        out = json.loads(_handle_xurl_error(xurl_client.XurlRateLimitError("x")))
        assert "429" in out["error"]

    def test_quota(self) -> None:
        out = json.loads(_handle_xurl_error(xurl_client.XurlQuotaError("x")))
        assert "402" in out["error"]

    def test_not_found(self) -> None:
        out = json.loads(
            _handle_xurl_error(xurl_client.XurlNotFoundError("no such tweet"))
        )
        assert out["error"] == "no such tweet"

    def test_generic(self) -> None:
        out = json.loads(_handle_xurl_error(xurl_client.XurlError("boom")))
        assert out["error"] == "boom"


# ===================================================================
# x_search_posts via xurl
# ===================================================================


class TestSearchPostsXurl:
    @pytest.fixture()
    def force_xurl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "xurl")

    async def test_routes_to_xurl_markdown(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_search(query, **kwargs):
            captured["query"] = query
            captured["kwargs"] = kwargs
            return SEARCH_PAYLOAD

        # If the xAI path were taken, this would error the test loudly.
        async def boom(*a, **k):
            raise AssertionError("xAI path must not run when backend=xurl")

        monkeypatch.setattr(xurl_client, "search_recent", fake_search)
        monkeypatch.setattr(x_search_mcp, "_call_responses_api", boom)

        params = XSearchPostsInput(query="grok", language="ja", max_results=5)
        out = await x_search_posts(params)

        assert "hello grok world" in out
        assert "@alice" in out
        assert captured["query"] == "grok lang:ja"  # language operator appended
        assert captured["kwargs"]["max_results"] == 5

    async def test_routes_to_xurl_json(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            xurl_client, "search_recent", lambda q, **k: SEARCH_PAYLOAD
        )
        params = XSearchPostsInput(query="grok", response_format=ResponseFormat.JSON)
        out = await x_search_posts(params)
        parsed = json.loads(out)
        assert parsed[0]["id"] == "1001"

    async def test_xurl_error_returns_formatted_error(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(q, **k):
            raise xurl_client.XurlAuthError("nope")

        monkeypatch.setattr(xurl_client, "search_recent", fail)
        out = await x_search_posts(XSearchPostsInput(query="grok"))
        assert json.loads(out)["source"] == "xurl"

    async def test_auto_falls_back_to_xai_on_xurl_error(
        self, monkeypatch: pytest.MonkeyPatch, fake_api_key: str
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "auto")
        monkeypatch.setattr(xurl_client, "available", lambda: True)

        def fail(q, **k):
            raise xurl_client.XurlError("transient")

        async def fake_xai(prompt, *, x_search_config=None):
            return "XAI-FALLBACK-RESULT"

        monkeypatch.setattr(xurl_client, "search_recent", fail)
        monkeypatch.setattr(x_search_mcp, "_call_responses_api", fake_xai)

        out = await x_search_posts(XSearchPostsInput(query="grok"))
        assert out == "XAI-FALLBACK-RESULT"


# ===================================================================
# x_get_user_posts via xurl
# ===================================================================


class TestUserPostsXurl:
    @pytest.fixture()
    def force_xurl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "xurl")

    async def test_resolves_username_and_fetches(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict = {}

        def fake_by_username(username, **k):
            seen["username"] = username
            return "42"

        def fake_tweets(user_id, **k):
            seen["user_id"] = user_id
            return SEARCH_PAYLOAD

        monkeypatch.setattr(xurl_client, "get_user_by_username", fake_by_username)
        monkeypatch.setattr(xurl_client, "get_user_tweets", fake_tweets)

        out = await x_get_user_posts(XGetUserPostsInput(username="alice"))
        assert seen["username"] == "alice"
        assert seen["user_id"] == "42"
        assert "hello grok world" in out

    async def test_topic_filter_applied_client_side(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(xurl_client, "get_user_by_username", lambda u, **k: "42")
        monkeypatch.setattr(xurl_client, "get_user_tweets", lambda i, **k: SEARCH_PAYLOAD)

        # "nomatch" is absent from the only post -> filtered out -> empty.
        out = await x_get_user_posts(
            XGetUserPostsInput(username="alice", topic_filter="nomatch")
        )
        assert out == "No posts found."

        # "grok" is present -> kept.
        out2 = await x_get_user_posts(
            XGetUserPostsInput(username="alice", topic_filter="grok")
        )
        assert "hello grok world" in out2

    async def test_user_not_found_error(
        self, force_xurl, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(u, **k):
            raise xurl_client.XurlNotFoundError("user not found: @ghost")

        monkeypatch.setattr(xurl_client, "get_user_by_username", fail)
        out = await x_get_user_posts(XGetUserPostsInput(username="ghost"))
        assert json.loads(out)["source"] == "xurl"


# ===================================================================
# x_auth_status
# ===================================================================


class TestAuthStatus:
    async def test_auto_with_xurl_available(
        self, monkeypatch: pytest.MonkeyPatch, fake_api_key: str
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "auto")
        monkeypatch.setattr(xurl_client, "available", lambda: True)
        out = json.loads(await x_auth_status())
        assert out["configured_backend"] == "auto"
        assert out["effective_backend"] == "xurl"
        assert out["xurl_available"] is True
        assert out["xai_key_present"] is True

    async def test_auto_without_xurl_uses_xai(
        self, monkeypatch: pytest.MonkeyPatch, clear_api_key: None
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "auto")
        monkeypatch.setattr(xurl_client, "available", lambda: False)
        out = json.loads(await x_auth_status())
        assert out["effective_backend"] == "xai"
        assert out["xurl_available"] is False
        assert out["xai_key_present"] is False

    async def test_forced_xurl_effective(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "xurl")
        monkeypatch.setattr(xurl_client, "available", lambda: False)
        out = json.loads(await x_auth_status())
        assert out["effective_backend"] == "xurl"

    async def test_forced_xai_effective(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X_SEARCH_BACKEND", "xai")
        monkeypatch.setattr(xurl_client, "available", lambda: True)
        out = json.loads(await x_auth_status())
        assert out["effective_backend"] == "xai"
