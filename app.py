"""Streamlit UI: run queries, see results, compare architectures."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Must be first Streamlit call
st.set_page_config(
    page_title="mcp-vs-a2a-bench",
    page_icon="🔬",
    layout="wide",
)

from shared.models import Architecture, BenchmarkResult, QueryComplexity
from hybrid.router import classify_query

# ── State ──

if "results" not in st.session_state:
    st.session_state.results = []
if "running" not in st.session_state:
    st.session_state.running = False
if "pipeline_log" not in st.session_state:
    st.session_state.pipeline_log = []


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
    """Execute a query on the selected architecture."""
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


def make_radar_chart(reports: dict[str, dict]) -> go.Figure:
    """Create a radar chart from project health data."""
    categories = ["Stars", "Downloads", "Security", "Community", "Activity"]

    fig = go.Figure()

    for project_name, data in reports.items():
        # Normalize scores to 0-100
        github = data.get("github", {})
        npm = data.get("npm", {})
        osv = data.get("osv", {})
        so = data.get("stackoverflow", {})

        scores = [
            min(100, (github.get("stars", 0) / 2000)),  # Stars (normalized)
            min(100, (npm.get("weekly_downloads", 0) / 100000)),  # Downloads
            max(0, 100 - osv.get("total_vulnerabilities", 0) * 10),  # Security (inverse)
            min(100, (so.get("total_questions", 0) / 5000)),  # Community
            min(100, (github.get("recent_commits_30d", 0) / 5)),  # Activity
        ]

        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=project_name,
            opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        title="Project Health Radar",
        template="plotly_white",
        height=400,
    )
    return fig


def make_metrics_comparison(results: list[BenchmarkResult]) -> go.Figure:
    """Create a metrics comparison table/chart."""
    if not results:
        return go.Figure()

    archs = []
    latencies = []
    tokens = []
    llm_calls = []
    api_calls = []

    for r in results:
        archs.append(r.architecture.value.upper())
        latencies.append(r.latency_ms / 1000)  # Convert to seconds
        tokens.append(r.total_tokens)
        llm_calls.append(r.llm_calls)
        api_calls.append(r.api_calls)

    fig = go.Figure(data=[
        go.Bar(name="Latency (s)", x=archs, y=latencies, marker_color="#FF6B6B"),
        go.Bar(name="Tokens (k)", x=archs, y=[t / 1000 for t in tokens], marker_color="#4ECDC4"),
        go.Bar(name="LLM Calls", x=archs, y=llm_calls, marker_color="#45B7D1"),
        go.Bar(name="API Calls", x=archs, y=api_calls, marker_color="#96CEB4"),
    ])
    fig.update_layout(
        barmode="group",
        title="Architecture Metrics Comparison",
        template="plotly_white",
        height=350,
    )
    return fig


# ── Benchmark Queries ──

EXAMPLE_QUERIES = {
    "Simple": [
        "How many stars does React have?",
        "What's the weekly npm download count for express?",
        "Are there any critical vulnerabilities in lodash?",
    ],
    "Medium": [
        "Give me a full health report on Express.js",
        "Is Deno a safer alternative to Node.js?",
        "Is Flask still relevant? Check all health indicators",
    ],
    "Complex": [
        "Compare React vs Vue vs Svelte across all health metrics",
        "Rank the top 5 Node.js web frameworks by overall project health",
        "Full ecosystem comparison: Next.js vs Nuxt vs SvelteKit",
    ],
}


# ── UI ──

st.title("mcp-vs-a2a-bench")
st.markdown("**Open Source Health Analyzer** — The first empirical benchmark comparing MCP and A2A agent communication protocols")

st.divider()

# Architecture selector
col1, col2 = st.columns([1, 3])

with col1:
    arch_options = ["MCP", "A2A", "Hybrid", "All (Compare)"]
    selected_arch = st.radio("Architecture", arch_options, horizontal=False)

with col2:
    # Query input
    query = st.text_input(
        "Query",
        placeholder="e.g., Compare React vs Vue vs Svelte — which project is healthiest?",
    )

    # Example queries
    with st.expander("Example queries"):
        for category, queries in EXAMPLE_QUERIES.items():
            st.markdown(f"**{category}:**")
            for q in queries:
                if st.button(q, key=q, use_container_width=True):
                    st.session_state["_query"] = q
                    st.rerun()

    # Check if example query was selected
    if "_query" in st.session_state:
        query = st.session_state.pop("_query")
        st.session_state["query_input"] = query

    # Action buttons
    bcol1, bcol2 = st.columns(2)
    run_query_btn = bcol1.button("Run Query", type="primary", use_container_width=True)
    run_benchmark_btn = bcol2.button("Run Benchmark Suite", use_container_width=True)

st.divider()

# ── Query Execution ──

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
            st.write(f"Parsing query intent...")
            st.write(f"Connecting to data sources...")

            try:
                result = run_async(execute_query(query, arch))
                results_this_run.append(result)
                st.session_state.results.append(result)
                status.update(label=f"{arch}: {result.latency_ms:.0f}ms", state="complete")
            except Exception as e:
                st.error(f"{arch} failed: {e}")
                status.update(label=f"{arch}: Failed", state="error")

    if results_this_run:
        # Display results
        st.subheader("Results")

        tabs = st.tabs([r.architecture.value.upper() for r in results_this_run])
        for tab, result in zip(tabs, results_this_run):
            with tab:
                st.markdown(result.response_text)

                mcol1, mcol2, mcol3, mcol4 = st.columns(4)
                mcol1.metric("Latency", f"{result.latency_ms / 1000:.1f}s")
                mcol2.metric("Tokens", f"{result.total_tokens:,}")
                mcol3.metric("LLM Calls", result.llm_calls)
                mcol4.metric("API Calls", result.api_calls)

        # Comparison chart if multiple architectures
        if len(results_this_run) > 1:
            st.subheader("Metrics Comparison")
            fig = make_metrics_comparison(results_this_run)
            st.plotly_chart(fig, use_container_width=True)

elif run_query_btn and not query:
    st.warning("Please enter a query.")

# ── Benchmark Suite ──

if run_benchmark_btn:
    st.subheader("Benchmark Suite")
    st.warning("This will run 30 queries x 3 architectures x 5 runs = 450 API calls. This costs real money.")

    if st.button("Confirm and Start"):
        with st.spinner("Running benchmark..."):
            from benchmark.run_benchmark import run_benchmark
            results = run_async(run_benchmark(runs=1))  # Start with 1 run for testing
            st.success(f"Benchmark complete! {len(results)} results collected.")

            # Generate charts
            import pandas as pd
            from benchmark.analyze_results import generate_latency_chart, generate_token_chart

            df = pd.DataFrame([r.model_dump() for r in results])
            fig1 = generate_latency_chart(df)
            fig2 = generate_token_chart(df)

            st.plotly_chart(fig1, use_container_width=True)
            st.plotly_chart(fig2, use_container_width=True)

# ── Historical Results ──

results_file = Path("benchmark/results/benchmark_results.json")
if results_file.exists():
    with st.expander("Load Previous Benchmark Results"):
        if st.button("Load Results"):
            import pandas as pd
            from benchmark.analyze_results import (
                compute_summaries,
                generate_latency_chart,
                generate_token_chart,
            )

            with open(results_file) as f:
                data = json.load(f)
            df = pd.DataFrame(data)

            st.subheader("Latency Comparison")
            fig1 = generate_latency_chart(df)
            st.plotly_chart(fig1, use_container_width=True)

            st.subheader("Token Usage")
            fig2 = generate_token_chart(df)
            st.plotly_chart(fig2, use_container_width=True)

            st.subheader("Summary Statistics")
            summaries = compute_summaries(df)
            summary_df = pd.DataFrame([s.model_dump() for s in summaries])
            st.dataframe(summary_df, use_container_width=True)

# ── Footer ──

st.divider()
st.caption(
    "mcp-vs-a2a-bench — The first empirical benchmark comparing MCP and A2A agent communication protocols. "
    "MIT License."
)
