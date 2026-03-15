"""Tests for LOC counter."""

import pytest
from benchmark.loc_counter import count_lines, measure_all, _cyclomatic_complexity
from pathlib import Path
import ast
import tempfile


class TestCountLines:
    def test_simple_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""# Comment
x = 1
y = 2

def foo():
    return x + y
""")
            f.flush()
            metrics = count_lines(Path(f.name))

        assert metrics.code_lines == 4  # x=1, y=2, def foo, return
        assert metrics.comment_lines == 1
        assert metrics.blank_lines >= 1
        assert metrics.functions == 1

    def test_docstring_handling(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('''"""Module docstring."""

def foo():
    """Function docstring."""
    return 1
''')
            f.flush()
            metrics = count_lines(Path(f.name))

        assert metrics.functions == 1
        assert metrics.comment_lines >= 2  # Module and function docstrings


class TestCyclomaticComplexity:
    def test_linear(self):
        tree = ast.parse("x = 1\ny = 2\n")
        assert _cyclomatic_complexity(tree) == 1

    def test_single_if(self):
        tree = ast.parse("if x:\n    y = 1\n")
        assert _cyclomatic_complexity(tree) == 2

    def test_if_else(self):
        tree = ast.parse("if x:\n    y = 1\nelse:\n    y = 2\n")
        assert _cyclomatic_complexity(tree) == 2  # else doesn't add

    def test_for_loop(self):
        tree = ast.parse("for i in range(10):\n    pass\n")
        assert _cyclomatic_complexity(tree) == 2

    def test_boolean_and(self):
        tree = ast.parse("if x and y:\n    pass\n")
        assert _cyclomatic_complexity(tree) == 3  # if + and

    def test_try_except(self):
        tree = ast.parse("try:\n    x = 1\nexcept:\n    pass\n")
        assert _cyclomatic_complexity(tree) == 2


class TestMeasureAll:
    def test_returns_all_architectures(self):
        results = measure_all()
        assert "mcp" in results
        assert "a2a" in results
        assert "hybrid" in results

    def test_mcp_less_than_a2a(self):
        results = measure_all()
        assert results["mcp"].specific_loc < results["a2a"].specific_loc

    def test_hybrid_most_code(self):
        results = measure_all()
        assert results["hybrid"].total_loc >= results["mcp"].total_loc
        assert results["hybrid"].total_loc >= results["a2a"].total_loc

    def test_nonzero_metrics(self):
        results = measure_all()
        for arch in ["mcp", "a2a", "hybrid"]:
            assert results[arch].total_loc > 0
            assert results[arch].total_files > 0
            assert results[arch].total_functions > 0
