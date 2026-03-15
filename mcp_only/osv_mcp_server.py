"""MCP server exposing OSV.dev vulnerability tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from shared.osv_client import query_vulnerabilities

mcp = FastMCP("OSV MCP Server")


@mcp.tool()
async def osv_check_vulnerabilities(package_name: str, ecosystem: str = "npm") -> str:
    """Check known vulnerabilities for a package.

    Args:
        package_name: Package name to check (e.g. 'lodash', 'express').
        ecosystem: Package ecosystem (default: 'npm'). Options: npm, PyPI, Go, Maven, etc.
    """
    report = await query_vulnerabilities(package_name, ecosystem)
    return json.dumps(report, indent=2)


@mcp.tool()
async def osv_get_vulnerability_summary(package_name: str, ecosystem: str = "npm") -> str:
    """Get a summary count of vulnerabilities by severity.

    Args:
        package_name: Package name to check.
        ecosystem: Package ecosystem (default: 'npm').
    """
    report = await query_vulnerabilities(package_name, ecosystem)
    return json.dumps({
        "package": package_name,
        "ecosystem": ecosystem,
        "total": report["total_vulnerabilities"],
        "critical": report["critical"],
        "high": report["high"],
        "medium": report["medium"],
        "low": report["low"],
    })


if __name__ == "__main__":
    mcp.run()
