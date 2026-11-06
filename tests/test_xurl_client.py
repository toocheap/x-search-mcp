"""Tests for xurl_client (the official xurl CLI adapter).

No mocks: xurl is invoked through an injectable Runner contract
((argv, timeout) -> (returncode, stdout, stderr)), so tests supply fake
runners that return canned JSON without spawning a subprocess. Sleep during
retry backoff is injected too, so rate-limit retries don't slow tests.
"""

import json
from typing import Any

import pytest

import xurl_client
from xurl_client import (
    DEFAULT_MAX_RETRIES,
    XurlAuthError,
    XurlError,
    XurlNotFoundError,
    XurlQuotaError,
    XurlRateLimitError,
    available,
    format_posts,
    get_user_by_username,
    get_user_tweets,
    posts_from_response,
    search_recent,
    tweet_json_to_post,
    whoami,
)


# ---------------------------------------------------------------------------
# Fake runners
# ---------------------------------------------------------------------------


def make_runner(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """A runner that always returns the given tuple and records its calls."""
    calls: list[tuple[list[str], float]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append((argv, timeout))
        return returncode, stdout, stderr

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def json_runner(body: dict[str, Any], returncode: int = 0):
    """A runner that returns ``body`` serialized as stdout JSON."""
    return make_runner(returncode=returncode, stdout=json.dumps(body))


def sequence_runner(*responses: tuple[int, str, str]):
    """A runner that yields a different tuple on each successive call."""
    state = {"i": 0}
    calls: list[tuple[list[str], float]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append((argv, timeout))
        idx = min(state["i"], len(responses) - 1)
        state["i"] += 1
        return responses[idx]

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------


def search_payload() -> dict[str, Any]:
    return {
        "data": [
            {
                "id": "1001",
                "text": "first post",
                "author_id": "42",
                "created_at": "2026-05-29T16:32:46.000Z",
                "public_metrics": {
                    "like_count": 5,
                    "retweet_count": 2,
                    "reply_count": 1,
                    "quote_count": 0,
                    "impression_count": 100,
                },
            },
            {
                "id": "1002",
                "text": "second post",
                "author_id": "42",
                "created_at": "2026-05-29T17:00:00.000Z",
                "public_metrics": {"like_count": 9},
            },
        ],
        "includes": {
            "users": [
                {"id": "42", "username": "alice", "name": "Alice"},
            ]
        },
    }


# ===================================================================
# _run_json error classification
# ===================================================================


class TestRunJsonErrors:
    def test_success_returns_parsed_dict(self) -> None:
        runner = json_runner({"data": {"id": "1"}})
        out = whoami(runner=runner)
        assert out == {"data": {"id": "1"}}

    def test_non_json_output_raises(self) -> None:
        runner = make_runner(stdout="not json at all")
        with pytest.raises(XurlError, match="non-JSON"):
            whoami(runner=runner)

    def test_non_dict_json_is_ignored_then_nonzero_raises(self) -> None:
        # A JSON list parses but isn't a dict; with a nonzero exit it surfaces
        # the CLI error path.
        runner = make_runner(returncode=1, stdout="[1, 2, 3]", stderr="boom")
        with pytest.raises(XurlError, match="exited 1"):
            whoami(runner=runner)

    @pytest.mark.parametrize(
        "status,exc",
        [
            (401, XurlAuthError),
            (403, XurlAuthError),
            (404, XurlNotFoundError),
            (402, XurlQuotaError),
            (500, XurlError),
        ],
    )
    def test_top_level_status_maps_to_exception(self, status, exc) -> None:
        runner = json_runner({"status": status, "title": "err"})
        with pytest.raises(exc):
            whoami(runner=runner)

    def test_errors_list_with_status_classified(self) -> None:
        runner = json_runner({"errors": [{"status": 403, "title": "Forbidden"}]})
        with pytest.raises(XurlAuthError):
            whoami(runner=runner)

    def test_errors_list_resource_not_found_by_type(self) -> None:
        runner = json_runner(
            {"errors": [{"type": "https://api.x/resource-not-found"}]}
        )
        with pytest.raises(XurlNotFoundError):
            whoami(runner=runner)

    def test_errors_list_not_found_by_title(self) -> None:
        runner = json_runner({"errors": [{"title": "Not Found Error"}]})
        with pytest.raises(XurlNotFoundError):
            whoami(runner=runner)

    def test_errors_with_data_present_is_not_fatal(self) -> None:
        # Partial-expansion errors alongside real data must not raise.
        runner = json_runner(
            {"data": {"id": "1"}, "errors": [{"title": "media gone"}]}
        )
        out = whoami(runner=runner)
        assert out["data"]["id"] == "1"

    def test_generic_errors_list_raises(self) -> None:
        runner = json_runner({"errors": [{"detail": "weird"}]})
        with pytest.raises(XurlError, match="API error"):
            whoami(runner=runner)

    def test_oauth_error_string_raises_auth(self) -> None:
        runner = json_runner({"error": "unauthorized_client"})
        with pytest.raises(XurlAuthError):
            whoami(runner=runner)

    def test_nonzero_exit_no_body_raises_with_stderr(self) -> None:
        runner = make_runner(returncode=2, stdout="", stderr="kaboom")
        with pytest.raises(XurlError, match="kaboom"):
            whoami(runner=runner)


# ===================================================================
# Rate-limit retry behaviour
# ===================================================================


class TestRetry:
    def test_429_retries_then_succeeds(self) -> None:
        body_429 = json.dumps({"status": 429})
        body_ok = json.dumps({"data": {"id": "9"}})
        runner = sequence_runner(
            (0, body_429, ""),
            (0, body_ok, ""),
        )
        slept: list[float] = []
        out = xurl_client._run_json(
            ["/2/users/me"], runner=runner, _sleep=slept.append
        )
        assert out["data"]["id"] == "9"
        assert len(slept) == 1  # one backoff between the two attempts

    def test_429_exhausts_retries_and_raises(self) -> None:
        body_429 = json.dumps({"status": 429})
        runner = make_runner(stdout=body_429)
        slept: list[float] = []
        with pytest.raises(XurlRateLimitError):
            xurl_client._run_json(
                ["/2/users/me"], runner=runner, _sleep=slept.append
            )
        # DEFAULT_MAX_RETRIES backoffs, then the final attempt raises.
        assert len(slept) == DEFAULT_MAX_RETRIES


# ===================================================================
# available()
# ===================================================================


class TestAvailable:
    def test_true_when_oauth2_bound(self) -> None:
        status = "▸ my-app\n      oauth2: toocheap\n"
        assert available(runner=make_runner(stdout=status)) is True

    def test_false_when_oauth2_none(self) -> None:
        status = "default\n      oauth2: (none)\n"
        assert available(runner=make_runner(stdout=status)) is False

    def test_false_on_no_apps(self) -> None:
        runner = make_runner(stdout="No apps registered")
        assert available(runner=runner) is False

    def test_false_on_nonzero_exit(self) -> None:
        runner = make_runner(returncode=1, stdout="oauth2: someone")
        assert available(runner=runner) is False

    def test_false_when_runner_raises(self) -> None:
        def boom(argv: list[str], timeout: float):
            raise XurlError("spawn failed")

        assert available(runner=boom) is False

    def test_reads_status_from_stderr_too(self) -> None:
        runner = make_runner(stdout="", stderr="oauth2: bob")
        assert available(runner=runner) is True

    def test_false_when_binary_missing_and_no_runner(self) -> None:
        # No runner injected -> the real shutil.which lookup runs; a bogus
        # binary name is guaranteed absent, so available() returns False
        # without spawning anything.
        assert available(bin="xurl-does-not-exist-zzz") is False


# ===================================================================
# _default_runner (the real subprocess path)
# ===================================================================


class TestDefaultRunner:
    def test_success_runs_real_command(self) -> None:
        # `true` exits 0 with no output; a portable, side-effect-free command.
        rc, out, err = xurl_client._default_runner(["true"], 5.0)
        assert rc == 0

    def test_nonzero_exit(self) -> None:
        rc, out, err = xurl_client._default_runner(["false"], 5.0)
        assert rc != 0

    def test_missing_binary_raises(self) -> None:
        with pytest.raises(XurlError, match="not found"):
            xurl_client._default_runner(["xurl-missing-binary-zzz"], 5.0)

    def test_timeout_raises(self) -> None:
        with pytest.raises(XurlError, match="timed out"):
            xurl_client._default_runner(["sleep", "5"], 0.05)


# ===================================================================
# Validation
# ===================================================================


class TestValidation:
    def test_get_user_tweets_rejects_non_numeric_id(self) -> None:
        with pytest.raises(XurlError, match="invalid user_id"):
            get_user_tweets("123/abc", runner=make_runner())

    @pytest.mark.parametrize("bad", ["", "no spaces!", "a" * 16, "@@bad"])
    def test_username_rejected(self, bad) -> None:
        with pytest.raises(XurlError, match="invalid username"):
            get_user_by_username(bad, runner=make_runner())

    def test_username_strips_leading_at(self) -> None:
        runner = json_runner({"data": {"id": "555"}})
        uid = get_user_by_username("@alice", runner=runner)
        assert uid == "555"
        # The '@' must not appear in the requested endpoint.
        argv = runner.calls[0][0]
        assert "/2/users/by/username/alice" in argv[1]
        assert "@" not in argv[1]

    def test_get_user_by_username_not_found(self) -> None:
        runner = json_runner({"data": {}})
        with pytest.raises(XurlNotFoundError):
            get_user_by_username("ghost", runner=runner)


# ===================================================================
# Endpoint construction
# ===================================================================


class TestEndpoints:
    def test_search_recent_builds_query_and_dates(self) -> None:
        runner = json_runner(search_payload())
        search_recent(
            "grok lang:ja",
            max_results=10,
            from_date="2025-01-01",
            to_date="2025-01-31",
            runner=runner,
        )
        url = runner.calls[0][0][1]
        assert url.startswith("/2/tweets/search/recent?query=")
        assert "grok%20lang%3Aja" in url  # query is percent-encoded
        assert "start_time=2025-01-01T00:00:00Z" in url
        assert "end_time=2025-01-31T23:59:59Z" in url  # to_date is inclusive

    def test_search_recent_floors_max_results_at_10(self) -> None:
        runner = json_runner(search_payload())
        search_recent("x", max_results=3, runner=runner)
        assert "max_results=10" in runner.calls[0][0][1]

    def test_search_recent_caps_max_results_at_100(self) -> None:
        runner = json_runner(search_payload())
        search_recent("x", max_results=999, runner=runner)
        assert "max_results=100" in runner.calls[0][0][1]

    def test_get_user_tweets_endpoint(self) -> None:
        runner = json_runner(search_payload())
        get_user_tweets(
            "42",
            max_results=10,
            from_date="2025-02-01",
            to_date="2025-02-28",
            runner=runner,
        )
        url = runner.calls[0][0][1]
        assert url.startswith("/2/users/42/tweets?")
        assert "start_time=2025-02-01T00:00:00Z" in url
        assert "end_time=2025-02-28T23:59:59Z" in url

    def test_invalid_date_raises(self) -> None:
        runner = json_runner(search_payload())
        with pytest.raises(XurlError, match="invalid date"):
            search_recent("x", from_date="01/01/2025", runner=runner)


# ===================================================================
# JSON -> post mapping
# ===================================================================


class TestMapping:
    def test_posts_from_response(self) -> None:
        posts = posts_from_response(search_payload())
        assert len(posts) == 2
        first = posts[0]
        assert first["id"] == "1001"
        assert first["username"] == "alice"
        assert first["author_name"] == "Alice"
        assert first["likes"] == 5
        assert first["retweets"] == 2
        assert first["views"] == 100
        assert first["url"] == "https://x.com/alice/status/1001"
        assert first["created_at"].endswith("+00:00")

    def test_posts_from_response_limit(self) -> None:
        posts = posts_from_response(search_payload(), limit=1)
        assert len(posts) == 1

    def test_posts_from_empty_response(self) -> None:
        assert posts_from_response({}) == []

    def test_tweet_without_id_returns_none(self) -> None:
        assert tweet_json_to_post({"text": "x"}, {}) is None

    def test_url_falls_back_without_username(self) -> None:
        post = tweet_json_to_post({"id": "77", "author_id": "x"}, {})
        assert post["url"] == "https://x.com/i/status/77"

    def test_created_at_passthrough_on_unparseable(self) -> None:
        post = tweet_json_to_post(
            {"id": "1", "created_at": "not-a-date"}, {}
        )
        assert post["created_at"] == "not-a-date"

    def test_created_at_none(self) -> None:
        post = tweet_json_to_post({"id": "1"}, {})
        assert post["created_at"] is None

    def test_created_at_naive_gets_utc(self) -> None:
        # No trailing Z / offset -> treated as UTC, normalized to +00:00.
        post = tweet_json_to_post(
            {"id": "1", "created_at": "2026-05-29T16:32:46"}, {}
        )
        assert post["created_at"] == "2026-05-29T16:32:46+00:00"

    def test_non_dict_items_skipped(self) -> None:
        resp = {"data": ["junk", {"id": "5", "author_id": "x"}]}
        posts = posts_from_response(resp)
        assert len(posts) == 1
        assert posts[0]["id"] == "5"


# ===================================================================
# Formatting
# ===================================================================


class TestFormat:
    def test_format_json(self) -> None:
        posts = posts_from_response(search_payload())
        out = format_posts(posts, as_json=True)
        parsed = json.loads(out)
        assert parsed[0]["id"] == "1001"

    def test_format_markdown(self) -> None:
        posts = posts_from_response(search_payload())
        out = format_posts(posts)
        assert "**Alice** (@alice)" in out
        assert "first post" in out
        assert "https://x.com/alice/status/1001" in out
        assert "---" in out  # separator between two posts

    def test_format_markdown_empty(self) -> None:
        assert format_posts([]) == "No posts found."

    def test_format_markdown_no_author_name(self) -> None:
        post = tweet_json_to_post({"id": "1", "author_id": "u"}, {})
        out = format_posts([post])
        assert "@unknown" in out
