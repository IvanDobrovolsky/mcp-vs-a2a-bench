"""Streamlit UI: run queries, see results, compare architectures."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="mcp-vs-a2a-bench",
    page_icon="🔬",
    layout="wide",
)

# ── Sidebar: API Keys ──

with st.sidebar:
    st.header("API Keys")
    st.caption("Keys are only used for this session and never stored.")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required. Get one at console.anthropic.com",
    )
    github_token = st.text_input(
        "GitHub Token (optional)",
        value=os.getenv("GITHUB_TOKEN", ""),
        type="password",
        help="Raises rate limit from 60 to 5,000 req/hr. Get one at github.com/settings/tokens",
    )

    # Apply keys to environment for this session
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token

    has_key = bool(anthropic_key)
    if has_key:
        st.success("Anthropic key set")
    else:
        st.warning("Enter your Anthropic API key to run queries")

    if github_token:
        st.success("GitHub token set")

    st.divider()
    st.markdown("""
**[GitHub Repo](https://github.com/IvanDobrovolsky/mcp-vs-a2a-bench)**

MIT License
    """)

# ── Imports (after env is set) ──

from shared.models import Architecture, BenchmarkResult, QueryComplexity
from hybrid.router import classify_query

# ── State ──

if "results" not in st.session_state:
    st.session_state.results = []


# ── Helpers ──

def run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def execute_query(query: str, architecture: str) -> BenchmarkResult:
    complexity = classify_query(query)
    if architecture == "MCP":
        from mcp_only.agent import run_query
        return await run_query(query, complexity=complexity)
    elif architecture == "A2A":
        from a2a_multi.coordinator import run_query
        return await run_query(query, complexity=complexity)
    elif architecture == "Hybrid":
        from hybrid.coordinator import run_query
        return await run_query(query, complexity=complexity)
    else:
        raise ValueError(f"Unknown architecture: {architecture}")


def make_metrics_comparison(results):
    archs, latencies, tokens, llm_calls, api_calls, costs = [], [], [], [], [], []
    for r in results:
        archs.append(r.architecture.value.upper())
        latencies.append(r.latency_ms / 1000)
        tokens.append(r.total_tokens)
        llm_calls.append(r.llm_calls)
        api_calls.append(r.api_calls)
        costs.append(r.cost_usd)

    fig = go.Figure(data=[
        go.Bar(name="Latency (s)", x=archs, y=latencies, marker_color="#FF6B6B"),
        go.Bar(name="Tokens (k)", x=archs, y=[t / 1000 for t in tokens], marker_color="#4ECDC4"),
        go.Bar(name="LLM Calls", x=archs, y=llm_calls, marker_color="#45B7D1"),
        go.Bar(name="API Calls", x=archs, y=api_calls, marker_color="#96CEB4"),
        go.Bar(name="Cost ($)", x=archs, y=costs, marker_color="#FFEAA7"),
    ])
    fig.update_layout(barmode="group", title="Architecture Metrics Comparison",
                      template="plotly_white", height=350)
    return fig


EXAMPLE_QUERIES = {
    "Simple (MCP wins)": [
        "How many stars does React have?",
        "What's the weekly npm download count for express?",
        "Are there any critical vulnerabilities in lodash?",
    ],
    "Medium (close race)": [
        "Give me a full health report on Express.js",
        "Is Deno a safer alternative to Node.js?",
        "Is Flask still relevant? Check all health indicators",
    ],
    "Complex (A2A wins)": [
        "Compare React vs Vue vs Svelte across all health metrics",
        "Rank the top 5 Node.js web frameworks by overall project health",
        "Full ecosystem comparison: Next.js vs Nuxt vs SvelteKit",
    ],
}

# ── UI ──

st.title("mcp-vs-a2a-bench")
st.markdown("**Open Source Health Analyzer** — The first empirical benchmark comparing MCP and A2A agent communication protocols")

# ── Tabs ──
tab_query, tab_benchmark, tab_results, tab_complexity = st.tabs([
    "Query", "Benchmark Suite", "Previous Results", "Code Complexity"
])

# ═══════════════════════════════════════════════════════
# TAB: Query
# ═══════════════════════════════════════════════════════
with tab_query:
    if not has_key:
        st.info("Enter your Anthropic API key in the sidebar to run queries. "
                "The Code Complexity and Previous Results tabs work without a key.")
    else:
        col1, col2 = st.columns([1, 3])

        with col1:
            arch_options = ["MCP", "A2A", "Hybrid", "All (Compare)"]
            selected_arch = st.radio("Architecture", arch_options, horizontal=False)

            st.markdown("---")
            st.caption(
                "**MCP** — single agent, 4 tool servers\n\n"
                "**A2A** — coordinator + 4 HTTP agent servers\n\n"
                "**Hybrid** — routes simple→MCP, complex→A2A"
            )

        with col2:
            query = st.text_input(
                "Query",
                placeholder="e.g., Compare React vs Vue vs Svelte — which project is healthiest?",
            )

            with st.expander("Example queries"):
                for category, queries in EXAMPLE_QUERIES.items():
                    st.markdown(f"**{category}:**")
                    for q in queries:
                        if st.button(q, key=q, use_container_width=True):
                            st.session_state["_query"] = q
                            st.rerun()

            if "_query" in st.session_state:
                query = st.session_state.pop("_query")

            run_query_btn = st.button("Run Query", type="primary", use_container_width=True)

        if run_query_btn and query:
            detected = classify_query(query)
            st.info(f"Detected complexity: **{detected.value}**")

            if selected_arch == "All (Compare)":
                architectures = ["MCP", "A2A", "Hybrid"]
            else:
                architectures = [selected_arch]

            results_this_run = []

            for arch in architectures:
                with st.status(f"Running {arch}...", expanded=True) as status:
                    st.write("Parsing query intent...")
                    st.write("Connecting to data sources...")
                    try:
                        result = run_async(execute_query(query, arch))
                        results_this_run.append(result)
                        st.session_state.results.append(result)
                        status.update(label=f"{arch}: {result.latency_ms:.0f}ms | ${result.cost_usd:.4f}", state="complete")
                    except Exception as e:
                        st.error(f"{arch} failed: {e}")
                        status.update(label=f"{arch}: Failed", state="error")

            if results_this_run:
                st.subheader("Results")

                result_tabs = st.tabs([r.architecture.value.upper() for r in results_this_run])
                for rtab, result in zip(result_tabs, results_this_run):
                    with rtab:
                        st.markdown(result.response_text)
                        mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
                        mcol1.metric("Latency", f"{result.latency_ms / 1000:.1f}s")
                        mcol2.metric("Tokens", f"{result.total_tokens:,}")
                        mcol3.metric("LLM Calls", result.llm_calls)
                        mcol4.metric("API Calls", result.api_calls)
                        mcol5.metric("Cost", f"${result.cost_usd:.4f}")

                if len(results_this_run) > 1:
                    st.subheader("Metrics Comparison")
                    fig = make_metrics_comparison(results_this_run)
                    st.plotly_chart(fig, use_container_width=True)

        elif run_query_btn and not query:
            st.warning("Please enter a query.")

# ═══════════════════════════════════════════════════════
# TAB: Benchmark Suite
# ═══════════════════════════════════════════════════════
with tab_benchmark:
    st.subheader("Benchmark Suite")
    st.markdown("Run 30 queries x 3 architectures x N runs. Includes fault injection and hallucination detection.")

    if not has_key:
        st.info("Enter your Anthropic API key in the sidebar to run benchmarks.")
    else:
        bcol1, bcol2 = st.columns(2)
        num_runs = bcol1.number_input("Runs per query", min_value=1, max_value=30, value=1)
        run_faults = bcol2.checkbox("Include fault injection tests", value=True)

        est_cost = 30 * 3 * num_runs * 0.03
        st.caption(f"Estimated: ~{30 * 3 * num_runs} LLM calls | ~${est_cost:.0f} cost | ~{num_runs * 30} minutes")

        if st.button("Start Benchmark", type="primary"):
            with st.spinner("Running benchmark..."):
                from benchmark.run_benchmark import run_benchmark
                results = run_async(run_benchmark(runs=num_runs))
                st.success(f"Benchmark complete! {len(results)} results collected.")

            import pandas as pd
            from benchmark.analyze_results import generate_latency_chart, generate_token_chart, generate_cost_chart

            df = pd.DataFrame([r.model_dump() for r in results])

            col1, col2 = st.columns(2)
            with col1:
                fig1 = generate_latency_chart(df)
                st.plotly_chart(fig1, use_container_width=True)
            with col2:
                fig2 = generate_token_chart(df)
                st.plotly_chart(fig2, use_container_width=True)

            fig3 = generate_cost_chart(df)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True)

            if run_faults:
                with st.spinner("Running fault injection tests..."):
                    from benchmark.fault_injection import run_fault_suite
                    fault_results = run_async(run_fault_suite())

                st.subheader("Fault Injection Results")
                for arch in ["mcp", "a2a", "hybrid"]:
                    arch_results = [r for r in fault_results if r.architecture.value == arch]
                    if not arch_results:
                        continue
                    total = len(arch_results)
                    recovered = sum(1 for r in arch_results if r.produced_response)
                    st.metric(
                        f"{arch.upper()} Recovery Rate",
                        f"{recovered}/{total} ({recovered/total*100:.0f}%)",
                    )

# ═══════════════════════════════════════════════════════
# TAB: Previous Results
# ═══════════════════════════════════════════════════════
with tab_results:
    results_file = Path("benchmark/results/benchmark_results.json")
    fault_file = Path("benchmark/results/fault_injection_results.json")
    hallucination_file = Path("benchmark/results/hallucination_results.json")

    if results_file.exists():
        if st.button("Load Benchmark Results"):
            import pandas as pd
            from benchmark.analyze_results import (
                compute_summaries,
                generate_latency_chart,
                generate_token_chart,
                generate_cost_chart,
            )

            with open(results_file) as f:
                data = json.load(f)
            df = pd.DataFrame(data)

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(generate_latency_chart(df), use_container_width=True)
            with col2:
                st.plotly_chart(generate_token_chart(df), use_container_width=True)

            cost_fig = generate_cost_chart(df)
            if cost_fig:
                st.plotly_chart(cost_fig, use_container_width=True)

            st.subheader("Summary Statistics")
            summaries = compute_summaries(df)
            summary_df = pd.DataFrame([s.model_dump() for s in summaries])
            st.dataframe(summary_df, use_container_width=True)

    if fault_file.exists():
        with st.expander("Fault Injection Results"):
            with open(fault_file) as f:
                fault_data = json.load(f)
            import pandas as pd
            st.dataframe(pd.DataFrame(fault_data), use_container_width=True)

    if hallucination_file.exists():
        with st.expander("Hallucination Detection Results"):
            with open(hallucination_file) as f:
                halluc_data = json.load(f)
            import pandas as pd
            summary_rows = []
            for r in halluc_data:
                summary_rows.append({
                    "Query": r["query_text"][:60],
                    "Architecture": r["architecture"],
                    "Claims": r["total_claims"],
                    "Verified": r["verified_claims"],
                    "Hallucinated": r["hallucinated_claims"],
                    "Rate": f"{r['hallucination_rate']:.0%}",
                })
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

    if not results_file.exists() and not fault_file.exists():
        st.info("No previous results found. Run a benchmark first.")

# ═══════════════════════════════════════════════════════
# TAB: Code Complexity
# ═══════════════════════════════════════════════════════
with tab_complexity:
    st.subheader("Code Complexity Comparison")

    from benchmark.loc_counter import measure_all

    complexity_results = measure_all()

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    for col, (arch, m) in zip([col1, col2, col3], complexity_results.items()):
        with col:
            st.markdown(f"### {arch.upper()}")
            st.metric("Total LOC", m.total_loc)
            st.metric("Architecture-specific LOC", m.specific_loc)
            st.metric("Files", m.total_files)
            st.metric("Functions", m.total_functions)
            st.metric("Avg Cyclomatic Complexity", f"{m.avg_cyclomatic_complexity:.1f}")

    # LOC bar chart
    fig = go.Figure(data=[
        go.Bar(
            name="Architecture-specific",
            x=[a.upper() for a in complexity_results],
            y=[m.specific_loc for m in complexity_results.values()],
            marker_color="#FF6B6B",
        ),
        go.Bar(
            name="Shared",
            x=[a.upper() for a in complexity_results],
            y=[m.shared_loc for m in complexity_results.values()],
            marker_color="#96CEB4",
        ),
    ])
    fig.update_layout(
        barmode="stack",
        title="Lines of Code by Architecture",
        yaxis_title="Lines of Code",
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # File breakdown
    with st.expander("Per-file breakdown"):
        import pandas as pd
        for arch, m in complexity_results.items():
            st.markdown(f"**{arch.upper()}**")
            file_data = [{
                "File": fm.path,
                "Code LOC": fm.code_lines,
                "Functions": fm.functions,
                "CC": fm.cyclomatic_complexity,
            } for fm in sorted(m.file_metrics, key=lambda f: -f.code_lines)]
            st.dataframe(pd.DataFrame(file_data), use_container_width=True)

# ── Footer ──

st.divider()
st.caption(
    "mcp-vs-a2a-bench — The first empirical benchmark comparing MCP and A2A agent communication protocols. "
    "MIT License. [GitHub](https://github.com/IvanDobrovolsky/mcp-vs-a2a-bench)"
)
