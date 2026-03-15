"""Automated code complexity measurement for each architecture.

Counts lines of code, cyclomatic complexity, and file counts per architecture.
This lets us empirically compare the implementation complexity cost of each approach.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Architecture-to-file mapping
ARCH_FILES = {
    "mcp": {
        "specific": [
            "mcp_only/agent.py",
            "mcp_only/github_mcp_server.py",
            "mcp_only/npm_mcp_server.py",
            "mcp_only/osv_mcp_server.py",
            "mcp_only/stackoverflow_mcp_server.py",
        ],
        "shared": [
            "shared/github_client.py",
            "shared/npm_client.py",
            "shared/osv_client.py",
            "shared/stackoverflow_client.py",
            "shared/models.py",
            "shared/metrics.py",
        ],
    },
    "a2a": {
        "specific": [
            "a2a_multi/coordinator.py",
            "a2a_multi/github_agent.py",
            "a2a_multi/npm_agent.py",
            "a2a_multi/osv_agent.py",
            "a2a_multi/stackoverflow_agent.py",
            "a2a_multi/a2a_server.py",
            "a2a_multi/a2a_client.py",
            "a2a_multi/a2a_models.py",
            "a2a_multi/launch.py",
        ],
        "shared": [
            "shared/github_client.py",
            "shared/npm_client.py",
            "shared/osv_client.py",
            "shared/stackoverflow_client.py",
            "shared/models.py",
            "shared/metrics.py",
        ],
    },
    "hybrid": {
        "specific": [
            "hybrid/coordinator.py",
            "hybrid/router.py",
            # Hybrid reuses both MCP and A2A, so include both
            "mcp_only/agent.py",
            "mcp_only/github_mcp_server.py",
            "mcp_only/npm_mcp_server.py",
            "mcp_only/osv_mcp_server.py",
            "mcp_only/stackoverflow_mcp_server.py",
            "a2a_multi/coordinator.py",
            "a2a_multi/github_agent.py",
            "a2a_multi/npm_agent.py",
            "a2a_multi/osv_agent.py",
            "a2a_multi/stackoverflow_agent.py",
            "a2a_multi/a2a_server.py",
            "a2a_multi/a2a_client.py",
            "a2a_multi/a2a_models.py",
            "a2a_multi/launch.py",
        ],
        "shared": [
            "shared/github_client.py",
            "shared/npm_client.py",
            "shared/osv_client.py",
            "shared/stackoverflow_client.py",
            "shared/models.py",
            "shared/metrics.py",
        ],
    },
}


@dataclass
class FileMetrics:
    """Metrics for a single file."""
    path: str
    total_lines: int = 0
    code_lines: int = 0  # Non-blank, non-comment
    blank_lines: int = 0
    comment_lines: int = 0
    functions: int = 0
    classes: int = 0
    cyclomatic_complexity: int = 0


@dataclass
class ArchitectureMetrics:
    """Aggregate metrics for an architecture."""
    architecture: str
    specific_loc: int = 0  # LOC unique to this architecture
    shared_loc: int = 0  # LOC shared across architectures
    total_loc: int = 0  # specific + shared
    specific_files: int = 0
    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    avg_cyclomatic_complexity: float = 0.0
    file_metrics: list[FileMetrics] = field(default_factory=list)


def count_lines(filepath: Path) -> FileMetrics:
    """Count lines, functions, classes, and estimate cyclomatic complexity."""
    try:
        rel_path = str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        rel_path = str(filepath)
    metrics = FileMetrics(path=rel_path)

    try:
        content = filepath.read_text()
    except (OSError, UnicodeDecodeError):
        return metrics

    lines = content.split("\n")
    metrics.total_lines = len(lines)

    in_docstring = False
    docstring_char = None

    for line in lines:
        stripped = line.strip()

        if not stripped:
            metrics.blank_lines += 1
            continue

        # Handle docstrings (triple quotes)
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                    # Single-line docstring
                    metrics.comment_lines += 1
                    continue
                in_docstring = True
                metrics.comment_lines += 1
                continue
            elif stripped.startswith("#"):
                metrics.comment_lines += 1
                continue
        else:
            metrics.comment_lines += 1
            if docstring_char in stripped:
                in_docstring = False
            continue

        metrics.code_lines += 1

    # AST analysis for functions, classes, cyclomatic complexity
    try:
        tree = ast.parse(content)
        metrics.functions = sum(
            1 for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        metrics.classes = sum(
            1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        )
        metrics.cyclomatic_complexity = _cyclomatic_complexity(tree)
    except SyntaxError:
        pass

    return metrics


def _cyclomatic_complexity(tree: ast.AST) -> int:
    """Estimate cyclomatic complexity from AST.

    CC = 1 + number of decision points (if, elif, for, while, and, or, except, with, assert)
    """
    complexity = 1  # Base complexity

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(node, (ast.While,)):
            complexity += 1
        elif isinstance(node, (ast.ExceptHandler,)):
            complexity += 1
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(node, (ast.Assert,)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # Each and/or adds a branch
            complexity += len(node.values) - 1

    return complexity


def measure_architecture(arch: str) -> ArchitectureMetrics:
    """Measure code complexity for a single architecture."""
    file_map = ARCH_FILES[arch]
    result = ArchitectureMetrics(architecture=arch)

    seen_files = set()

    # Specific files (unique to this architecture)
    for rel_path in file_map["specific"]:
        filepath = PROJECT_ROOT / rel_path
        if filepath.exists() and rel_path not in seen_files:
            seen_files.add(rel_path)
            fm = count_lines(filepath)
            result.file_metrics.append(fm)
            result.specific_loc += fm.code_lines
            result.specific_files += 1
            result.total_functions += fm.functions
            result.total_classes += fm.classes

    # Shared files
    for rel_path in file_map["shared"]:
        filepath = PROJECT_ROOT / rel_path
        if filepath.exists() and rel_path not in seen_files:
            seen_files.add(rel_path)
            fm = count_lines(filepath)
            result.file_metrics.append(fm)
            result.shared_loc += fm.code_lines

    result.total_loc = result.specific_loc + result.shared_loc
    result.total_files = len(seen_files)

    # Average cyclomatic complexity
    complexities = [fm.cyclomatic_complexity for fm in result.file_metrics if fm.cyclomatic_complexity > 0]
    result.avg_cyclomatic_complexity = sum(complexities) / len(complexities) if complexities else 0

    return result


def measure_all() -> dict[str, ArchitectureMetrics]:
    """Measure code complexity for all architectures."""
    results = {}
    for arch in ["mcp", "a2a", "hybrid"]:
        results[arch] = measure_architecture(arch)
    return results


def print_report(results: dict[str, ArchitectureMetrics]):
    """Print a formatted comparison report."""
    print("=" * 80)
    print("CODE COMPLEXITY COMPARISON")
    print("=" * 80)

    # Summary table
    print(f"\n{'Metric':<30} {'MCP':>10} {'A2A':>10} {'Hybrid':>10}")
    print("-" * 60)

    mcp, a2a, hybrid = results["mcp"], results["a2a"], results["hybrid"]

    print(f"{'Architecture-specific LOC':<30} {mcp.specific_loc:>10} {a2a.specific_loc:>10} {hybrid.specific_loc:>10}")
    print(f"{'Shared LOC':<30} {mcp.shared_loc:>10} {a2a.shared_loc:>10} {hybrid.shared_loc:>10}")
    print(f"{'Total LOC':<30} {mcp.total_loc:>10} {a2a.total_loc:>10} {hybrid.total_loc:>10}")
    print(f"{'Files':<30} {mcp.total_files:>10} {a2a.total_files:>10} {hybrid.total_files:>10}")
    print(f"{'Architecture-specific files':<30} {mcp.specific_files:>10} {a2a.specific_files:>10} {hybrid.specific_files:>10}")
    print(f"{'Functions':<30} {mcp.total_functions:>10} {a2a.total_functions:>10} {hybrid.total_functions:>10}")
    print(f"{'Classes':<30} {mcp.total_classes:>10} {a2a.total_classes:>10} {hybrid.total_classes:>10}")
    print(f"{'Avg cyclomatic complexity':<30} {mcp.avg_cyclomatic_complexity:>10.1f} {a2a.avg_cyclomatic_complexity:>10.1f} {hybrid.avg_cyclomatic_complexity:>10.1f}")

    # Per-file breakdown
    for arch_name, arch_metrics in results.items():
        print(f"\n--- {arch_name.upper()} file breakdown ---")
        for fm in sorted(arch_metrics.file_metrics, key=lambda f: -f.code_lines):
            print(f"  {fm.path:<45} {fm.code_lines:>5} LOC  {fm.functions:>3} fn  CC={fm.cyclomatic_complexity}")


def save_report(results: dict[str, ArchitectureMetrics]):
    """Save results as JSON for inclusion in paper figures."""
    output_dir = PROJECT_ROOT / "paper" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    data = {}
    for arch, metrics in results.items():
        data[arch] = {
            "specific_loc": metrics.specific_loc,
            "shared_loc": metrics.shared_loc,
            "total_loc": metrics.total_loc,
            "total_files": metrics.total_files,
            "specific_files": metrics.specific_files,
            "total_functions": metrics.total_functions,
            "total_classes": metrics.total_classes,
            "avg_cyclomatic_complexity": metrics.avg_cyclomatic_complexity,
            "files": [
                {
                    "path": fm.path,
                    "code_lines": fm.code_lines,
                    "total_lines": fm.total_lines,
                    "functions": fm.functions,
                    "classes": fm.classes,
                    "cyclomatic_complexity": fm.cyclomatic_complexity,
                }
                for fm in metrics.file_metrics
            ],
        }

    filepath = output_dir / "code_complexity.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to {filepath}")


def main():
    results = measure_all()
    print_report(results)
    save_report(results)


if __name__ == "__main__":
    main()
