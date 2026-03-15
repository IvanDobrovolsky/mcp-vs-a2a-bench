"""Generate publication-ready LaTeX tables from benchmark results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.analyze_results import bootstrap_ci, cliffs_delta, load_results, pairwise_comparisons
from shared.models import Architecture

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent.parent / "paper" / "figures"

COMPLEXITY_ORDER = ["simple", "medium", "complex"]


def generate_main_results_table(df: pd.DataFrame) -> str:
    """Generate the main results table (Table 1 in paper).

    Shows avg latency, tokens, LLM calls, API calls, cost per architecture per complexity.
    """
    successful = df[df["success"] == True]

    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Benchmark Results: Mean (95\% CI) across 5 runs per query}",
        r"\label{tab:main-results}",
        r"\begin{tabular}{llrrrrc}",
        r"\toprule",
        r"\textbf{Complexity} & \textbf{Arch} & \textbf{Latency (ms)} & \textbf{Tokens} & \textbf{LLM Calls} & \textbf{API Calls} & \textbf{Cost (\$)} \\",
        r"\midrule",
    ]

    for comp in COMPLEXITY_ORDER:
        first_in_group = True
        for arch in ["mcp", "a2a", "hybrid"]:
            data = successful[
                (successful["architecture"] == arch) & (successful["complexity"] == comp)
            ]
            if data.empty:
                continue

            lat_mean, lat_lo, lat_hi = bootstrap_ci(data["latency_ms"].values)
            tok_mean, tok_lo, tok_hi = bootstrap_ci(data["total_tokens"].values)
            llm_mean = data["llm_calls"].mean()
            api_mean = data["api_calls"].mean()
            cost_mean = data["cost_usd"].mean() if "cost_usd" in data.columns else 0

            comp_label = comp.capitalize() if first_in_group else ""
            first_in_group = False

            lines.append(
                f"{comp_label} & {arch.upper()} & "
                f"{lat_mean:,.0f} [{lat_lo:,.0f}, {lat_hi:,.0f}] & "
                f"{tok_mean:,.0f} & "
                f"{llm_mean:.1f} & "
                f"{api_mean:.1f} & "
                f"{cost_mean:.4f} \\\\"
            )

        lines.append(r"\midrule")

    # Remove last midrule and add bottomrule
    lines[-1] = r"\bottomrule"
    lines.extend([
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_significance_table(df: pd.DataFrame) -> str:
    """Generate pairwise significance table (Table 2 in paper)."""
    comparisons = pairwise_comparisons(df, metric="latency_ms")
    if comparisons.empty:
        return "% No data for significance table"

    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Pairwise Latency Comparisons (Mann-Whitney U, Bonferroni-corrected)}",
        r"\label{tab:significance}",
        r"\begin{tabular}{llccc}",
        r"\toprule",
        r"\textbf{Complexity} & \textbf{Comparison} & \textbf{$p$ (corrected)} & \textbf{Cliff's $\delta$} & \textbf{Effect} \\",
        r"\midrule",
    ]

    for _, row in comparisons.iterrows():
        sig_marker = "*" if row["significant"] else ""
        lines.append(
            f"{row['complexity'].capitalize()} & "
            f"{row['arch_a'].upper()} vs {row['arch_b'].upper()} & "
            f"{row['p_corrected']:.4f}{sig_marker} & "
            f"{row['cliffs_delta']:+.3f} & "
            f"{row['effect_size']} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_loc_table() -> str:
    """Generate code complexity table (Table 3 in paper)."""
    from benchmark.loc_counter import measure_all

    results = measure_all()

    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Implementation Complexity by Architecture}",
        r"\label{tab:complexity}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"\textbf{Metric} & \textbf{MCP} & \textbf{A2A} & \textbf{Hybrid} \\",
        r"\midrule",
    ]

    mcp, a2a, hybrid = results["mcp"], results["a2a"], results["hybrid"]

    rows = [
        ("Architecture-specific LOC", mcp.specific_loc, a2a.specific_loc, hybrid.specific_loc),
        ("Shared LOC", mcp.shared_loc, a2a.shared_loc, hybrid.shared_loc),
        ("Total LOC", mcp.total_loc, a2a.total_loc, hybrid.total_loc),
        ("Files", mcp.total_files, a2a.total_files, hybrid.total_files),
        ("Functions", mcp.total_functions, a2a.total_functions, hybrid.total_functions),
        ("Avg. Cyclomatic Complexity", f"{mcp.avg_cyclomatic_complexity:.1f}",
         f"{a2a.avg_cyclomatic_complexity:.1f}", f"{hybrid.avg_cyclomatic_complexity:.1f}"),
    ]

    for label, m, a, h in rows:
        lines.append(f"{label} & {m} & {a} & {h} \\\\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_fault_table() -> str:
    """Generate fault injection results table (Table 4 in paper)."""
    filepath = RESULTS_DIR / "fault_injection_results.json"
    if not filepath.exists():
        return "% No fault injection results available"

    with open(filepath) as f:
        data = json.load(f)

    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Error Recovery Under Fault Injection}",
        r"\label{tab:fault-injection}",
        r"\begin{tabular}{llccc}",
        r"\toprule",
        r"\textbf{Architecture} & \textbf{Fault} & \textbf{Recovered} & \textbf{Completeness} & \textbf{Reported} \\",
        r"\midrule",
    ]

    for row in data:
        if row["fault_mode"] == "none":
            continue
        recovered = "Yes" if row["produced_response"] else "No"
        reported = "Yes" if row["fault_reported"] else "No"
        lines.append(
            f"{row['architecture'].upper()} & "
            f"{row['fault_description'][:30]} & "
            f"{recovered} & "
            f"{row['response_completeness']:.0%} & "
            f"{reported} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_all_tables(input_file: str = "benchmark_results.json"):
    """Generate all LaTeX tables and save to paper/figures/."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Main results
    try:
        df = load_results(input_file)
        main_table = generate_main_results_table(df)
        sig_table = generate_significance_table(df)
    except FileNotFoundError:
        main_table = "% No benchmark results available"
        sig_table = "% No benchmark results available"

    loc_table = generate_loc_table()
    fault_table = generate_fault_table()

    # Combine into one file
    all_tables = "\n\n".join([
        "% Auto-generated LaTeX tables for mcp-vs-a2a-bench paper",
        "% Run: python -m benchmark.latex_tables",
        "",
        "% Table 1: Main Results",
        main_table,
        "",
        "% Table 2: Statistical Significance",
        sig_table,
        "",
        "% Table 3: Code Complexity",
        loc_table,
        "",
        "% Table 4: Fault Injection",
        fault_table,
    ])

    output_path = FIGURES_DIR / "tables.tex"
    with open(output_path, "w") as f:
        f.write(all_tables)

    print(f"LaTeX tables saved to {output_path}")
    print("\nPreview:")
    print(all_tables[:2000])


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate LaTeX tables")
    parser.add_argument("--input", default="benchmark_results.json")
    args = parser.parse_args()
    generate_all_tables(args.input)


if __name__ == "__main__":
    main()
