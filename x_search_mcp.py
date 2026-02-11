#!/usr/bin/env python3
"""
X (Twitter) Search MCP Server via xAI Agent Tools API

Uses xAI's Responses API with built-in x_search tool to search
X/Twitter posts. This is the new Agent Tools API that replaced
the deprecated Live Search API.

Required environment variable:
    XAI_API_KEY - Your xAI API key from https://console.x.ai/

Usage with Claude Desktop:
    Add to claude_desktop_config.json:
    {
        "mcpServers": {
            "x_search": {
                "command": "/path/to/.venv/bin/python3",
                "args": ["/path/to/x_search_mcp.py"],
                "env": {
                    "XAI_API_KEY": "your-api-key-here"
                }
            }
        }
    }
"""

import json
import os
import sys
from enum import Enum
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

XAI_API_BASE = "https://api.x.ai/v1"
XAI_MODEL = "grok-4-1-fast"
DEFAULT_TIMEOUT = 120.0
MAX_RESULTS_DEFAULT = 10

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("x_search_mcp")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    """Retrieve xAI API key from environment."""
    key = os.environ.get("XAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "XAI_API_KEY environment variable is not set. "
            "Get your key from https://console.x.ai/"
        )
    return key


async def _call_responses_api(
    user_prompt: str,
    *,
    x_search_config: Optional[dict] = None,
) -> str:
    """Call xAI Responses API with x_search tool.

    Uses the new /v1/responses endpoint with Agent Tools API.

    Args:
        user_prompt: The user query to search for.
        x_search_config: Optional dict of x_search tool parameters
            (allowed_x_handles, excluded_x_handles, from_date, to_date, etc.)

    Returns:
        The text response from the API.
    """
    api_key = _get_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build x_search tool config
    x_search_tool: dict = {"type": "x_search"}
    if x_search_config:
        x_search_tool.update(x_search_config)

    body = {
        "model": XAI_MODEL,
        "input": [
            {"role": "user", "content": user_prompt},
        ],
        "tools": [x_search_tool],
    }

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(
            f"{XAI_API_BASE}/responses",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract text from the response output
    output = data.get("output", [])
    text_parts = []
    for item in output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
        elif isinstance(item.get("text"), str):
            text_parts.append(item["text"])

    if text_parts:
        return "\n".join(text_parts)

    # Fallback: return raw JSON if we can't parse text
    return json.dumps(data, indent=2, ensure_ascii=False)


def _handle_api_error(e: Exception) -> str:
    """Format API errors into user-friendly messages."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return json.dumps({
                "error": "Authentication failed. Check your XAI_API_KEY.",
                "status": 401,
            })
        if status == 429:
            return json.dumps({
                "error": "Rate limit exceeded. Please wait before retrying.",
                "status": 429,
            })
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return json.dumps({
            "error": f"API request failed with status {status}",
            "detail": str(detail),
        })
    if isinstance(e, httpx.TimeoutException):
        return json.dumps({"error": "Request timed out. Try again later."})
    if isinstance(e, RuntimeError):
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"Unexpected error: {type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
# Input Models
# ---------------------------------------------------------------------------


class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class XSearchPostsInput(BaseModel):
    """Input for searching X posts by keyword or topic."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    query: str = Field(
        ...,
        description=(
            "Search query for X posts. Can be keywords, hashtags, "
            "or natural language (e.g., 'AI news today', '#python', "
            "'what people are saying about Tesla')"
        ),
        min_length=1,
        max_length=500,
    )
    max_results: Optional[int] = Field(
        default=MAX_RESULTS_DEFAULT,
        description="Maximum number of posts to return",
        ge=1,
        le=30,
    )
    language: Optional[str] = Field(
        default=None,
        description=(
            "Filter by language (e.g., 'ja' for Japanese, 'en' for English). "
            "Leave empty for all languages."
        ),
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Search start date in YYYY-MM-DD format (e.g., '2025-01-01')",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="Search end date in YYYY-MM-DD format (e.g., '2025-12-31')",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for readable text, 'json' for structured data",
    )


class XGetUserPostsInput(BaseModel):
    """Input for retrieving a specific X user's recent posts."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    username: str = Field(
        ...,
        description="X username without @ prefix (e.g., 'elonmusk', 'OpenAI')",
        min_length=1,
        max_length=50,
    )
    max_results: Optional[int] = Field(
        default=MAX_RESULTS_DEFAULT,
        description="Maximum number of posts to return",
        ge=1,
        le=30,
    )
    topic_filter: Optional[str] = Field(
        default=None,
        description="Optional topic to filter posts by (e.g., 'AI', 'cybersecurity')",
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Search start date in YYYY-MM-DD format",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="Search end date in YYYY-MM-DD format",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for readable text, 'json' for structured data",
    )


class XTrendingInput(BaseModel):
    """Input for retrieving trending topics on X."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    region: Optional[str] = Field(
        default=None,
        description=(
            "Region for trends (e.g., 'Japan', 'United States', 'global'). "
            "Leave empty for global trends."
        ),
    )
    category: Optional[str] = Field(
        default=None,
        description="Optional category filter (e.g., 'technology', 'politics', 'sports')",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for readable text, 'json' for structured data",
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _build_x_search_config(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    allowed_handles: Optional[list] = None,
    excluded_handles: Optional[list] = None,
) -> Optional[dict]:
    """Build x_search tool configuration dict."""
    config: dict = {}
    if from_date:
        config["from_date"] = from_date
    if to_date:
        config["to_date"] = to_date
    if allowed_handles:
        config["allowed_x_handles"] = allowed_handles
    if excluded_handles:
        config["excluded_x_handles"] = excluded_handles
    return config if config else None


@mcp.tool(
    name="x_search_posts",
    annotations={
        "title": "Search X (Twitter) Posts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def x_search_posts(params: XSearchPostsInput) -> str:
    """Search for posts on X (Twitter) by keywords, hashtags, or topics.

    Uses xAI's Grok API with live search to find recent and relevant
    X posts matching the search query.

    Args:
        params (XSearchPostsInput): Validated input containing:
            - query (str): Search keywords or topic
            - max_results (int): Max posts to return (1-30, default 10)
            - language (str): Optional language filter
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Search results formatted as markdown or JSON
    """
    try:
        lang_part = ""
        if params.language:
            lang_part = f" Filter to {params.language} language posts only."

        fmt = "JSON" if params.response_format == ResponseFormat.JSON else "markdown"

        prompt = (
            f"Search X (Twitter) for posts about: {params.query}\n"
            f"Return up to {params.max_results} recent and relevant posts.{lang_part}\n"
            f"For each post include: author @username, display name, post text, "
            f"date/time, and engagement metrics (likes, reposts, replies) if available.\n"
            f"Format the output as {fmt}."
        )

        x_config = _build_x_search_config(
            from_date=params.from_date,
            to_date=params.to_date,
        )

        return await _call_responses_api(prompt, x_search_config=x_config)

    except Exception as e:
        return _handle_api_error(e)


@mcp.tool(
    name="x_get_user_posts",
    annotations={
        "title": "Get X User's Recent Posts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def x_get_user_posts(params: XGetUserPostsInput) -> str:
    """Retrieve recent posts from a specific X (Twitter) user.

    Uses xAI's Grok API with live search to find recent posts
    from the specified user account.

    Args:
        params (XGetUserPostsInput): Validated input containing:
            - username (str): X username without @
            - max_results (int): Max posts to return (1-30, default 10)
            - topic_filter (str): Optional topic filter
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: User's recent posts formatted as markdown or JSON
    """
    try:
        topic_part = ""
        if params.topic_filter:
            topic_part = f" Focus on posts related to: {params.topic_filter}."

        fmt = "JSON" if params.response_format == ResponseFormat.JSON else "markdown"

        prompt = (
            f"Find recent posts from X (Twitter) user @{params.username}.\n"
            f"Return up to {params.max_results} of their most recent posts.{topic_part}\n"
            f"For each post include: post text, date/time, and engagement metrics "
            f"(likes, reposts, replies) if available.\n"
            f"Format the output as {fmt}."
        )

        x_config = _build_x_search_config(
            from_date=params.from_date,
            to_date=params.to_date,
            allowed_handles=[params.username],
        )

        return await _call_responses_api(prompt, x_search_config=x_config)

    except Exception as e:
        return _handle_api_error(e)


@mcp.tool(
    name="x_get_trending",
    annotations={
        "title": "Get Trending Topics on X",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def x_get_trending(params: XTrendingInput) -> str:
    """Get current trending topics and hashtags on X (Twitter).

    Uses xAI's Grok API with live search to find what's currently
    trending on X.

    Args:
        params (XTrendingInput): Validated input containing:
            - region (str): Optional region filter
            - category (str): Optional category filter
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Trending topics formatted as markdown or JSON
    """
    try:
        region_part = f" in {params.region}" if params.region else " globally"
        category_part = ""
        if params.category:
            category_part = f" Focus on {params.category} topics."

        fmt = "JSON" if params.response_format == ResponseFormat.JSON else "markdown"

        prompt = (
            f"What are the current trending topics and hashtags on X (Twitter)"
            f"{region_part}?{category_part}\n"
            f"List the top trending topics with brief descriptions of why they are trending.\n"
            f"Format the output as {fmt}."
        )

        return await _call_responses_api(prompt)

    except Exception as e:
        return _handle_api_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
