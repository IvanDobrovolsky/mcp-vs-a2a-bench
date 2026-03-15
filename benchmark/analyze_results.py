"""Generate comparison tables and charts from benchmark results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import Architecture, BenchmarkSummary, QueryComplexity

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent.parent / "paper" / "figures"


def load_results(filename: str = "benchmark_results.json") -> pd.DataFrame:
    """Load benchmark results into a DataFrame."""
    filepath = RESULTS_DIR / filename
    with open(filepath) as f:
        data = json.load(f)
    return pd.DataFrame(data)


def compute_summaries(df: pd.DataFrame) -> list[BenchmarkSummary]:
    """Compute summary statistics per architecture per complexity."""
    summaries = []

    for arch in ["mcp", "a2a", "hybrid"]:
        for comp in ["simple", "medium", "complex"]:
            subset = df[(df["architecture"] == arch) & (df["complexity"] == comp)]
            if subset.empty:
                continue

            successful = subset[subset["success"] == True]

            summaries.append(BenchmarkSummary(
                architecture=Architecture(arch),
                complexity=QueryComplexity(comp),
                avg_latency_ms=float(successful["latency_ms"].mean()) if not successful.empty else 0,
                median_latency_ms=float(successful["latency_ms"].median()) if not successful.empty else 0,
                p95_latency_ms=float(successful["latency_ms"].quantile(0.95)) if not successful.empty else 0,
                avg_tokens=float(successful["total_tokens"].mean()) if not successful.empty else 0,
                avg_llm_calls=float(successful["llm_calls"].mean()) if not successful.empty else 0,
                avg_api_calls=float(successful["api_calls"].mean()) if not successful.empty else 0,
                success_rate=float(successful.shape[0] / subset.shape[0] * 100) if not subset.empty else 0,
                error_recovery_rate=float(
                    subset[subset["error_recovery"] == True].shape[0] / subset.shape[0] * 100
                ) if not subset.empty else 0,
                total_runs=int(subset.shape[0]),
            ))

    return summaries


def generate_latency_chart(df: pd.DataFrame, output_path: Path | None = None):
    """Generate latency comparison chart (the key paper figure)."""
    successful = df[df["success"] == True].copy()

    summary = successful.groupby(["architecture", "complexity"]).agg(
        avg_latency=("latency_ms", "mean"),
        std_latency=("latency_ms", "std"),
    ).reset_index()

    # Order complexity
    complexity_order = ["simple", "medium", "complex"]
    summary["complexity"] = pd.Categorical(
        summary["complexity"], categories=complexity_order, ordered=True
    )
    summary = summary.sort_values("complexity")

    fig = px.line(
        summary,
        x="complexity",
        y="avg_latency",
        color="architecture",
        markers=True,
        title="Latency by Query Complexity",
        labels={
            "avg_latency": "Average Latency (ms)",
            "complexity": "Query Complexity",
            "architecture": "Architecture",
        },
        color_discrete_map={"mcp": "#FF6B6B", "a2a": "#4ECDC4", "hybrid": "#45B7D1"},
    )
    fig.update_layout(
        template="plotly_white",
        font=dict(size=14),
        legend=dict(x=0.02, y=0.98),
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(str(output_path))
        fig.write_html(str(output_path.with_suffix(".html")))

    return fig


def generate_token_chart(df: pd.DataFrame, output_path: Path | None = None):
    """Generate token usage comparison chart."""
    successful = df[df["success"] == True].copy()

    summary = successful.groupby(["architecture", "complexity"]).agg(
        avg_tokens=("total_tokens", "mean"),
    ).reset_index()

    complexity_order = ["simple", "medium", "complex"]
    summary["complexity"] = pd.Categorical(
        summary["complexity"], categories=complexity_order, ordered=True
    )
    summary = summary.sort_values("complexity")

    fig = px.bar(
        summary,
        x="complexity",
        y="avg_tokens",
        color="architecture",
        barmode="group",
        title="Token Usage by Query Complexity",
        labels={
            "avg_tokens": "Average Tokens",
            "complexity": "Query Complexity",
            "architecture": "Architecture",
        },
        color_discrete_map={"mcp": "#FF6B6B", "a2a": "#4ECDC4", "hybrid": "#45B7D1"},
    )
    fig.update_layout(template="plotly_white", font=dict(size=14))

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(str(output_path))
        fig.write_html(str(output_path.with_suffix(".html")))

    return fig


def generate_all_charts(df: pd.DataFrame):
    """Generate all publication-ready charts."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    generate_latency_chart(df, FIGURES_DIR / "latency_comparison.png")
    generate_token_chart(df, FIGURES_DIR / "token_comparison.png")

    # Summary table
    summaries = compute_summaries(df)
    summary_data = [s.model_dump() for s in summaries]
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(FIGURES_DIR / "summary_table.csv", index=False)

    print(f"Charts saved to {FIGURES_DIR}")
    print("\nSummary Table:")
    print(summary_df.to_string(index=False))


def generate_radar_chart(project_data: dict, output_path: Path | None = None):
    """Generate a radar chart for project health comparison."""
    categories = ["Stars", "Downloads", "Security", "Community", "Activity"]

    fig = go.Figure()

    for project_name, scores in project_data.items():
        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],  # Close the polygon
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
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze benchmark results")
    parser.add_argument("--input", default="benchmark_results.json",
                        help="Input results file")
    args = parser.parse_args()

    df = load_results(args.input)
    generate_all_charts(df)


if __name__ == "__main__":
    main()
