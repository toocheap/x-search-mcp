"""Adapter over the `xurl` CLI (the official X API command-line tool).

This module lets the MCP server use the authenticated X API v2 as a data
source, as an alternative to the xAI Grok `x_search` server-side tool. It is
a trimmed, dependency-free port of MOA's xurl_client
(/Users/too/src/my_obsidian_assistant/moa/xurl_client.py): the adapter shells
out to `xurl`, parses the JSON response, classifies API errors, and maps X API
v2 payloads onto a flat ``post`` dict that the MCP tools format for output.

Security:
- Never pass -v/--verbose to xurl (it leaks auth headers/tokens).
- Never read or log ~/.xurl or any token material.
- Auth setup (`xurl auth apps add` / `xurl auth oauth2`) is the user's
  responsibility, performed outside the agent session.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

# Runner contract: (argv, timeout) -> (returncode, stdout, stderr).
# Injectable so tests can supply a fake without spawning a real process.
Runner = Callable[[list[str], float], tuple[int, str, str]]

DEFAULT_BIN = "xurl"
DEFAULT_TIMEOUT = 30.0

# Retry transient rate-limit (HTTP 429) responses with exponential backoff.
DEFAULT_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0  # seconds; wait = base * 2**attempt

# Fields requested for read/search so we can populate the post dict with
# author, timestamps, and engagement metrics.
_TWEET_FIELDS = (
    "created_at,author_id,public_metrics,conversation_id,"
    "in_reply_to_user_id,text"
)
_EXPANSIONS = "author_id"
_USER_FIELDS = "username,name"

# X tweet/user IDs are numeric snowflakes. Validate before interpolating into
# an endpoint path so a crafted value cannot change the endpoint/query.
_ID_RE = re.compile(r"^\d+$")

# X usernames: 1-15 chars, alphanumeric + underscore (a leading @ is stripped
# by the caller). Validated before interpolation into the by-username path.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class XurlError(RuntimeError):
    """Base error for xurl invocation failures."""


class XurlAuthError(XurlError):
    """Authentication failure (not authenticated, HTTP 401/403)."""


class XurlQuotaError(XurlError):
    """Quota / payment failure (HTTP 402). Not retryable."""


class XurlRateLimitError(XurlQuotaError):
    """Rate limited (HTTP 429). Transient — retried with backoff.

    Subclasses XurlQuotaError so existing `except XurlQuotaError` handlers
    continue to treat it as a quota-class failure.
    """


class XurlNotFoundError(XurlError):
    """The tweet/resource does not exist (HTTP 404 / resource-not-found).

    Permanent — not retryable.
    """


def _default_runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
    """Run xurl as a subprocess. Raises XurlError on spawn failure/timeout."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise XurlError(f"xurl binary not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise XurlError(f"xurl timed out after {timeout}s") from exc
    return proc.returncode, proc.stdout, proc.stderr


def _validate_id(value: str, kind: str) -> str:
    """Return value if it is a numeric X id, else raise XurlError."""
    if not _ID_RE.match(value or ""):
        raise XurlError(f"invalid {kind}: {value!r} (expected a numeric id)")
    return value


def _validate_username(value: str) -> str:
    """Return a bare username if valid, else raise XurlError.

    Strips a single leading '@'. Prevents a crafted handle from altering the
    endpoint path/query when interpolated into the by-username route.
    """
    candidate = value or ""
    if candidate.startswith("@"):
        candidate = candidate[1:]
    if not _USERNAME_RE.match(candidate):
        raise XurlError(
            f"invalid username: {value!r} "
            f"(expected 1-15 chars of letters, digits, or underscore)"
        )
    return candidate


def _raise_for_status(status: int, context: str) -> None:
    """Raise the appropriate XurlError subclass for an HTTP-like status."""
    if status in (401, 403):
        raise XurlAuthError(f"xurl auth error (HTTP {status}{context})")
    if status == 404:
        raise XurlNotFoundError(f"xurl resource not found (HTTP 404{context})")
    if status == 429:
        raise XurlRateLimitError(f"xurl rate limited (HTTP 429{context})")
    if status == 402:
        raise XurlQuotaError(f"xurl quota error (HTTP 402{context})")
    raise XurlError(f"xurl request failed (HTTP {status}{context})")


def _raise_for_errors(returncode: int, data: dict[str, Any], stderr: str) -> None:
    """Inspect a parsed xurl response and raise on API/CLI errors.

    X API v2 surfaces errors either as a top-level problem object with a
    numeric "status", an "errors" list (whose items may also carry a status),
    or an OAuth-style "error" string.
    """
    status = data.get("status")
    if isinstance(status, int) and status >= 400:
        _raise_for_status(status, "")

    errors = data.get("errors")
    if errors:
        # If the main payload came back, the errors describe partial expansions
        # (e.g., a referenced tweet/media that is gone) — not a failure of the
        # requested resource. Use the payload rather than raising.
        if data.get("data"):
            return
        # Classify by an embedded status when present so auth/quota failures
        # nested under "errors" still drive fallback decisions.
        if isinstance(errors, list):
            for err in errors:
                if isinstance(err, dict):
                    es = err.get("status")
                    if isinstance(es, int) and es >= 400:
                        _raise_for_status(es, " in errors")
            # resource-not-found is returned with HTTP 200 and no numeric
            # status, so detect it by problem type/title.
            if any(
                isinstance(e, dict)
                and (
                    "resource-not-found" in str(e.get("type", ""))
                    or e.get("title") == "Not Found Error"
                )
                for e in errors
            ):
                raise XurlNotFoundError(f"xurl resource not found: {errors}")
        raise XurlError(f"xurl API error: {errors}")

    if data.get("error"):
        # OAuth-style failure (e.g. unauthorized_client). Do not log details
        # that might carry sensitive context beyond the error code.
        raise XurlAuthError(f"xurl auth error: {data.get('error')}")

    if returncode != 0:
        # No structured error body — surface stderr (xurl does not print tokens
        # to stderr unless -v is used, which we never pass).
        raise XurlError(f"xurl exited {returncode}: {stderr.strip()[:200]}")


def _run_json(
    args: list[str],
    *,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Invoke xurl and return the parsed JSON response.

    Retries on HTTP 429 (rate limit) up to max_retries with exponential
    backoff. Other errors (auth, 402 quota, malformed output) are not retried.
    """
    run = runner or _default_runner
    argv = [bin, *args]
    attempt = 0
    while True:
        returncode, stdout, stderr = run(argv, timeout)

        data: dict[str, Any] = {}
        text = (stdout or "").strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError as exc:
                raise XurlError(
                    f"xurl returned non-JSON output (exit {returncode})"
                ) from exc

        try:
            _raise_for_errors(returncode, data, stderr)
        except XurlRateLimitError:
            if attempt >= max_retries:
                raise
            _sleep(_RETRY_BACKOFF_BASE * (2 ** attempt))
            attempt += 1
            continue
        return data


def available(
    *,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Return True if xurl is installed and has a usable oauth2 credential.

    Uses `xurl auth status` only (the documented, no-cost way to verify
    credentials) — never reads ~/.xurl or issues a billed request.
    """
    run = runner or _default_runner
    if runner is None and shutil.which(bin) is None:
        return False
    try:
        returncode, stdout, stderr = run([bin, "auth", "status"], timeout)
    except XurlError:
        return False
    if returncode != 0:
        return False
    text = f"{stdout or ''}\n{stderr or ''}"
    if "No apps registered" in text:
        return False
    # Require at least one "oauth2: <username>" binding whose value is not
    # "(none)" / empty (the built-in default app has no credentials).
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("oauth2:"):
            value = stripped[len("oauth2:"):].strip()
            if value and value != "(none)":
                return True
    return False


def whoami(
    *,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Return the authenticated user (/2/users/me)."""
    return _run_json(["/2/users/me"], runner=runner, bin=bin, timeout=timeout)


def _rfc3339(date_str: Optional[str], *, end_of_day: bool = False) -> Optional[str]:
    """Convert a YYYY-MM-DD date to an RFC3339 timestamp the X API accepts.

    The X API search/timeline endpoints want start_time/end_time as RFC3339
    (e.g. 2025-01-01T00:00:00Z). A bare date is widened to the day's start, or
    its last second when end_of_day is set, so to_date is inclusive.
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise XurlError(
            f"invalid date: {date_str!r} (expected YYYY-MM-DD)"
        ) from exc
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def search_recent(
    query: str,
    *,
    max_results: int = 10,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search recent posts (/2/tweets/search/recent). Returns raw API JSON.

    The X API requires max_results in [10, 100]; callers asking for fewer get
    10 and the tool trims afterward.
    """
    mr = max(10, min(max_results, 100))
    parts = [
        "/2/tweets/search/recent",
        f"?query={quote(query, safe='')}",
        f"&max_results={mr}",
        f"&tweet.fields={_TWEET_FIELDS}",
        f"&expansions={_EXPANSIONS}",
        f"&user.fields={_USER_FIELDS}",
    ]
    start = _rfc3339(from_date)
    end = _rfc3339(to_date, end_of_day=True)
    if start:
        parts.append(f"&start_time={start}")
    if end:
        parts.append(f"&end_time={end}")
    return _run_json(["".join(parts)], runner=runner, bin=bin, timeout=timeout)


def get_user_by_username(
    username: str,
    *,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Resolve a username to its numeric user id (/2/users/by/username/:u)."""
    handle = _validate_username(username)
    data = _run_json(
        [f"/2/users/by/username/{handle}"],
        runner=runner,
        bin=bin,
        timeout=timeout,
    )
    user_id = (data.get("data") or {}).get("id")
    if not user_id:
        raise XurlNotFoundError(f"user not found: @{handle}")
    return str(user_id)


def get_user_tweets(
    user_id: str,
    *,
    max_results: int = 10,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    runner: Optional[Runner] = None,
    bin: str = DEFAULT_BIN,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch a user's recent tweets (/2/users/:id/tweets). Raw API JSON."""
    _validate_id(user_id, "user_id")
    mr = max(5, min(max_results, 100))
    parts = [
        f"/2/users/{user_id}/tweets",
        f"?max_results={mr}",
        f"&tweet.fields={_TWEET_FIELDS}",
        f"&expansions={_EXPANSIONS}",
        f"&user.fields={_USER_FIELDS}",
    ]
    start = _rfc3339(from_date)
    end = _rfc3339(to_date, end_of_day=True)
    if start:
        parts.append(f"&start_time={start}")
    if end:
        parts.append(f"&end_time={end}")
    return _run_json(["".join(parts)], runner=runner, bin=bin, timeout=timeout)


def _normalize_created_at(raw: Optional[str]) -> Optional[str]:
    """Normalize an X API timestamp to an ISO string with +00:00 offset."""
    if not raw:
        return None
    candidate = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def tweet_json_to_post(
    data: dict[str, Any],
    users: dict[str, dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Convert one /2/tweets data object to a flat post dict.

    ``users`` maps author_id -> user object (from response ``includes.users``).
    Returns None when the payload lacks a tweet id.
    """
    if not data or "id" not in data:
        return None
    author = users.get(data.get("author_id"), {})
    metrics = data.get("public_metrics") or {}
    username = author.get("username", "")
    tweet_id = str(data["id"])
    url = (
        f"https://x.com/{username}/status/{tweet_id}"
        if username
        else f"https://x.com/i/status/{tweet_id}"
    )
    return {
        "id": tweet_id,
        "author_name": author.get("name", ""),
        "username": username,
        "text": data.get("text", ""),
        "created_at": _normalize_created_at(data.get("created_at")),
        "likes": int(metrics.get("like_count", 0) or 0),
        "retweets": int(metrics.get("retweet_count", 0) or 0),
        "replies": int(metrics.get("reply_count", 0) or 0),
        "quotes": int(metrics.get("quote_count", 0) or 0),
        "views": int(metrics.get("impression_count", 0) or 0),
        "url": url,
    }


def posts_from_response(
    response: dict[str, Any],
    *,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Map a search/timeline response (data + includes) to post dicts.

    Trims to ``limit`` when given (the X API floors max_results at 5/10, so a
    caller asking for fewer needs a post-hoc trim).
    """
    raw = response.get("data") or []
    includes = response.get("includes") or {}
    users = {
        u.get("id"): u
        for u in (includes.get("users") or [])
        if isinstance(u, dict)
    }
    posts: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            post = tweet_json_to_post(item, users)
            if post is not None:
                posts.append(post)
    if limit is not None:
        posts = posts[:limit]
    return posts


def format_posts(posts: list[dict[str, Any]], *, as_json: bool = False) -> str:
    """Render post dicts as markdown or a JSON string."""
    if as_json:
        return json.dumps(posts, indent=2, ensure_ascii=False)
    if not posts:
        return "No posts found."
    blocks: list[str] = []
    for p in posts:
        handle = f"@{p['username']}" if p.get("username") else "@unknown"
        name = p.get("author_name") or ""
        header = f"**{name}** ({handle})" if name else f"**{handle}**"
        when = p.get("created_at") or ""
        meta = (
            f"❤ {p.get('likes', 0)} · 🔁 {p.get('retweets', 0)} · "
            f"💬 {p.get('replies', 0)}"
        )
        lines = [
            f"### {header}",
            p.get("text", ""),
            "",
            f"{when}  ·  {meta}",
            p.get("url", ""),
        ]
        blocks.append("\n".join(line for line in lines if line is not None))
    return "\n\n---\n\n".join(blocks)
