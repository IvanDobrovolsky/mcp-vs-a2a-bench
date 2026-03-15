"""MCP server exposing GitHub tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from shared.github_client import get_last_commit_date, get_repo_info

mcp = FastMCP("GitHub MCP Server")

# Mapping of common project names to GitHub owner/repo
REPO_MAP: dict[str, tuple[str, str]] = {
    "react": ("facebook", "react"),
    "vue": ("vuejs", "core"),
    "svelte": ("sveltejs", "svelte"),
    "angular": ("angular", "angular"),
    "next.js": ("vercel", "next.js"),
    "nextjs": ("vercel", "next.js"),
    "nuxt": ("nuxt", "nuxt"),
    "sveltekit": ("sveltejs", "kit"),
    "express": ("expressjs", "express"),
    "express.js": ("expressjs", "express"),
    "fastify": ("fastify", "fastify"),
    "koa": ("koajs", "koa"),
    "django": ("django", "django"),
    "flask": ("pallets", "flask"),
    "fastapi": ("fastapi", "fastapi"),
    "deno": ("denoland", "deno"),
    "bun": ("oven-sh", "bun"),
    "node.js": ("nodejs", "node"),
    "nodejs": ("nodejs", "node"),
    "vite": ("vitejs", "vite"),
    "webpack": ("webpack", "webpack"),
    "turbopack": ("vercel", "turborepo"),
    "prisma": ("prisma", "prisma"),
    "drizzle": ("drizzle-team", "drizzle-orm"),
    "typeorm": ("typeorm", "typeorm"),
    "sequelize": ("sequelize", "sequelize"),
    "redux": ("reduxjs", "redux"),
    "zustand": ("pmndrs", "zustand"),
    "jotai": ("pmndrs", "jotai"),
    "recoil": ("facebookexperimental", "Recoil"),
    "tailwind": ("tailwindlabs", "tailwindcss"),
    "tailwind css": ("tailwindlabs", "tailwindcss"),
    "tailwindcss": ("tailwindlabs", "tailwindcss"),
    "bootstrap": ("twbs", "bootstrap"),
    "jest": ("jestjs", "jest"),
    "vitest": ("vitest-dev", "vitest"),
    "playwright": ("microsoft", "playwright"),
    "lodash": ("lodash", "lodash"),
    "axios": ("axios", "axios"),
    "tensorflow.js": ("tensorflow", "tfjs"),
    "tensorflowjs": ("tensorflow", "tfjs"),
    "remix": ("remix-run", "remix"),
}


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
