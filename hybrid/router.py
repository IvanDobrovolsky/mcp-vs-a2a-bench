"""Query complexity router for the hybrid architecture."""

from __future__ import annotations

import re

import anthropic

from shared.metrics import MetricsCollector
from shared.models import QueryComplexity

MODEL = "claude-sonnet-4-20250514"

# Heuristic keywords for fast classification
SINGLE_SOURCE_KEYWORDS = [
    "stars", "star count", "forks", "fork count",
    "downloads", "download count", "weekly downloads",
    "vulnerabilities", "vulnerability", "CVE",
    "stackoverflow", "questions tagged",
    "latest version", "last commit", "contributors",
    "open issues", "bundle size",
]

COMPARISON_KEYWORDS = [
    " vs ", " versus ", "compare", "comparison", "rank",
    "top 5", "top 10", "healthiest", "best",
    "cross-reference", "dashboard",
]

MULTI_SOURCE_KEYWORDS = [
    "health report", "full health", "risk assessment",
    "ecosystem", "all health", "gaining traction",
    "still relevant", "actively maintained",
    "evaluate", "should i adopt",
]


def classify_query_heuristic(query: str) -> QueryComplexity:
    """Fast heuristic classification without LLM call."""
    query_lower = query.lower()

    # Check for comparison/complex patterns
    has_comparison = any(kw in query_lower for kw in COMPARISON_KEYWORDS)

    # Count project mentions (rough proxy)
    from mcp_only.github_mcp_server import REPO_MAP
    projects_mentioned = sum(1 for name in REPO_MAP if name in query_lower)

    if has_comparison and projects_mentioned >= 3:
        return QueryComplexity.COMPLEX
    if has_comparison and projects_mentioned >= 2:
        return QueryComplexity.COMPLEX

    # Check for multi-source patterns
    has_multi_source = any(kw in query_lower for kw in MULTI_SOURCE_KEYWORDS)
    if has_multi_source:
        return QueryComplexity.MEDIUM

    # Check for single-source patterns
    has_single = any(kw in query_lower for kw in SINGLE_SOURCE_KEYWORDS)
    if has_single and projects_mentioned <= 1:
        return QueryComplexity.SIMPLE

    # Default: medium
    return QueryComplexity.MEDIUM


async def classify_query_llm(
    query: str, metrics: MetricsCollector
) -> QueryComplexity:
    """Use LLM for more accurate classification (costs tokens)."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system="""Classify the query complexity. Respond with ONLY one word:
- SIMPLE: single data source, single project (e.g., "How many stars does React have?")
- MEDIUM: multiple data sources, single project (e.g., "Give me a full health report on Express")
- COMPLEX: multiple sources, multiple projects (e.g., "Compare React vs Vue vs Svelte")""",
        messages=[{"role": "user", "content": query}],
    )
    metrics.record_llm_usage(response.usage.input_tokens, response.usage.output_tokens)

    text = response.content[0].text.strip().upper()
    if "SIMPLE" in text:
        return QueryComplexity.SIMPLE
    elif "COMPLEX" in text:
        return QueryComplexity.COMPLEX
    else:
        return QueryComplexity.MEDIUM


def classify_query(query: str) -> QueryComplexity:
    """Classify using fast heuristics (no LLM cost)."""
    return classify_query_heuristic(query)
