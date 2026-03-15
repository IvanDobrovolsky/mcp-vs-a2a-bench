"""Fault injection framework for testing error recovery across architectures.

Systematically degrades API sources and A2A agents to measure how each
architecture handles partial failures. This is critical for publication —
reviewers expect active fault testing, not passive "did something happen to fail."

Fault modes:
1. API timeout — individual data source becomes slow/unresponsive
2. API error — individual data source returns errors
3. Agent crash — A2A agent server becomes unavailable (A2A/Hybrid only)
4. Partial data — API returns incomplete/malformed data
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx

from shared.models import Architecture, BenchmarkResult, QueryComplexity

RESULTS_DIR = Path(__file__).parent / "results"


class FaultMode(str, Enum):
    NONE = "none"
    API_TIMEOUT = "api_timeout"
    API_ERROR = "api_error"
    AGENT_CRASH = "agent_crash"
    PARTIAL_DATA = "partial_data"


class FaultTarget(str, Enum):
    GITHUB = "github"
    NPM = "npm"
    OSV = "osv"
    STACKOVERFLOW = "stackoverflow"


@dataclass
class FaultConfig:
    """Configuration for a fault injection scenario."""
    mode: FaultMode
    target: FaultTarget
    description: str = ""
    timeout_seconds: float = 30.0  # For API_TIMEOUT mode
    error_code: int = 500  # For API_ERROR mode


@dataclass
class FaultResult:
    """Result of a fault injection test."""
    fault_config: FaultConfig
    architecture: Architecture
    query_id: int
    query_text: str
    # Did the system still produce a meaningful response?
    produced_response: bool = False
    # Did the response include data from non-faulted sources?
    partial_data_recovered: bool = False
    # Was the fault detected and reported to the user?
    fault_reported: bool = False
    # Response quality (0-1, fraction of expected data present)
    response_completeness: float = 0.0
    latency_ms: float = 0.0
    error_message: str = ""
    response_text: str = ""


# ── Fault Injection Mechanisms ──


def _make_timeout_mock(target: FaultTarget, timeout_seconds: float):
    """Create a mock that simulates API timeout for a specific data source."""
    original_clients = {
        FaultTarget.GITHUB: "shared.github_client",
        FaultTarget.NPM: "shared.npm_client",
        FaultTarget.OSV: "shared.osv_client",
        FaultTarget.STACKOVERFLOW: "shared.stackoverflow_client",
    }

    module = original_clients[target]

    async def slow_request(*args, **kwargs):
        await asyncio.sleep(timeout_seconds)
        raise httpx.TimeoutException(f"Simulated timeout for {target.value}")

    return module, slow_request


def _make_error_mock(target: FaultTarget, error_code: int):
    """Create a mock that simulates API errors."""
    async def error_request(*args, **kwargs):
        raise httpx.HTTPStatusError(
            f"Simulated {error_code} error for {target.value}",
            request=httpx.Request("GET", "http://fake"),
            response=httpx.Response(error_code),
        )

    return error_request


def _make_partial_data_mock(target: FaultTarget):
    """Create a mock that returns incomplete data."""
    if target == FaultTarget.GITHUB:
        async def partial(*args, **kwargs):
            return {"name": "", "stars": 0, "forks": 0, "open_issues": 0}
        return partial
    elif target == FaultTarget.NPM:
        async def partial(*args, **kwargs):
            return {"name": "", "weekly_downloads": 0, "monthly_downloads": 0}
        return partial
    elif target == FaultTarget.OSV:
        async def partial(*args, **kwargs):
            return {"package_name": "", "total_vulnerabilities": 0, "vulnerabilities": []}
        return partial
    else:
        async def partial(*args, **kwargs):
            return {"tag": "", "total_questions": 0}
        return partial


@asynccontextmanager
async def inject_fault(config: FaultConfig) -> AsyncGenerator[None, None]:
    """Context manager that injects a fault for the duration of a test."""
    if config.mode == FaultMode.NONE:
        yield
        return

    patches = []

    if config.mode == FaultMode.API_TIMEOUT:
        module, mock_fn = _make_timeout_mock(config.target, config.timeout_seconds)
        # Patch the main async functions in each client module
        if config.target == FaultTarget.GITHUB:
            patches.append(patch(f"{module}.get_repo_info", side_effect=mock_fn))
            patches.append(patch(f"{module}.get_last_commit_date", side_effect=mock_fn))
        elif config.target == FaultTarget.NPM:
            patches.append(patch(f"{module}.get_full_package_info", side_effect=mock_fn))
            patches.append(patch(f"{module}.get_package_info", side_effect=mock_fn))
            patches.append(patch(f"{module}.get_download_stats", side_effect=mock_fn))
        elif config.target == FaultTarget.OSV:
            patches.append(patch(f"{module}.query_vulnerabilities", side_effect=mock_fn))
        elif config.target == FaultTarget.STACKOVERFLOW:
            patches.append(patch(f"{module}.get_tag_info", side_effect=mock_fn))

    elif config.mode == FaultMode.API_ERROR:
        mock_fn = _make_error_mock(config.target, config.error_code)
        if config.target == FaultTarget.GITHUB:
            patches.append(patch("shared.github_client.get_repo_info", side_effect=mock_fn))
            patches.append(patch("shared.github_client.get_last_commit_date", side_effect=mock_fn))
        elif config.target == FaultTarget.NPM:
            patches.append(patch("shared.npm_client.get_full_package_info", side_effect=mock_fn))
            patches.append(patch("shared.npm_client.get_package_info", side_effect=mock_fn))
            patches.append(patch("shared.npm_client.get_download_stats", side_effect=mock_fn))
        elif config.target == FaultTarget.OSV:
            patches.append(patch("shared.osv_client.query_vulnerabilities", side_effect=mock_fn))
        elif config.target == FaultTarget.STACKOVERFLOW:
            patches.append(patch("shared.stackoverflow_client.get_tag_info", side_effect=mock_fn))

    elif config.mode == FaultMode.PARTIAL_DATA:
        mock_fn = _make_partial_data_mock(config.target)
        if config.target == FaultTarget.GITHUB:
            patches.append(patch("shared.github_client.get_repo_info", side_effect=mock_fn))
        elif config.target == FaultTarget.NPM:
            patches.append(patch("shared.npm_client.get_full_package_info", side_effect=mock_fn))
        elif config.target == FaultTarget.OSV:
            patches.append(patch("shared.osv_client.query_vulnerabilities", side_effect=mock_fn))
        elif config.target == FaultTarget.STACKOVERFLOW:
            patches.append(patch("shared.stackoverflow_client.get_tag_info", side_effect=mock_fn))

    elif config.mode == FaultMode.AGENT_CRASH:
        # For agent crash, we kill the A2A agent process.
        # This only affects A2A and Hybrid architectures.
        # The coordinator should gracefully handle the unavailable agent.
        # We simulate this by making the HTTP client fail for that agent's port.
        port_map = {
            FaultTarget.GITHUB: 8001,
            FaultTarget.NPM: 8002,
            FaultTarget.OSV: 8003,
            FaultTarget.STACKOVERFLOW: 8004,
        }
        port = port_map[config.target]

        original_post = httpx.AsyncClient.post

        async def failing_post(self, url, *args, **kwargs):
            if f":{port}" in str(url):
                raise httpx.ConnectError(f"Simulated agent crash on port {port}")
            return await original_post(self, url, *args, **kwargs)

        patches.append(patch.object(httpx.AsyncClient, "post", failing_post))

        original_get = httpx.AsyncClient.get

        async def failing_get(self, url, *args, **kwargs):
            if f":{port}" in str(url):
                raise httpx.ConnectError(f"Simulated agent crash on port {port}")
            return await original_get(self, url, *args, **kwargs)

        patches.append(patch.object(httpx.AsyncClient, "get", failing_get))

    # Apply patches
    for p in patches:
        p.start()

    try:
        yield
    finally:
        for p in patches:
            p.stop()


# ── Fault Test Scenarios ──

FAULT_SCENARIOS = [
    FaultConfig(FaultMode.NONE, FaultTarget.GITHUB, "Baseline — no faults"),
    # API failures
    FaultConfig(FaultMode.API_ERROR, FaultTarget.GITHUB, "GitHub API returns 500"),
    FaultConfig(FaultMode.API_ERROR, FaultTarget.NPM, "npm API returns 500"),
    FaultConfig(FaultMode.API_ERROR, FaultTarget.OSV, "OSV API returns 500"),
    FaultConfig(FaultMode.API_ERROR, FaultTarget.STACKOVERFLOW, "StackOverflow API returns 500"),
    # Timeouts
    FaultConfig(FaultMode.API_TIMEOUT, FaultTarget.GITHUB, "GitHub API times out", timeout_seconds=5),
    FaultConfig(FaultMode.API_TIMEOUT, FaultTarget.NPM, "npm API times out", timeout_seconds=5),
    # Partial data
    FaultConfig(FaultMode.PARTIAL_DATA, FaultTarget.GITHUB, "GitHub returns empty data"),
    FaultConfig(FaultMode.PARTIAL_DATA, FaultTarget.NPM, "npm returns empty data"),
    # Agent crashes (A2A/Hybrid only)
    FaultConfig(FaultMode.AGENT_CRASH, FaultTarget.GITHUB, "GitHub A2A agent crashes"),
    FaultConfig(FaultMode.AGENT_CRASH, FaultTarget.NPM, "npm A2A agent crashes"),
]

# Multi-source query for fault testing (touches all 4 sources)
FAULT_TEST_QUERY = {
    "id": 11,
    "text": "Give me a full health report on Express.js",
    "complexity": "medium",
}


def _assess_response(response_text: str, fault_config: FaultConfig) -> dict:
    """Assess the quality of a response under fault conditions."""
    if not response_text:
        return {
            "produced_response": False,
            "partial_data_recovered": False,
            "fault_reported": False,
            "response_completeness": 0.0,
        }

    response_lower = response_text.lower()

    # Check if non-faulted sources contributed data
    source_indicators = {
        FaultTarget.GITHUB: ["stars", "forks", "contributors", "commits", "issues"],
        FaultTarget.NPM: ["downloads", "version", "dependencies", "npm"],
        FaultTarget.OSV: ["vulnerabilit", "security", "cve"],
        FaultTarget.STACKOVERFLOW: ["stackoverflow", "questions", "answered"],
    }

    sources_present = 0
    total_sources = 4

    for target, indicators in source_indicators.items():
        if any(ind in response_lower for ind in indicators):
            sources_present += 1

    # The faulted source should be missing
    expected_sources = total_sources - 1 if fault_config.mode != FaultMode.NONE else total_sources

    return {
        "produced_response": True,
        "partial_data_recovered": sources_present >= expected_sources - 1,
        "fault_reported": any(
            word in response_lower
            for word in ["unavailable", "error", "unable", "failed", "could not", "timeout"]
        ),
        "response_completeness": sources_present / total_sources,
    }


async def run_fault_test(
    architecture: Architecture,
    fault_config: FaultConfig,
) -> FaultResult:
    """Run a single fault injection test."""
    query = FAULT_TEST_QUERY

    # Skip agent crash tests for MCP (not applicable)
    if fault_config.mode == FaultMode.AGENT_CRASH and architecture == Architecture.MCP:
        return FaultResult(
            fault_config=fault_config,
            architecture=architecture,
            query_id=query["id"],
            query_text=query["text"],
            error_message="Agent crash not applicable to MCP architecture",
        )

    complexity = QueryComplexity(query["complexity"])

    # Select the right runner
    if architecture == Architecture.MCP:
        from mcp_only.agent import run_query
    elif architecture == Architecture.A2A:
        from a2a_multi.coordinator import run_query
    else:
        from hybrid.coordinator import run_query

    start = time.perf_counter()

    try:
        async with inject_fault(fault_config):
            result = await run_query(
                query["text"],
                query_id=query["id"],
                complexity=complexity,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        assessment = _assess_response(result.response_text, fault_config)

        return FaultResult(
            fault_config=fault_config,
            architecture=architecture,
            query_id=query["id"],
            query_text=query["text"],
            produced_response=assessment["produced_response"],
            partial_data_recovered=assessment["partial_data_recovered"],
            fault_reported=assessment["fault_reported"],
            response_completeness=assessment["response_completeness"],
            latency_ms=elapsed_ms,
            response_text=result.response_text,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return FaultResult(
            fault_config=fault_config,
            architecture=architecture,
            query_id=query["id"],
            query_text=query["text"],
            latency_ms=elapsed_ms,
            error_message=str(e),
        )


async def run_fault_suite(
    architectures: list[Architecture] | None = None,
    scenarios: list[FaultConfig] | None = None,
) -> list[FaultResult]:
    """Run the full fault injection test suite."""
    if architectures is None:
        architectures = [Architecture.MCP, Architecture.A2A, Architecture.HYBRID]
    if scenarios is None:
        scenarios = FAULT_SCENARIOS

    results: list[FaultResult] = []
    total = len(architectures) * len(scenarios)
    completed = 0

    print(f"Running {total} fault injection tests\n")

    for arch in architectures:
        for scenario in scenarios:
            completed += 1
            label = f"[{completed}/{total}] {arch.value:6s} | {scenario.mode.value:15s} | {scenario.target.value}"
            print(f"{label}...", end=" ", flush=True)

            result = await run_fault_test(arch, scenario)

            status = "RECOVERED" if result.produced_response else "FAILED"
            completeness = f"{result.response_completeness:.0%}"
            print(f"{status} (completeness: {completeness}, {result.latency_ms:.0f}ms)")

            results.append(result)

    # Save results
    _save_fault_results(results)

    # Print summary
    _print_fault_summary(results)

    return results


def _save_fault_results(results: list[FaultResult]):
    """Save fault test results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / "fault_injection_results.json"

    data = []
    for r in results:
        data.append({
            "architecture": r.architecture.value,
            "fault_mode": r.fault_config.mode.value,
            "fault_target": r.fault_config.target.value,
            "fault_description": r.fault_config.description,
            "query_id": r.query_id,
            "query_text": r.query_text,
            "produced_response": r.produced_response,
            "partial_data_recovered": r.partial_data_recovered,
            "fault_reported": r.fault_reported,
            "response_completeness": r.response_completeness,
            "latency_ms": r.latency_ms,
            "error_message": r.error_message,
        })

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nResults saved to {filepath}")


def _print_fault_summary(results: list[FaultResult]):
    """Print a summary table of fault injection results."""
    print("\n" + "=" * 80)
    print("FAULT INJECTION SUMMARY")
    print("=" * 80)

    for arch in [Architecture.MCP, Architecture.A2A, Architecture.HYBRID]:
        arch_results = [r for r in results if r.architecture == arch]
        if not arch_results:
            continue

        print(f"\n--- {arch.value.upper()} ---")
        total = len(arch_results)
        recovered = sum(1 for r in arch_results if r.produced_response)
        reported = sum(1 for r in arch_results if r.fault_reported)
        avg_completeness = sum(r.response_completeness for r in arch_results) / total if total else 0

        print(f"  Recovery rate:    {recovered}/{total} ({recovered/total*100:.0f}%)")
        print(f"  Fault reporting:  {reported}/{total} ({reported/total*100:.0f}%)")
        print(f"  Avg completeness: {avg_completeness:.0%}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run fault injection tests")
    parser.add_argument("--arch", nargs="+", choices=["mcp", "a2a", "hybrid"])
    args = parser.parse_args()

    architectures = None
    if args.arch:
        architectures = [Architecture(a) for a in args.arch]

    await run_fault_suite(architectures=architectures)


if __name__ == "__main__":
    asyncio.run(main())
