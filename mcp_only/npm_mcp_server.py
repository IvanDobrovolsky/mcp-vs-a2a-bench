"""MCP server exposing npm tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from shared.npm_client import get_download_stats, get_full_package_info, get_package_info

mcp = FastMCP("npm MCP Server")


@mcp.tool()
async def npm_get_package(package_name: str) -> str:
    """Get full npm package information including downloads.

    Args:
        package_name: npm package name (e.g. 'react', 'express').
    """
    info = await get_full_package_info(package_name)
    return json.dumps(info, indent=2)


@mcp.tool()
async def npm_get_downloads(package_name: str) -> str:
    """Get weekly and monthly download counts for an npm package.

    Args:
        package_name: npm package name.
    """
    stats = await get_download_stats(package_name)
    stats["package"] = package_name
    return json.dumps(stats)


@mcp.tool()
async def npm_get_version(package_name: str) -> str:
    """Get the latest version of an npm package.

    Args:
        package_name: npm package name.
    """
    info = await get_package_info(package_name)
    return json.dumps({
        "package": package_name,
        "latest_version": info["latest_version"],
        "last_publish": info["last_publish"],
    })


@mcp.tool()
async def npm_get_dependencies(package_name: str) -> str:
    """Get dependency count for an npm package.

    Args:
        package_name: npm package name.
    """
    info = await get_package_info(package_name)
    return json.dumps({
        "package": package_name,
        "dependency_count": info["dependency_count"],
    })


if __name__ == "__main__":
    mcp.run()
