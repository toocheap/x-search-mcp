"""Tests for the optional Xquik backend adapter."""

import json

import xquik_client


def test_available_uses_key_presence(monkeypatch):
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    assert xquik_client.available() is False

    monkeypatch.setenv("XQUIK_API_KEY", "xquik-test-key")
    assert xquik_client.available() is True


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("XQUIK_BASE_URL", "https://example.test/api/v1/")
    assert xquik_client.base_url() == "https://example.test/api/v1"


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
