"""Adapter for the Xquik X/Twitter API read backend.

This backend is optional and only sends requests when XQUIK_API_KEY is set or
when X_SEARCH_BACKEND=xquik is explicitly selected. It never logs or returns
the API key value.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "https://xquik.com/api/v1"
DEFAULT_TIMEOUT = 30.0


class XquikError(RuntimeError):
    """Base error for Xquik backend failures."""


class XquikAuthError(XquikError):
    """Authentication failure."""


class XquikQuotaError(XquikError):
    """Quota or payment failure."""


class XquikRateLimitError(XquikQuotaError):
    """Rate limit failure."""


class XquikNotFoundError(XquikError):
    """Resource was not found."""


def available() -> bool:
    """Return True when an Xquik API key is configured."""
    return bool(os.environ.get("XQUIK_API_KEY"))


def base_url() -> str:
    """Return the configured Xquik API base URL without a trailing slash."""
    return os.environ.get("XQUIK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    key = os.environ.get("XQUIK_API_KEY", "")
    if not key:
        raise XquikAuthError(
            "XQUIK_API_KEY is not set. Set it or choose X_SEARCH_BACKEND=xai."
        )
    return key


def _iso_boundary(raw: Optional[str], *, end_of_day: bool = False) -> Optional[str]:
    """Convert YYYY-MM-DD input to an ISO timestamp accepted by Xquik."""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if len(raw) == 10:
        boundary = time.max if end_of_day else time.min
        parsed = datetime.combine(parsed.date(), boundary)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _raise_for_status(exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    if status in (401, 403):
        raise XquikAuthError(f"Xquik auth error (HTTP {status})") from exc
    if status == 404:
        raise XquikNotFoundError("Xquik resource not found") from exc
    if status == 429:
        raise XquikRateLimitError("Xquik rate limited (HTTP 429)") from exc
    if status == 402:
        raise XquikQuotaError("Xquik quota error (HTTP 402)") from exc
    raise XquikError(f"Xquik request failed (HTTP {status})") from exc


def _get(path: str, *, params: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "x-api-key": _api_key(),
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
            response = client.get(f"{base_url()}{path}", params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_status(exc)
    except httpx.TimeoutException as exc:
        raise XquikError("Xquik request timed out") from exc
    except httpx.HTTPError as exc:
        raise XquikError(f"Xquik request failed: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise XquikError("Xquik returned a non-object response")
    return data


def _tweet_to_post(tweet: dict[str, Any]) -> Optional[dict[str, Any]]:
    tweet_id = tweet.get("id")
    if not tweet_id:
        return None
    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    username = author.get("username") or tweet.get("username") or ""
    return {
        "id": str(tweet_id),
        "author_name": author.get("name", ""),
        "username": username,
        "text": tweet.get("text", ""),
        "created_at": tweet.get("createdAt"),
        "likes": int(tweet.get("likeCount", 0) or 0),
        "retweets": int(tweet.get("retweetCount", 0) or 0),
        "replies": int(tweet.get("replyCount", 0) or 0),
        "quotes": int(tweet.get("quoteCount", 0) or 0),
        "views": int(tweet.get("viewCount", 0) or 0),
        "url": tweet.get("url") or f"https://x.com/i/status/{tweet_id}",
    }


def posts_from_response(response: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    """Extract and normalize posts from an Xquik paginated tweet response."""
    raw_tweets = response.get("tweets")
    if raw_tweets is None:
        raw_tweets = response.get("data", [])
    posts: list[dict[str, Any]] = []
    if isinstance(raw_tweets, list):
        for item in raw_tweets:
            if isinstance(item, dict):
                post = _tweet_to_post(item)
                if post is not None:
                    posts.append(post)
    return posts[:limit]


def search_recent(
    query: str,
    *,
    max_results: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict[str, Any]:
    """Search posts with the Xquik tweet search endpoint."""
    params: dict[str, Any] = {
        "q": query,
        "queryType": "Latest",
        "limit": max_results,
    }
    since_time = _iso_boundary(from_date)
    until_time = _iso_boundary(to_date, end_of_day=True)
    if since_time:
        params["sinceTime"] = since_time
    if until_time:
        params["untilTime"] = until_time
    return _get("/x/tweets/search", params=params)


def get_user_tweets(
    username: str,
    *,
    max_results: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch recent posts for a user ID or username."""
    params: dict[str, Any] = {
        "includeReplies": "false",
        "includeParentTweet": "false",
    }
    since_time = _iso_boundary(from_date)
    until_time = _iso_boundary(to_date, end_of_day=True)
    if since_time:
        params["sinceTime"] = since_time
    if until_time:
        params["untilTime"] = until_time
    response = _get(f"/x/users/{username}/tweets", params=params)
    response["tweets"] = response.get("tweets", [])[:max_results]
    return response


def get_trends(*, count: int = 10, woeid: int = 1) -> dict[str, Any]:
    """Fetch current trends from Xquik."""
    return _get("/trends", params={"count": count, "woeid": woeid})


def format_trends(data: dict[str, Any], *, as_json: bool = False) -> str:
    """Render an Xquik trends response as markdown or JSON."""
    trends = data.get("trends") if isinstance(data.get("trends"), list) else []
    if as_json:
        return json.dumps(trends, indent=2, ensure_ascii=False)
    if not trends:
        return "No trends found."
    lines = ["# X Trends"]
    for idx, trend in enumerate(trends, start=1):
        if not isinstance(trend, dict):
            continue
        name = trend.get("name", "")
        description = trend.get("description")
        rank = trend.get("rank") or idx
        line = f"{rank}. {name}"
        if description:
            line = f"{line} - {description}"
        lines.append(line)
    return "\n".join(lines)
