"""Tests for the optional Xquik backend adapter."""

import json

import httpx
import xquik_client


def test_available_uses_key_presence(monkeypatch):
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    assert xquik_client.available() is False

    monkeypatch.setenv("XQUIK_API_KEY", "xquik-test-key")
    assert xquik_client.available() is True


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("XQUIK_BASE_URL", "https://example.test/api/v1/")
    assert xquik_client.base_url() == "https://example.test/api/v1"


def test_get_sends_api_key_header(monkeypatch):
    captured: dict = {}

    class CapturingClient:
        def __init__(self, *, timeout, headers):
            captured["timeout"] = timeout
            captured["headers"] = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, *, params):
            captured["url"] = url
            captured["params"] = params
            request = httpx.Request("GET", url)
            return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setenv("XQUIK_API_KEY", "xquik-test-key")
    monkeypatch.setenv("XQUIK_BASE_URL", "https://example.test/api/v1")
    monkeypatch.setattr(xquik_client.httpx, "Client", CapturingClient)

    response = xquik_client._get("/trends", params={"count": 1})

    assert response == {"ok": True}
    assert captured["headers"]["x-api-key"] == "xquik-test-key"
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["url"] == "https://example.test/api/v1/trends"
    assert captured["params"] == {"count": 1}


def test_iso_boundary_converts_dates_to_utc_boundaries():
    assert xquik_client._iso_boundary("2026-06-06") == "2026-06-06T00:00:00Z"
    assert (
        xquik_client._iso_boundary("2026-06-06", end_of_day=True)
        == "2026-06-06T23:59:59.999999Z"
    )


def test_posts_from_response_normalizes_tweets():
    payload = {
        "tweets": [
            {
                "id": "123",
                "text": "hello",
                "createdAt": "2026-06-06T12:00:00Z",
                "author": {"username": "alice", "name": "Alice"},
                "likeCount": 3,
                "retweetCount": 2,
                "replyCount": 1,
                "quoteCount": 0,
                "viewCount": 10,
            }
        ]
    }

    posts = xquik_client.posts_from_response(payload, limit=10)
    assert posts == [
        {
            "id": "123",
            "author_name": "Alice",
            "username": "alice",
            "text": "hello",
            "created_at": "2026-06-06T12:00:00Z",
            "likes": 3,
            "retweets": 2,
            "replies": 1,
            "quotes": 0,
            "views": 10,
            "url": "https://x.com/i/status/123",
        }
    ]


def test_format_trends_markdown_and_json():
    payload = {
        "trends": [
            {"name": "#AI", "description": "models", "rank": 1},
        ]
    }

    markdown = xquik_client.format_trends(payload)
    assert "# X Trends" in markdown
    assert "1. #AI - models" in markdown

    parsed = json.loads(xquik_client.format_trends(payload, as_json=True))
    assert parsed[0]["name"] == "#AI"
