"""npm Registry API wrapper."""

from __future__ import annotations

import httpx

NPM_REGISTRY = "https://registry.npmjs.org"
NPM_API = "https://api.npmjs.org"


async def get_package_info(package_name: str) -> dict:
    """Fetch package metadata from npm registry."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{NPM_REGISTRY}/{package_name}")
        resp.raise_for_status()
        data = resp.json()

        latest_version = data.get("dist-tags", {}).get("latest", "")
        versions = data.get("versions", {})
        latest_data = versions.get(latest_version, {})

        # Count dependencies
        deps = latest_data.get("dependencies", {})
        dependency_count = len(deps) if deps else 0

        return {
            "name": data.get("name", package_name),
            "latest_version": latest_version,
            "dependency_count": dependency_count,
            "versions_count": len(versions),
            "last_publish": data.get("time", {}).get(latest_version, ""),
            "description": data.get("description", ""),
            "license": latest_data.get("license") or data.get("license", ""),
        }


async def get_download_stats(package_name: str) -> dict:
    """Fetch download statistics for a package."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Weekly downloads
        weekly_resp = await client.get(
            f"{NPM_API}/downloads/point/last-week/{package_name}"
        )
        weekly = 0
        if weekly_resp.status_code == 200:
            weekly = weekly_resp.json().get("downloads", 0)

        # Monthly downloads
        monthly_resp = await client.get(
            f"{NPM_API}/downloads/point/last-month/{package_name}"
        )
        monthly = 0
        if monthly_resp.status_code == 200:
            monthly = monthly_resp.json().get("downloads", 0)

        return {
            "weekly_downloads": weekly,
            "monthly_downloads": monthly,
        }


async def get_full_package_info(package_name: str) -> dict:
    """Get combined package info and download stats."""
    info = await get_package_info(package_name)
    downloads = await get_download_stats(package_name)
    info.update(downloads)
    return info
