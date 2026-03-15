"""MCP server exposing StackOverflow tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from shared.stackoverflow_client import get_tag_info

mcp = FastMCP("StackOverflow MCP Server")


@mcp.tool()
async def stackoverflow_get_tag_stats(tag: str) -> str:
    """Get StackOverflow statistics for a tag.

    Args:
        tag: The StackOverflow tag to look up (e.g. 'reactjs', 'python', 'express').
    """
    info = await get_tag_info(tag)
    return json.dumps(info, indent=2)


@mcp.tool()
async def stackoverflow_get_question_count(tag: str) -> str:
    """Get total question count for a StackOverflow tag.

    Args:
        tag: The StackOverflow tag.
    """
    info = await get_tag_info(tag)
    return json.dumps({
        "tag": tag,
        "total_questions": info["total_questions"],
        "questions_last_30d": info["questions_last_30d"],
    })


if __name__ == "__main__":
    mcp.run()
