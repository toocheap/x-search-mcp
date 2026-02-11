#!/usr/bin/env python3
"""
X (Twitter) Search MCP Server via xAI API

Uses xAI's Grok API with built-in live search capabilities to search
X/Twitter posts. Grok has native access to X data through its API.

Required environment variable:
    XAI_API_KEY - Your xAI API key from https://console.x.ai/

Usage with Claude Desktop:
    Add to claude_desktop_config.json:
    {
        "mcpServers": {
            "x_search": {
                "command": "python",
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
XAI_MODEL = "grok-3-mini"
DEFAULT_TIMEOUT = 60.0
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


async def _call_grok(prompt: str, *, search_enabled: bool = True) -> str:
    """Call xAI Grok API with optional live search for X data.

    Args:
        prompt: The prompt to send to Grok.
        search_enabled: Whether to enable live X/web search.

    Returns:
        The text response from Grok.
    """
    api_key = _get_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body: dict = {
        "model": XAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that searches X (Twitter) posts. "
                    "Return results in structured JSON format. "
                    "For each post found, include: author username, author display name, "
                    "post text content, approximate date/time, and engagement metrics "
                    "(likes, reposts, replies) if available. "
                    "Always respond with valid JSON only, no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "search_parameters": {"mode": "auto" if search_enabled else "off"},
        "temperature": 0.0,
    }

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(
            f"{XAI_API_BASE}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract the assistant message
    choices = data.get("choices", [])
    if not choices:
        return json.dumps({"error": "No response from Grok API"})
    return choices[0]["message"]["content"]


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
        # Try to extract error detail from response body
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

        return await _call_grok(prompt, search_enabled=True)

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

        return await _call_grok(prompt, search_enabled=True)

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
            f"List the top trending topics with brief descriptions of why they're trending.\n"
            f"Format the output as {fmt}."
        )

        return await _call_grok(prompt, search_enabled=True)

    except Exception as e:
        return _handle_api_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
