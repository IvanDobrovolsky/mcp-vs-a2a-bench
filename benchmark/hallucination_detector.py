"""Hallucination detection — compare LLM responses against ground-truth API data.

Approach:
1. For each benchmark query, independently fetch ground-truth data from the APIs
2. Extract numerical claims from the LLM response (stars, downloads, vuln counts, etc.)
3. Compare extracted claims against ground truth with tolerance bands
4. Flag fabricated data (numbers that don't match any real value)

This turns the spec's "manual spot-check" into a systematic, reproducible measurement.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.github_client import get_repo_info
from shared.npm_client import get_full_package_info
from shared.osv_client import query_vulnerabilities
from shared.stackoverflow_client import get_tag_info

RESULTS_DIR = Path(__file__).parent / "results"

# Project-to-API-args mapping (reuse from MCP server)
from mcp_only.github_mcp_server import REPO_MAP

NPM_MAP: dict[str, str] = {
    "react": "react", "vue": "vue", "svelte": "svelte",
    "angular": "@angular/core", "next.js": "next", "express": "express",
    "fastify": "fastify", "koa": "koa", "vite": "vite", "webpack": "webpack",
    "prisma": "@prisma/client", "drizzle": "drizzle-orm", "typeorm": "typeorm",
    "sequelize": "sequelize", "redux": "redux", "zustand": "zustand",
    "jotai": "jotai", "recoil": "recoil", "tailwindcss": "tailwindcss",
    "jest": "jest", "vitest": "vitest", "playwright": "playwright",
    "lodash": "lodash", "axios": "axios", "django": "django", "flask": "flask",
    "fastapi": "fastapi", "remix": "@remix-run/react", "bootstrap": "bootstrap",
}

SO_MAP: dict[str, str] = {
    "react": "reactjs", "vue": "vue.js", "svelte": "svelte",
    "angular": "angular", "express": "express", "fastify": "fastify",
    "django": "django", "flask": "flask", "fastapi": "fastapi",
    "redux": "redux", "jest": "jestjs", "vitest": "vitest",
    "playwright": "playwright", "lodash": "lodash", "axios": "axios",
}

OSV_MAP: dict[str, tuple[str, str]] = {
    "react": ("react", "npm"), "vue": ("vue", "npm"), "express": ("express", "npm"),
    "lodash": ("lodash", "npm"), "axios": ("axios", "npm"),
    "django": ("django", "PyPI"), "flask": ("flask", "PyPI"),
    "fastapi": ("fastapi", "PyPI"),
}


@dataclass
class Claim:
    """A numerical claim extracted from an LLM response."""
    metric: str  # e.g., "stars", "downloads", "vulnerabilities"
    project: str
    claimed_value: float
    source_context: str  # surrounding text for debugging


@dataclass
class GroundTruth:
    """Ground-truth data fetched directly from APIs."""
    project: str
    github: dict = field(default_factory=dict)
    npm: dict = field(default_factory=dict)
    osv: dict = field(default_factory=dict)
    stackoverflow: dict = field(default_factory=dict)


@dataclass
class HallucinationResult:
    """Result of hallucination check for a single response."""
    query_id: int
    query_text: str
    architecture: str
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0
    hallucinated_claims: int = 0
    hallucination_rate: float = 0.0
    claims_detail: list[dict] = field(default_factory=list)


# ── Ground Truth Fetching ──


async def fetch_ground_truth(projects: list[str]) -> dict[str, GroundTruth]:
    """Fetch ground-truth data for a set of projects from all APIs."""
    results = {}

    for project in projects:
        gt = GroundTruth(project=project)

        # GitHub
        key = project.lower().strip()
        if key in REPO_MAP:
            owner, repo = REPO_MAP[key]
            try:
                gt.github = await get_repo_info(owner, repo)
            except Exception:
                pass

        # npm
        if key in NPM_MAP:
            try:
                gt.npm = await get_full_package_info(NPM_MAP[key])
            except Exception:
                pass

        # OSV
        if key in OSV_MAP:
            pkg, eco = OSV_MAP[key]
            try:
                gt.osv = await query_vulnerabilities(pkg, eco)
            except Exception:
                pass

        # StackOverflow
        if key in SO_MAP:
            try:
                gt.stackoverflow = await get_tag_info(SO_MAP[key])
            except Exception:
                pass

        results[project] = gt

    return results


# ── Claim Extraction ──


def extract_claims(response_text: str, projects: list[str]) -> list[Claim]:
    """Extract numerical claims from an LLM response.

    Looks for patterns like:
    - "React has 220,000 stars"
    - "45.2 million weekly downloads"
    - "12 known vulnerabilities"
    - "150,000 questions on StackOverflow"
    """
    claims = []
    text = response_text

    # Patterns for numerical claims
    patterns = [
        # Stars: "X stars", "X GitHub stars"
        (r"([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*(?:github\s+)?stars", "stars"),
        # Forks
        (r"([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*forks", "forks"),
        # Downloads: "X weekly downloads", "X million downloads"
        (r"([\d,]+(?:\.\d+)?)\s*(?:million|M|k|K)?\s*(?:weekly\s+)?downloads", "downloads"),
        # Issues: "X open issues"
        (r"([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*(?:open\s+)?issues", "issues"),
        # Contributors
        (r"([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*contributors", "contributors"),
        # Vulnerabilities
        (r"([\d,]+)\s*(?:known\s+)?vulnerabilit(?:y|ies)", "vulnerabilities"),
        # Critical vulns
        (r"([\d,]+)\s*critical\s*(?:vulnerabilit(?:y|ies))?", "critical_vulns"),
        # StackOverflow questions
        (r"([\d,]+(?:\.\d+)?)\s*(?:k|K|million|M)?\s*(?:stackoverflow\s+)?questions", "so_questions"),
        # Commits
        (r"([\d,]+)\s*(?:recent\s+)?commits", "commits"),
    ]

    for pattern, metric in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw_value = match.group(1).replace(",", "")
            value = float(raw_value)

            # Check for multipliers in context
            context_start = max(0, match.start() - 50)
            context_end = min(len(text), match.end() + 50)
            context = text[context_start:context_end]

            if re.search(r"million|M\b", context, re.IGNORECASE) and value < 1000:
                value *= 1_000_000
            elif re.search(r"\b[kK]\b", context) and value < 10000:
                value *= 1000

            # Associate with nearest project mention
            best_project = _find_nearest_project(text, match.start(), projects)

            if best_project:
                claims.append(Claim(
                    metric=metric,
                    project=best_project,
                    claimed_value=value,
                    source_context=context.strip(),
                ))

    return claims


def _find_nearest_project(text: str, position: int, projects: list[str]) -> str | None:
    """Find the project name mentioned closest to a given position in text."""
    best_project = None
    best_distance = float("inf")

    text_lower = text.lower()

    for project in projects:
        # Search for project name near the claim
        idx = text_lower.rfind(project.lower(), max(0, position - 300), position + 100)
        if idx >= 0:
            distance = abs(position - idx)
            if distance < best_distance:
                best_distance = distance
                best_project = project

    return best_project


# ── Claim Verification ──


# Tolerance bands for different metrics (relative tolerance)
TOLERANCES = {
    "stars": 0.10,          # 10% — stars change slowly
    "forks": 0.10,
    "downloads": 0.20,      # 20% — downloads fluctuate more
    "issues": 0.15,
    "contributors": 0.15,
    "vulnerabilities": 0.0, # Exact match for vuln counts
    "critical_vulns": 0.0,
    "so_questions": 0.10,
    "commits": 0.25,        # Commits in last 30d vary
}


def verify_claim(claim: Claim, ground_truth: GroundTruth) -> dict:
    """Verify a single claim against ground truth.

    Returns a dict with verification status and details.
    """
    gt_value = _get_ground_truth_value(claim.metric, ground_truth)

    if gt_value is None:
        return {
            "metric": claim.metric,
            "project": claim.project,
            "claimed": claim.claimed_value,
            "ground_truth": None,
            "status": "unverified",
            "reason": "No ground truth available for this metric",
            "context": claim.source_context,
        }

    tolerance = TOLERANCES.get(claim.metric, 0.15)
    claimed = claim.claimed_value
    actual = float(gt_value)

    if actual == 0:
        is_correct = claimed == 0
    else:
        relative_error = abs(claimed - actual) / actual
        is_correct = relative_error <= tolerance

    status = "verified" if is_correct else "hallucinated"

    return {
        "metric": claim.metric,
        "project": claim.project,
        "claimed": claimed,
        "ground_truth": actual,
        "relative_error": abs(claimed - actual) / actual if actual != 0 else (0 if claimed == 0 else float("inf")),
        "tolerance": tolerance,
        "status": status,
        "reason": "" if is_correct else f"Claimed {claimed:,.0f}, actual {actual:,.0f} (error: {abs(claimed - actual) / actual * 100:.1f}%)" if actual != 0 else f"Claimed {claimed:,.0f}, actual 0",
        "context": claim.source_context,
    }


def _get_ground_truth_value(metric: str, gt: GroundTruth) -> float | None:
    """Look up ground truth value for a metric."""
    if metric == "stars":
        return gt.github.get("stars")
    elif metric == "forks":
        return gt.github.get("forks")
    elif metric == "issues":
        return gt.github.get("open_issues")
    elif metric == "contributors":
        return gt.github.get("contributors_count")
    elif metric == "commits":
        return gt.github.get("recent_commits_30d")
    elif metric == "downloads":
        # Could be weekly or monthly
        weekly = gt.npm.get("weekly_downloads")
        monthly = gt.npm.get("monthly_downloads")
        return weekly or monthly
    elif metric == "vulnerabilities":
        return gt.osv.get("total_vulnerabilities")
    elif metric == "critical_vulns":
        return gt.osv.get("critical")
    elif metric == "so_questions":
        return gt.stackoverflow.get("total_questions")
    return None


# ── Full Check ──


async def check_hallucinations(
    response_text: str,
    projects: list[str],
    query_id: int = 0,
    query_text: str = "",
    architecture: str = "",
) -> HallucinationResult:
    """Run full hallucination check on a response."""
    # Fetch ground truth
    ground_truth = await fetch_ground_truth(projects)

    # Extract claims
    claims = extract_claims(response_text, projects)

    # Verify each claim
    details = []
    verified = 0
    hallucinated = 0
    unverified = 0

    for claim in claims:
        gt = ground_truth.get(claim.project)
        if gt:
            result = verify_claim(claim, gt)
            details.append(result)
            if result["status"] == "verified":
                verified += 1
            elif result["status"] == "hallucinated":
                hallucinated += 1
            else:
                unverified += 1
        else:
            unverified += 1
            details.append({
                "metric": claim.metric,
                "project": claim.project,
                "claimed": claim.claimed_value,
                "status": "unverified",
                "reason": "Project not in ground truth set",
                "context": claim.source_context,
            })

    total = verified + hallucinated + unverified
    rate = hallucinated / (verified + hallucinated) if (verified + hallucinated) > 0 else 0.0

    return HallucinationResult(
        query_id=query_id,
        query_text=query_text,
        architecture=architecture,
        total_claims=total,
        verified_claims=verified,
        unverified_claims=unverified,
        hallucinated_claims=hallucinated,
        hallucination_rate=rate,
        claims_detail=details,
    )


async def check_benchmark_results(filename: str = "benchmark_results.json") -> list[HallucinationResult]:
    """Run hallucination detection on all saved benchmark results."""
    filepath = RESULTS_DIR / filename
    with open(filepath) as f:
        results = json.load(f)

    # Load queries for project lists
    queries_file = Path(__file__).parent / "queries.json"
    with open(queries_file) as f:
        queries = {q["id"]: q for q in json.load(f)["queries"]}

    hallucination_results = []
    total = len(results)

    for i, result in enumerate(results):
        query_id = result.get("query_id", 0)
        query_info = queries.get(query_id, {})
        projects = query_info.get("projects", [])

        if not projects or not result.get("response_text"):
            continue

        print(f"[{i+1}/{total}] Checking Q{query_id} ({result['architecture']})...", end=" ", flush=True)

        hr = await check_hallucinations(
            response_text=result["response_text"],
            projects=projects,
            query_id=query_id,
            query_text=result.get("query_text", ""),
            architecture=result.get("architecture", ""),
        )

        status = f"{hr.verified_claims}V/{hr.hallucinated_claims}H/{hr.unverified_claims}U"
        print(f"claims: {status} (rate: {hr.hallucination_rate:.0%})")

        hallucination_results.append(hr)

    # Save
    _save_results(hallucination_results)
    _print_summary(hallucination_results)

    return hallucination_results


def _save_results(results: list[HallucinationResult]):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / "hallucination_results.json"

    data = []
    for r in results:
        data.append({
            "query_id": r.query_id,
            "query_text": r.query_text,
            "architecture": r.architecture,
            "total_claims": r.total_claims,
            "verified_claims": r.verified_claims,
            "unverified_claims": r.unverified_claims,
            "hallucinated_claims": r.hallucinated_claims,
            "hallucination_rate": r.hallucination_rate,
            "claims_detail": r.claims_detail,
        })

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nResults saved to {filepath}")


def _print_summary(results: list[HallucinationResult]):
    print("\n" + "=" * 70)
    print("HALLUCINATION DETECTION SUMMARY")
    print("=" * 70)

    for arch in ["mcp", "a2a", "hybrid"]:
        arch_results = [r for r in results if r.architecture == arch]
        if not arch_results:
            continue

        total_claims = sum(r.verified_claims + r.hallucinated_claims for r in arch_results)
        total_hallucinated = sum(r.hallucinated_claims for r in arch_results)
        rate = total_hallucinated / total_claims if total_claims > 0 else 0

        print(f"\n  {arch.upper()}:")
        print(f"    Verifiable claims:  {total_claims}")
        print(f"    Hallucinated:       {total_hallucinated}")
        print(f"    Hallucination rate: {rate:.1%}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check for hallucinated data in benchmark responses")
    parser.add_argument("--input", default="benchmark_results.json")
    args = parser.parse_args()

    await check_benchmark_results(args.input)


if __name__ == "__main__":
    asyncio.run(main())
