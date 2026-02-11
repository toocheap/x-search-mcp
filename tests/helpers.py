"""Reusable test utilities for x_search_mcp tests.

Provides response builders and transport factories using httpx.MockTransport.
Separated from conftest.py so that test modules can import these directly.
"""

import json
from typing import Any, Callable, Optional

import httpx


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def make_response_data(
    text: str = "Sample response text",
    *,
    output_type: str = "message",
) -> dict[str, Any]:
    """Build a realistic xAI Responses API JSON body.

    Args:
        text: The text content to include in the response.
        output_type: Either "message" (standard) or "text" (direct text item).
    """
    if output_type == "message":
        return {
            "id": "resp_test123",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text},
                    ],
                }
            ],
        }
    # Direct text item variant
    return {
        "id": "resp_test123",
        "output": [
            {"text": text},
        ],
    }


def make_empty_response_data() -> dict[str, Any]:
    """Build a response with no extractable text (triggers JSON fallback)."""
    return {
        "id": "resp_test_empty",
        "output": [],
    }


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------

def fake_transport(
    status_code: int = 200,
    json_body: Optional[dict] = None,
    *,
    handler: Optional[Callable] = None,
) -> httpx.MockTransport:
    """Create an httpx.MockTransport that returns a fixed response.

    Args:
        status_code: HTTP status code to return.
        json_body: JSON body to return.  Defaults to a standard message response.
        handler: If provided, overrides the default behaviour.  The callable
            receives an ``httpx.Request`` and must return an ``httpx.Response``.
    """
    if handler is not None:
        return httpx.MockTransport(handler)

    body = json_body if json_body is not None else make_response_data()

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=body,
            request=request,
        )

    return httpx.MockTransport(_handler)


def capture_transport(
    json_body: Optional[dict] = None,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Create a transport that captures requests for later inspection.

    Returns:
        A tuple of (transport, captured_requests_list).
    """
    body = json_body if json_body is not None else make_response_data()
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=body, request=request)

    return httpx.MockTransport(_handler), captured
