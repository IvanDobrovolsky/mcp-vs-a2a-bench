"""Execute all queries x 3 architectures x 5 runs = 450 total runs."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import Architecture, BenchmarkResult, QueryComplexity

RESULTS_DIR = Path(__file__).parent / "results"
QUERIES_FILE = Path(__file__).parent / "queries.json"

RUNS_PER_QUERY = 5


async def run_single(
    arch: Architecture,
    query: dict,
    run_number: int,
) -> BenchmarkResult:
    """Run a single query on a single architecture."""
    complexity = QueryComplexity(query["complexity"])
    query_text = query["text"]
    query_id = query["id"]

    if arch == Architecture.MCP:
        from mcp_only.agent import run_query
    elif arch == Architecture.A2A:
        from a2a_multi.coordinator import run_query
    else:
        from hybrid.coordinator import run_query

    try:
        result = await run_query(
            query_text,
            query_id=query_id,
            complexity=complexity,
            run_number=run_number,
        )
        return result
    except Exception as e:
        return BenchmarkResult(
            query_id=query_id,
            query_text=query_text,
            complexity=complexity,
            architecture=arch,
            run_number=run_number,
            success=False,
            error_message=str(e),
        )


async def run_benchmark(
    architectures: list[Architecture] | None = None,
    query_ids: list[int] | None = None,
    runs: int = RUNS_PER_QUERY,
    output_file: str | None = None,
) -> list[BenchmarkResult]:
    """Run the full benchmark suite."""
    if architectures is None:
        architectures = [Architecture.MCP, Architecture.A2A, Architecture.HYBRID]

    with open(QUERIES_FILE) as f:
        all_queries = json.load(f)["queries"]

    if query_ids:
        queries = [q for q in all_queries if q["id"] in query_ids]
    else:
        queries = all_queries

    total = len(queries) * len(architectures) * runs
    print(f"Running {total} total executions:")
    print(f"  {len(queries)} queries x {len(architectures)} architectures x {runs} runs\n")

    results: list[BenchmarkResult] = []
    completed = 0

    for query in queries:
        for arch in architectures:
            for run_num in range(1, runs + 1):
                completed += 1
                label = f"[{completed}/{total}] Q{query['id']} ({query['complexity']}) | {arch.value} | run {run_num}"
                print(f"{label}...", end=" ", flush=True)

                start = time.perf_counter()
                result = await run_single(arch, query, run_num)
                elapsed = time.perf_counter() - start

                status = "OK" if result.success else f"FAIL: {result.error_message[:50]}"
                print(f"{status} ({elapsed:.1f}s)")

                results.append(result)

                # Save incrementally
                _save_results(results, output_file)

    print(f"\nBenchmark complete. {len(results)} results saved.")
    return results


def _save_results(results: list[BenchmarkResult], output_file=None):
    """Save results to JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / (output_file or "benchmark_results.json")
    with open(filepath, "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2, default=str)


async def main():
    """CLI entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(description="Run MCP vs A2A benchmark")
    parser.add_argument("--arch", nargs="+", choices=["mcp", "a2a", "hybrid"],
                        help="Architectures to test (default: all)")
    parser.add_argument("--queries", nargs="+", type=int,
                        help="Query IDs to run (default: all)")
    parser.add_argument("--runs", type=int, default=RUNS_PER_QUERY,
                        help=f"Runs per query (default: {RUNS_PER_QUERY})")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (default: benchmark_results.json)")
    parser.add_argument("--fault-injection", action="store_true",
                        help="Also run fault injection tests after benchmark")
    parser.add_argument("--hallucination-check", action="store_true",
                        help="Run hallucination detection on results after benchmark")
    parser.add_argument("--loc", action="store_true",
                        help="Print code complexity metrics")
    parser.add_argument("--full", action="store_true",
                        help="Run everything: benchmark + fault injection + hallucination check + LOC")

    args = parser.parse_args()

    architectures = None
    if args.arch:
        architectures = [Architecture(a) for a in args.arch]

    run_full = args.full

    # Main benchmark
    await run_benchmark(
        architectures=architectures,
        query_ids=args.queries,
        runs=args.runs,
        output_file=args.output,
    )

    # Fault injection
    if args.fault_injection or run_full:
        print("\n" + "=" * 80)
        print("FAULT INJECTION TESTS")
        print("=" * 80 + "\n")
        from benchmark.fault_injection import run_fault_suite
        await run_fault_suite(architectures=architectures)

    # Hallucination check
    if args.hallucination_check or run_full:
        print("\n" + "=" * 80)
        print("HALLUCINATION DETECTION")
        print("=" * 80 + "\n")
        from benchmark.hallucination_detector import check_benchmark_results
        input_file = args.output or "benchmark_results.json"
        await check_benchmark_results(input_file)

    # LOC metrics
    if args.loc or run_full:
        print("\n")
        from benchmark.loc_counter import measure_all, print_report, save_report
        results = measure_all()
        print_report(results)
        save_report(results)


if __name__ == "__main__":
    asyncio.run(main())
