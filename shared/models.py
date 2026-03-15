"""Pydantic models for health reports, query plans, and benchmark results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class Architecture(str, Enum):
    MCP = "mcp"
    A2A = "a2a"
    HYBRID = "hybrid"


# ── GitHub Models ──


class GitHubRepoInfo(BaseModel):
    name: str = ""
    full_name: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    watchers: int = 0
    language: str | None = None
    created_at: str = ""
    updated_at: str = ""
    pushed_at: str = ""
    description: str = ""
    contributors_count: int = 0
    recent_commits_30d: int = 0
    open_prs: int = 0
    license: str | None = None


# ── npm Models ──


class NpmPackageInfo(BaseModel):
    name: str = ""
    latest_version: str = ""
    weekly_downloads: int = 0
    monthly_downloads: int = 0
    dependency_count: int = 0
    versions_count: int = 0
    last_publish: str = ""
    description: str = ""
    license: str | None = None


# ── OSV Models ──


class Vulnerability(BaseModel):
    id: str = ""
    summary: str = ""
    severity: str = ""
    published: str = ""
    modified: str = ""
    affected_versions: list[str] = Field(default_factory=list)


class OsvReport(BaseModel):
    package_name: str = ""
    ecosystem: str = ""
    total_vulnerabilities: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    vulnerabilities: list[Vulnerability] = Field(default_factory=list)


# ── StackOverflow Models ──


class StackOverflowInfo(BaseModel):
    tag: str = ""
    total_questions: int = 0
    questions_last_30d: int = 0
    avg_answer_count: float = 0.0
    answered_percentage: float = 0.0
    avg_score: float = 0.0


# ── Composite Models ──


class ProjectHealthReport(BaseModel):
    project_name: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    github: GitHubRepoInfo | None = None
    npm: NpmPackageInfo | None = None
    osv: OsvReport | None = None
    stackoverflow: StackOverflowInfo | None = None
    health_score: float | None = None
    summary: str = ""


class QueryPlan(BaseModel):
    query: str
    complexity: QueryComplexity
    sources_needed: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    strategy: str = ""


# ── Benchmark Models ──


class BenchmarkResult(BaseModel):
    query_id: int
    query_text: str
    complexity: QueryComplexity
    architecture: Architecture
    run_number: int
    latency_ms: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    api_calls: int = 0
    error_recovery: bool = False
    cold_start_ms: float = 0.0
    cost_usd: float = 0.0
    success: bool = True
    error_message: str = ""
    response_text: str = ""
    reports: list[ProjectHealthReport] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSummary(BaseModel):
    architecture: Architecture
    complexity: QueryComplexity
    avg_latency_ms: float = 0.0
    median_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_tokens: float = 0.0
    avg_llm_calls: float = 0.0
    avg_api_calls: float = 0.0
    avg_cost_usd: float = 0.0
    success_rate: float = 0.0
    error_recovery_rate: float = 0.0
    total_runs: int = 0
