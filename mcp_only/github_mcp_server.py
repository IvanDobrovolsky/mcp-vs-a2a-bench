"""MCP server exposing GitHub tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from shared.github_client import get_last_commit_date, get_repo_info
from shared.project_maps import GITHUB_REPO_MAP

mcp = FastMCP("GitHub MCP Server")

# Re-export for backward compatibility
REPO_MAP = GITHUB_REPO_MAP


def _resolve_repo(project: str) -> tuple[str, str]:
    key = project.lower().strip()
    if key in REPO_MAP:
        return REPO_MAP[key]
    if "/" in project:
        parts = project.split("/", 1)
        return parts[0], parts[1]
    raise ValueError(
        f"Unknown project '{project}'. Use 'owner/repo' format or a known name."
    )


@mcp.tool()
async def github_get_repo(project: str) -> str:
    """Get GitHub repository information for a project.

    Args:
        project: Project name (e.g. 'react', 'vue') or 'owner/repo' format.
    """
    owner, repo = _resolve_repo(project)
    info = await get_repo_info(owner, repo)
    return json.dumps(info, indent=2)


@mcp.tool()
async def github_get_stars(project: str) -> str:
    """Get star count for a GitHub project.

    Args:
        project: Project name or 'owner/repo' format.
    """
    owner, repo = _resolve_repo(project)
    info = await get_repo_info(owner, repo)
    return json.dumps({"project": project, "stars": info["stars"]})


@mcp.tool()
async def github_get_last_commit(project: str) -> str:
    """Get the date of the last commit for a project.

    Args:
        project: Project name or 'owner/repo' format.
    """
    owner, repo = _resolve_repo(project)
    date = await get_last_commit_date(owner, repo)
    return json.dumps({"project": project, "last_commit": date})


@mcp.tool()
async def github_get_contributors(project: str) -> str:
    """Get contributor count for a project.

    Args:
        project: Project name or 'owner/repo' format.
    """
    owner, repo = _resolve_repo(project)
    info = await get_repo_info(owner, repo)
    return json.dumps({"project": project, "contributors": info["contributors_count"]})


@mcp.tool()
async def github_get_issues(project: str) -> str:
    """Get open issue count for a project.

    Args:
        project: Project name or 'owner/repo' format.
    """
    owner, repo = _resolve_repo(project)
    info = await get_repo_info(owner, repo)
    return json.dumps({"project": project, "open_issues": info["open_issues"]})


if __name__ == "__main__":
    mcp.run()
