"""Architecture C: Hybrid coordinator that routes by query complexity."""

from __future__ import annotations

import asyncio
import sys

from hybrid.router import classify_query
from shared.metrics import MetricsCollector
from shared.models import Architecture, BenchmarkResult, QueryComplexity


async def run_query(
    query: str,
    query_id: int = 0,
    complexity: QueryComplexity = QueryComplexity.SIMPLE,
    run_number: int = 1,
) -> BenchmarkResult:
    """Run a query through the hybrid architecture.

    Routes simple queries through MCP (less overhead) and
    complex queries through A2A (parallel delegation).
    """
    metrics = MetricsCollector()
    metrics.start()

    # Classify query complexity
    detected_complexity = classify_query(query)

    if detected_complexity == QueryComplexity.SIMPLE:
        # Route through MCP-only (less overhead for simple queries)
        from mcp_only.agent import run_query as mcp_run
        result = await mcp_run(query, query_id, complexity, run_number)
        # Override architecture label
        result.architecture = Architecture.HYBRID
        result.metadata["routing"] = "mcp"
        result.metadata["detected_complexity"] = detected_complexity.value
        return result
    else:
        # Route through A2A (parallel delegation for complex queries)
        from a2a_multi.coordinator import run_query as a2a_run
        result = await a2a_run(query, query_id, complexity, run_number)
        # Override architecture label
        result.architecture = Architecture.HYBRID
        result.metadata["routing"] = "a2a"
        result.metadata["detected_complexity"] = detected_complexity.value
        return result


async def main():
    """CLI entry point."""
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How many stars does React have?"
    print(f"Query: {query}\n")
    result = await run_query(query)
    routing = result.metadata.get("routing", "unknown")
    detected = result.metadata.get("detected_complexity", "unknown")
    print(f"Routing: {routing} (detected: {detected})\n")
    print(f"Response:\n{result.response_text}\n")
    print(f"Latency: {result.latency_ms:.0f}ms | Tokens: {result.total_tokens} | "
          f"LLM calls: {result.llm_calls} | API calls: {result.api_calls}")


if __name__ == "__main__":
    asyncio.run(main())
