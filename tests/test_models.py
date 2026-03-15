"""Tests for Pydantic models."""

import pytest
from shared.models import (
    Architecture,
    BenchmarkResult,
    BenchmarkSummary,
    GitHubRepoInfo,
    NpmPackageInfo,
    OsvReport,
    ProjectHealthReport,
    QueryComplexity,
    QueryPlan,
    StackOverflowInfo,
    Vulnerability,
)


class TestEnums:
    def test_query_complexity_values(self):
        assert QueryComplexity.SIMPLE == "simple"
        assert QueryComplexity.MEDIUM == "medium"
        assert QueryComplexity.COMPLEX == "complex"

    def test_architecture_values(self):
        assert Architecture.MCP == "mcp"
        assert Architecture.A2A == "a2a"
        assert Architecture.HYBRID == "hybrid"


class TestGitHubRepoInfo:
    def test_defaults(self):
        info = GitHubRepoInfo()
        assert info.stars == 0
        assert info.forks == 0
        assert info.language is None

    def test_from_data(self):
        info = GitHubRepoInfo(
            name="react",
            stars=220000,
            forks=45000,
            open_issues=1200,
            language="JavaScript",
        )
        assert info.stars == 220000
        assert info.language == "JavaScript"


class TestNpmPackageInfo:
    def test_defaults(self):
        info = NpmPackageInfo()
        assert info.weekly_downloads == 0
        assert info.versions_count == 0

    def test_from_data(self):
        info = NpmPackageInfo(
            name="react",
            latest_version="18.2.0",
            weekly_downloads=20_000_000,
        )
        assert info.weekly_downloads == 20_000_000


class TestOsvReport:
    def test_empty(self):
        report = OsvReport()
        assert report.total_vulnerabilities == 0
        assert report.vulnerabilities == []

    def test_with_vulns(self):
        report = OsvReport(
            package_name="lodash",
            total_vulnerabilities=3,
            critical=1,
            high=1,
            medium=1,
            vulnerabilities=[
                Vulnerability(id="CVE-2021-1234", severity="CRITICAL"),
            ],
        )
        assert report.critical == 1
        assert len(report.vulnerabilities) == 1


class TestBenchmarkResult:
    def test_minimal(self):
        result = BenchmarkResult(
            query_id=1,
            query_text="test",
            complexity=QueryComplexity.SIMPLE,
            architecture=Architecture.MCP,
            run_number=1,
        )
        assert result.success is True
        assert result.cost_usd == 0.0
        assert result.metadata == {}

    def test_failed_result(self):
        result = BenchmarkResult(
            query_id=1,
            query_text="test",
            complexity=QueryComplexity.SIMPLE,
            architecture=Architecture.A2A,
            run_number=1,
            success=False,
            error_message="Agent unavailable",
        )
        assert result.success is False

    def test_serialization(self):
        result = BenchmarkResult(
            query_id=1,
            query_text="test",
            complexity=QueryComplexity.SIMPLE,
            architecture=Architecture.MCP,
            run_number=1,
            latency_ms=1500.0,
            total_tokens=3000,
            cost_usd=0.012,
        )
        data = result.model_dump()
        assert data["cost_usd"] == 0.012
        assert data["architecture"] == "mcp"

        # Round-trip
        restored = BenchmarkResult(**data)
        assert restored.cost_usd == 0.012


class TestQueryPlan:
    def test_plan(self):
        plan = QueryPlan(
            query="Compare React vs Vue",
            complexity=QueryComplexity.COMPLEX,
            sources_needed=["github", "npm"],
            projects=["react", "vue"],
        )
        assert len(plan.projects) == 2
