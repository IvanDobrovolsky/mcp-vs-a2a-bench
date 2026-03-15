"""Generate comparison tables, charts, and statistical analysis from benchmark results.

Statistical methods:
- 95% confidence intervals via bootstrap (non-parametric, no normality assumption)
- Wilcoxon signed-rank test for pairwise architecture comparisons
- Cliff's delta for effect size (non-parametric alternative to Cohen's d)
- Bonferroni correction for multiple comparisons
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import Architecture, BenchmarkSummary, QueryComplexity

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent.parent / "paper" / "figures"

ARCH_COLORS = {"mcp": "#FF6B6B", "a2a": "#4ECDC4", "hybrid": "#45B7D1"}
COMPLEXITY_ORDER = ["simple", "medium", "complex"]


# ── Data Loading ──


def load_results(filename: str = "benchmark_results.json") -> pd.DataFrame:
    """Load benchmark results into a DataFrame."""
    filepath = RESULTS_DIR / filename
    with open(filepath) as f:
        data = json.load(f)
    return pd.DataFrame(data)


# ── Statistical Tests ──


def bootstrap_ci(data: np.ndarray, n_bootstrap: int = 10000, ci: float = 0.95) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval.

    Returns (mean, ci_lower, ci_upper).
    Non-parametric — makes no distributional assumptions.
    """
    if len(data) < 2:
        mean = float(np.mean(data))
        return mean, mean, mean

    rng = np.random.default_rng(42)
    boot_means = np.array([
        np.mean(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_bootstrap)
    ])

    alpha = 1 - ci
    lower = float(np.percentile(boot_means, 100 * alpha / 2))
    upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    mean = float(np.mean(data))

    return mean, lower, upper


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> tuple[float, str]:
    """Compute Cliff's delta effect size (non-parametric).

    Returns (delta, interpretation) where interpretation is one of:
    negligible (|d| < 0.147), small (|d| < 0.33), medium (|d| < 0.474), large
    """
    n_x, n_y = len(x), len(y)
    if n_x == 0 or n_y == 0:
        return 0.0, "negligible"

    # Count dominance
    more = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    delta = (more - less) / (n_x * n_y)

    # Interpret
    abs_d = abs(delta)
    if abs_d < 0.147:
        interpretation = "negligible"
    elif abs_d < 0.33:
        interpretation = "small"
    elif abs_d < 0.474:
        interpretation = "medium"
    else:
        interpretation = "large"

    return delta, interpretation


def pairwise_comparisons(
    df: pd.DataFrame,
    metric: str = "latency_ms",
    groupby: str = "complexity",
) -> pd.DataFrame:
    """Run Wilcoxon signed-rank tests between all architecture pairs.

    Uses Bonferroni correction for multiple comparisons.
    """
    results = []
    architectures = df["architecture"].unique()
    groups = df[groupby].unique()

    n_comparisons = len(list(combinations(architectures, 2))) * len(groups)

    for group in groups:
        group_df = df[df[groupby] == group]

        for arch_a, arch_b in combinations(architectures, 2):
            data_a = group_df[group_df["architecture"] == arch_a][metric].values
            data_b = group_df[group_df["architecture"] == arch_b][metric].values

            if len(data_a) < 5 or len(data_b) < 5:
                continue

            # Wilcoxon rank-sum (Mann-Whitney U) for independent samples
            try:
                stat, p_value = stats.mannwhitneyu(data_a, data_b, alternative="two-sided")
            except ValueError:
                stat, p_value = 0, 1.0

            # Bonferroni correction
            p_corrected = min(p_value * n_comparisons, 1.0)

            # Effect size
            delta, delta_interp = cliffs_delta(data_a, data_b)

            # Bootstrap CIs for each
            mean_a, ci_a_lo, ci_a_hi = bootstrap_ci(data_a)
            mean_b, ci_b_lo, ci_b_hi = bootstrap_ci(data_b)

            results.append({
                groupby: group,
                "arch_a": arch_a,
                "arch_b": arch_b,
                f"mean_{metric}_a": mean_a,
                f"ci_95_a": f"[{ci_a_lo:.1f}, {ci_a_hi:.1f}]",
                f"mean_{metric}_b": mean_b,
                f"ci_95_b": f"[{ci_b_lo:.1f}, {ci_b_hi:.1f}]",
                "U_statistic": stat,
                "p_value": p_value,
                "p_corrected": p_corrected,
                "significant": p_corrected < 0.05,
                "cliffs_delta": delta,
                "effect_size": delta_interp,
            })

    return pd.DataFrame(results)


# ── Summary Statistics ──


def compute_summaries(df: pd.DataFrame) -> list[BenchmarkSummary]:
    """Compute summary statistics per architecture per complexity."""
    summaries = []

    for arch in ["mcp", "a2a", "hybrid"]:
        for comp in COMPLEXITY_ORDER:
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


# ── Charts ──


def generate_latency_chart(df: pd.DataFrame, output_path: Path | None = None):
    """Generate latency comparison chart with 95% confidence intervals."""
    successful = df[df["success"] == True].copy()

    # Compute CIs per group
    rows = []
    for arch in successful["architecture"].unique():
        for comp in COMPLEXITY_ORDER:
            data = successful[
                (successful["architecture"] == arch) & (successful["complexity"] == comp)
            ]["latency_ms"].values
            if len(data) == 0:
                continue
            mean, ci_lo, ci_hi = bootstrap_ci(data)
            rows.append({
                "architecture": arch,
                "complexity": comp,
                "avg_latency": mean,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "error_minus": mean - ci_lo,
                "error_plus": ci_hi - mean,
            })

    summary = pd.DataFrame(rows)
    summary["complexity"] = pd.Categorical(
        summary["complexity"], categories=COMPLEXITY_ORDER, ordered=True
    )
    summary = summary.sort_values("complexity")

    fig = go.Figure()

    for arch in ["mcp", "a2a", "hybrid"]:
        arch_data = summary[summary["architecture"] == arch]
        if arch_data.empty:
            continue
        fig.add_trace(go.Scatter(
            x=arch_data["complexity"],
            y=arch_data["avg_latency"],
            error_y=dict(
                type="data",
                symmetric=False,
                array=arch_data["error_plus"].values,
                arrayminus=arch_data["error_minus"].values,
            ),
            mode="lines+markers",
            name=arch.upper(),
            line=dict(color=ARCH_COLORS[arch], width=2),
            marker=dict(size=8),
        ))

    fig.update_layout(
        title="Latency by Query Complexity (95% CI)",
        xaxis_title="Query Complexity",
        yaxis_title="Average Latency (ms)",
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
    """Generate token usage comparison chart with confidence intervals."""
    successful = df[df["success"] == True].copy()

    rows = []
    for arch in successful["architecture"].unique():
        for comp in COMPLEXITY_ORDER:
            data = successful[
                (successful["architecture"] == arch) & (successful["complexity"] == comp)
            ]["total_tokens"].values
            if len(data) == 0:
                continue
            mean, ci_lo, ci_hi = bootstrap_ci(data)
            rows.append({
                "architecture": arch,
                "complexity": comp,
                "avg_tokens": mean,
                "error_minus": mean - ci_lo,
                "error_plus": ci_hi - mean,
            })

    summary = pd.DataFrame(rows)
    summary["complexity"] = pd.Categorical(
        summary["complexity"], categories=COMPLEXITY_ORDER, ordered=True
    )

    fig = go.Figure()

    for arch in ["mcp", "a2a", "hybrid"]:
        arch_data = summary[summary["architecture"] == arch]
        if arch_data.empty:
            continue
        fig.add_trace(go.Bar(
            x=arch_data["complexity"],
            y=arch_data["avg_tokens"],
            error_y=dict(
                type="data",
                symmetric=False,
                array=arch_data["error_plus"].values,
                arrayminus=arch_data["error_minus"].values,
            ),
            name=arch.upper(),
            marker_color=ARCH_COLORS[arch],
        ))

    fig.update_layout(
        barmode="group",
        title="Token Usage by Query Complexity (95% CI)",
        xaxis_title="Query Complexity",
        yaxis_title="Average Tokens",
        template="plotly_white",
        font=dict(size=14),
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(str(output_path))
        fig.write_html(str(output_path.with_suffix(".html")))

    return fig


def generate_cost_chart(df: pd.DataFrame, output_path: Path | None = None):
    """Generate cost comparison chart (dollars per query)."""
    successful = df[df["success"] == True].copy()
    if "cost_usd" not in successful.columns:
        return None

    rows = []
    for arch in successful["architecture"].unique():
        for comp in COMPLEXITY_ORDER:
            data = successful[
                (successful["architecture"] == arch) & (successful["complexity"] == comp)
            ]["cost_usd"].values
            if len(data) == 0:
                continue
            mean, ci_lo, ci_hi = bootstrap_ci(data)
            rows.append({
                "architecture": arch,
                "complexity": comp,
                "avg_cost": mean,
                "error_minus": mean - ci_lo,
                "error_plus": ci_hi - mean,
            })

    if not rows:
        return None

    summary = pd.DataFrame(rows)
    summary["complexity"] = pd.Categorical(
        summary["complexity"], categories=COMPLEXITY_ORDER, ordered=True
    )

    fig = go.Figure()
    for arch in ["mcp", "a2a", "hybrid"]:
        arch_data = summary[summary["architecture"] == arch]
        if arch_data.empty:
            continue
        fig.add_trace(go.Bar(
            x=arch_data["complexity"],
            y=arch_data["avg_cost"],
            error_y=dict(
                type="data",
                symmetric=False,
                array=arch_data["error_plus"].values,
                arrayminus=arch_data["error_minus"].values,
            ),
            name=arch.upper(),
            marker_color=ARCH_COLORS[arch],
        ))

    fig.update_layout(
        barmode="group",
        title="Cost per Query by Complexity (95% CI)",
        xaxis_title="Query Complexity",
        yaxis_title="Cost (USD)",
        template="plotly_white",
        font=dict(size=14),
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(str(output_path))
        fig.write_html(str(output_path.with_suffix(".html")))

    return fig


def generate_effect_size_heatmap(df: pd.DataFrame, output_path: Path | None = None):
    """Generate heatmap of Cliff's delta effect sizes across comparisons."""
    comparisons = pairwise_comparisons(df, metric="latency_ms")
    if comparisons.empty:
        return None

    # Pivot for heatmap
    comparisons["pair"] = comparisons["arch_a"] + " vs " + comparisons["arch_b"]

    pivot = comparisons.pivot_table(
        index="pair",
        columns="complexity",
        values="cliffs_delta",
        aggfunc="first",
    )

    # Reorder columns
    ordered_cols = [c for c in COMPLEXITY_ORDER if c in pivot.columns]
    pivot = pivot[ordered_cols]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=[[f"{v:.2f}" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont=dict(size=14),
        colorbar=dict(title="Cliff's δ"),
    ))

    fig.update_layout(
        title="Effect Size: Latency Differences (Cliff's δ)",
        xaxis_title="Query Complexity",
        yaxis_title="Architecture Comparison",
        template="plotly_white",
        font=dict(size=14),
        height=300,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(str(output_path))
        fig.write_html(str(output_path.with_suffix(".html")))

    return fig


def generate_radar_chart(project_data: dict, output_path: Path | None = None):
    """Generate a radar chart for project health comparison."""
    categories = ["Stars", "Downloads", "Security", "Community", "Activity"]

    fig = go.Figure()

    for project_name, scores in project_data.items():
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
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


# ── Full Analysis ──


def generate_all_charts(df: pd.DataFrame):
    """Generate all publication-ready charts and statistical analysis."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating charts...")
    generate_latency_chart(df, FIGURES_DIR / "latency_comparison.png")
    generate_token_chart(df, FIGURES_DIR / "token_comparison.png")
    generate_cost_chart(df, FIGURES_DIR / "cost_comparison.png")
    generate_effect_size_heatmap(df, FIGURES_DIR / "effect_size_heatmap.png")

    # Summary table
    summaries = compute_summaries(df)
    summary_data = [s.model_dump() for s in summaries]
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(FIGURES_DIR / "summary_table.csv", index=False)

    print(f"\nCharts saved to {FIGURES_DIR}")
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(summary_df.to_string(index=False))

    # Pairwise comparisons
    print("\n" + "=" * 80)
    print("PAIRWISE STATISTICAL COMPARISONS (Latency)")
    print("=" * 80)

    latency_comp = pairwise_comparisons(df, metric="latency_ms")
    if not latency_comp.empty:
        latency_comp.to_csv(FIGURES_DIR / "pairwise_latency.csv", index=False)
        for _, row in latency_comp.iterrows():
            sig = "*" if row["significant"] else " "
            print(
                f"  {row['complexity']:8s} | {row['arch_a']:6s} vs {row['arch_b']:6s} | "
                f"p={row['p_corrected']:.4f}{sig} | δ={row['cliffs_delta']:+.3f} ({row['effect_size']})"
            )

    print("\n" + "=" * 80)
    print("PAIRWISE STATISTICAL COMPARISONS (Tokens)")
    print("=" * 80)

    token_comp = pairwise_comparisons(df, metric="total_tokens")
    if not token_comp.empty:
        token_comp.to_csv(FIGURES_DIR / "pairwise_tokens.csv", index=False)
        for _, row in token_comp.iterrows():
            sig = "*" if row["significant"] else " "
            print(
                f"  {row['complexity']:8s} | {row['arch_a']:6s} vs {row['arch_b']:6s} | "
                f"p={row['p_corrected']:.4f}{sig} | δ={row['cliffs_delta']:+.3f} ({row['effect_size']})"
            )


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
