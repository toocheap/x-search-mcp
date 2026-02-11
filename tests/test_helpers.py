"""Tests for helper functions in x_search_mcp.

Tests _get_api_key, _build_x_search_config, _handle_api_error, and
_call_responses_api.  HTTP calls use httpx.MockTransport (transport-level
fake) rather than unittest.mock.
"""

import json

import httpx
import pytest

from x_search_mcp import (
    _build_x_search_config,
    _call_responses_api,
    _get_api_key,
    _handle_api_error,
)
from tests.helpers import (
    capture_transport,
    fake_transport,
    make_empty_response_data,
    make_response_data,
)


# ===================================================================
# _get_api_key
# ===================================================================


class TestGetApiKey:
    """Tests for _get_api_key()."""

    def test_returns_key_when_set(self, fake_api_key: str) -> None:
        """API key is returned when the env var is set."""
        assert _get_api_key() == fake_api_key

    def test_raises_when_not_set(self, clear_api_key: None) -> None:
        """RuntimeError is raised when XAI_API_KEY is missing."""
        with pytest.raises(RuntimeError, match="XAI_API_KEY"):
            _get_api_key()

    def test_raises_when_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError is raised when XAI_API_KEY is an empty string."""
        monkeypatch.setenv("XAI_API_KEY", "")
        with pytest.raises(RuntimeError, match="XAI_API_KEY"):
            _get_api_key()


# ===================================================================
# _build_x_search_config
# ===================================================================


class TestBuildXSearchConfig:
    """Tests for _build_x_search_config()."""

    def test_returns_none_when_no_params(self) -> None:
        """Returns None when nothing is provided."""
        assert _build_x_search_config() is None

    def test_from_date_only(self) -> None:
        """Includes from_date when specified."""
        result = _build_x_search_config(from_date="2025-01-01")
        assert result == {"from_date": "2025-01-01"}

    def test_to_date_only(self) -> None:
        """Includes to_date when specified."""
        result = _build_x_search_config(to_date="2025-12-31")
        assert result == {"to_date": "2025-12-31"}

    def test_allowed_handles(self) -> None:
        """Includes allowed_x_handles when specified."""
        result = _build_x_search_config(allowed_handles=["elonmusk"])
        assert result == {"allowed_x_handles": ["elonmusk"]}

    def test_excluded_handles(self) -> None:
        """Includes excluded_x_handles when specified."""
        result = _build_x_search_config(excluded_handles=["spambot"])
        assert result == {"excluded_x_handles": ["spambot"]}

    def test_all_params(self) -> None:
        """All params are included when specified."""
        result = _build_x_search_config(
            from_date="2025-01-01",
            to_date="2025-12-31",
            allowed_handles=["user1", "user2"],
            excluded_handles=["spam"],
        )
        assert result == {
            "from_date": "2025-01-01",
            "to_date": "2025-12-31",
            "allowed_x_handles": ["user1", "user2"],
            "excluded_x_handles": ["spam"],
        }


# ===================================================================
# _handle_api_error
# ===================================================================


class TestHandleApiError:
    """Tests for _handle_api_error()."""

    @staticmethod
    def _make_http_error(
        status_code: int,
        json_body: dict | None = None,
        text_body: str = "",
    ) -> httpx.HTTPStatusError:
        """Create a real httpx.HTTPStatusError with the given status code."""
        request = httpx.Request("POST", "https://api.x.ai/v1/responses")
        if json_body is not None:
            response = httpx.Response(
                status_code,
                json=json_body,
                request=request,
            )
        else:
            response = httpx.Response(
                status_code,
                text=text_body,
                request=request,
            )
        return httpx.HTTPStatusError(
            message=f"status {status_code}",
            request=request,
            response=response,
        )

    def test_401_error(self) -> None:
        """401 returns auth failure message."""
        err = self._make_http_error(401)
        result = json.loads(_handle_api_error(err))
        assert result["status"] == 401
        assert "Authentication" in result["error"]

    def test_429_error(self) -> None:
        """429 returns rate limit message."""
        err = self._make_http_error(429)
        result = json.loads(_handle_api_error(err))
        assert result["status"] == 429
        assert "Rate limit" in result["error"]

    def test_other_http_error_with_json_detail(self) -> None:
        """Other HTTP errors include parsed JSON detail."""
        err = self._make_http_error(500, json_body={"message": "server broke"})
        result = json.loads(_handle_api_error(err))
        assert "500" in result["error"]
        assert "server broke" in result["detail"]

    def test_other_http_error_with_text_fallback(self) -> None:
        """When response JSON parsing fails, text body is used as detail."""
        err = self._make_http_error(502, text_body="Bad Gateway")
        result = json.loads(_handle_api_error(err))
        assert "502" in result["error"]
        assert "Bad Gateway" in result["detail"]

    def test_timeout_error(self) -> None:
        """TimeoutException returns timeout message."""
        err = httpx.TimeoutException("timed out")
        result = json.loads(_handle_api_error(err))
        assert "timed out" in result["error"].lower()

    def test_runtime_error(self) -> None:
        """RuntimeError message is preserved."""
        err = RuntimeError("XAI_API_KEY environment variable is not set.")
        result = json.loads(_handle_api_error(err))
        assert "XAI_API_KEY" in result["error"]

    def test_unexpected_error(self) -> None:
        """Unknown exception types include type name and message."""
        err = ValueError("something weird")
        result = json.loads(_handle_api_error(err))
        assert "ValueError" in result["error"]
        assert "something weird" in result["error"]


# ===================================================================
# _call_responses_api
# ===================================================================


class TestCallResponsesApi:
    """Tests for _call_responses_api().

    Uses httpx.MockTransport to intercept HTTP calls at the transport
    level.  monkeypatch replaces httpx.AsyncClient so that our fake
    transport is injected without mock objects.
    """

    def _patch_client(
        self,
        monkeypatch: pytest.MonkeyPatch,
        transport: httpx.MockTransport,
    ) -> None:
        """Replace httpx.AsyncClient with one using the given transport.

        Reason for monkeypatch: _call_responses_api creates its own
        AsyncClient internally, so we need to intercept the constructor
        to inject our transport.  This is the minimal intervention needed
        and is documented here per project policy.
        """
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client: httpx.AsyncClient, **kwargs: object) -> None:
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    async def test_message_type_response(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extracts text from message-type output items."""
        data = make_response_data("Hello from Grok", output_type="message")
        self._patch_client(monkeypatch, fake_transport(json_body=data))

        result = await _call_responses_api("test query")
        assert result == "Hello from Grok"

    async def test_text_type_response(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extracts text from direct text-type output items."""
        data = make_response_data("Direct text", output_type="text")
        self._patch_client(monkeypatch, fake_transport(json_body=data))

        result = await _call_responses_api("test query")
        assert result == "Direct text"

    async def test_empty_output_returns_json_fallback(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When output has no extractable text, raw JSON is returned."""
        data = make_empty_response_data()
        self._patch_client(monkeypatch, fake_transport(json_body=data))

        result = await _call_responses_api("test query")
        parsed = json.loads(result)
        assert parsed["id"] == "resp_test_empty"

    async def test_request_body_without_config(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Request body has basic x_search tool when no config is given."""
        transport, captured = capture_transport()
        self._patch_client(monkeypatch, transport)

        await _call_responses_api("test query")

        assert len(captured) == 1
        body = json.loads(captured[0].content)
        assert body["tools"] == [{"type": "x_search"}]
        assert body["input"][0]["content"] == "test query"

    async def test_request_body_with_config(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """x_search_config params are merged into the tool definition."""
        transport, captured = capture_transport()
        self._patch_client(monkeypatch, transport)

        config = {"from_date": "2025-01-01", "allowed_x_handles": ["user1"]}
        await _call_responses_api("test query", x_search_config=config)

        body = json.loads(captured[0].content)
        tool = body["tools"][0]
        assert tool["type"] == "x_search"
        assert tool["from_date"] == "2025-01-01"
        assert tool["allowed_x_handles"] == ["user1"]

    async def test_http_error_propagates(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HTTPStatusError is raised on non-2xx responses."""
        self._patch_client(
            monkeypatch,
            fake_transport(status_code=500, json_body={"error": "fail"}),
        )

        with pytest.raises(httpx.HTTPStatusError):
            await _call_responses_api("test query")

    async def test_multiple_text_parts_joined(
        self, fake_api_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple text parts in output are joined with newlines."""
        data = {
            "id": "resp_multi",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Part 1"},
                        {"type": "output_text", "text": "Part 2"},
                    ],
                },
            ],
        }
        self._patch_client(monkeypatch, fake_transport(json_body=data))

        result = await _call_responses_api("test query")
        assert result == "Part 1\nPart 2"
