"""GitHub REST API wrapper."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get_repo_info(owner: str, repo: str) -> dict:
    """Fetch core repository metadata."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()

        # Get contributor count
        contributors_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contributors",
            headers=_headers(),
            params={"per_page": 1, "anon": "true"},
        )
        contributors_count = 0
        if contributors_resp.status_code == 200:
            # Use Link header to get total count
            link = contributors_resp.headers.get("Link", "")
            if 'rel="last"' in link:
                import re
                match = re.search(r"page=(\d+)>; rel=\"last\"", link)
                if match:
                    contributors_count = int(match.group(1))
            else:
                contributors_count = len(contributors_resp.json())

        # Get recent commits (last 30 days)
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        commits_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_headers(),
            params={"since": since, "per_page": 1},
        )
        recent_commits = 0
        if commits_resp.status_code == 200:
            link = commits_resp.headers.get("Link", "")
            if 'rel="last"' in link:
                import re
                match = re.search(r"page=(\d+)>; rel=\"last\"", link)
                if match:
                    recent_commits = int(match.group(1))
            else:
                recent_commits = len(commits_resp.json())

        # Get open PRs count
        prs_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(),
            params={"state": "open", "per_page": 1},
        )
        open_prs = 0
        if prs_resp.status_code == 200:
            link = prs_resp.headers.get("Link", "")
            if 'rel="last"' in link:
                import re
                match = re.search(r"page=(\d+)>; rel=\"last\"", link)
                if match:
                    open_prs = int(match.group(1))
            else:
                open_prs = len(prs_resp.json())

        return {
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "watchers": data.get("subscribers_count", 0),
            "language": data.get("language"),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "pushed_at": data.get("pushed_at", ""),
            "description": data.get("description", "") or "",
            "contributors_count": contributors_count,
            "recent_commits_30d": recent_commits,
            "open_prs": open_prs,
            "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
        }


async def get_last_commit_date(owner: str, repo: str) -> str:
    """Get the date of the most recent commit."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_headers(),
            params={"per_page": 1},
        )
        resp.raise_for_status()
        commits = resp.json()
        if commits:
            return commits[0].get("commit", {}).get("committer", {}).get("date", "")
        return ""
