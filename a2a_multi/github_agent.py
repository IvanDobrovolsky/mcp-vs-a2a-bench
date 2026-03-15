"""A2A specialist agent for GitHub data — runs as an HTTP server on port 8001."""

from __future__ import annotations

import json

import anthropic
import uvicorn

from a2a_multi.a2a_models import AgentCard, AgentCapabilities, AgentSkill
from a2a_multi.a2a_server import A2AServer
from shared.github_client import get_repo_info
from shared.metrics import MetricsCollector

MODEL = "claude-sonnet-4-20250514"
PORT = 8001

from mcp_only.github_mcp_server import REPO_MAP

SYSTEM_PROMPT = """You are a GitHub data specialist agent. You analyze GitHub repository data to assess project health.

You will receive queries about open source projects. Use the provided data to give detailed, factual responses about:
- Repository statistics (stars, forks, watchers)
- Development activity (commits, PRs, issues)
- Maintainer/contributor health
- Overall project momentum

Always respond with structured data and clear analysis."""

AGENT_CARD = AgentCard(
    name="GitHub Health Agent",
    description="Specialist agent for analyzing GitHub repository health metrics including stars, forks, issues, PRs, contributors, and commit activity.",
    url=f"http://localhost:{PORT}",
    version="1.0.0",
    capabilities=AgentCapabilities(),
    skills=[
        AgentSkill(
            id="github-repo-analysis",
            name="GitHub Repository Analysis",
            description="Analyzes GitHub repository statistics and development activity",
            tags=["github", "repository", "stars", "forks", "issues", "commits", "contributors"],
            examples=[
                "How many stars does React have?",
                "When was the last commit to fastify?",
                "How many contributors does Django have?",
            ],
        )
    ],
)


def _resolve_repo(project: str) -> tuple[str, str]:
    key = project.lower().strip()
    if key in REPO_MAP:
        return REPO_MAP[key]
    if "/" in project:
        parts = project.split("/", 1)
        return parts[0], parts[1]
    raise ValueError(f"Unknown project: {project}")


def _extract_projects_from_query(query: str) -> list[str]:
    found = []
    query_lower = query.lower()
    for name in REPO_MAP:
        if name in query_lower:
            found.append(name)
    return found if found else ["react"]


class GitHubA2AServer(A2AServer):
    async def process_task(self, query: str, projects: list[str] | None) -> dict:
        metrics = MetricsCollector()
        metrics.start()

        results = {}
        errors = []

        if not projects:
            projects = _extract_projects_from_query(query)

        for project in projects:
            try:
                owner, repo = _resolve_repo(project)
                info = await get_repo_info(owner, repo)
                metrics.record_api_call()
                results[project] = info
            except Exception as e:
                errors.append(f"{project}: {str(e)}")
                metrics.record_error(str(e))

        response_text = ""
        if results:
            client = anthropic.Anthropic()
            synthesis_prompt = f"""Based on this GitHub data, answer the query: "{query}"

Data:
{json.dumps(results, indent=2)}

Provide a factual analysis based on the numbers."""

            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            metrics.record_llm_usage(response.usage.input_tokens, response.usage.output_tokens)
            response_text = response.content[0].text

        metrics.stop()

        return {
            "source": "github",
            "response": response_text,
            "data": results,
            "errors": errors,
            "metrics": {
                "latency_ms": metrics.latency_ms,
                "total_tokens": metrics.total_tokens,
                "prompt_tokens": metrics.prompt_tokens,
                "completion_tokens": metrics.completion_tokens,
                "llm_calls": metrics.llm_calls,
                "api_calls": metrics.api_calls,
            },
        }


server = GitHubA2AServer(AGENT_CARD)
app = server.app

if __name__ == "__main__":
    uvicorn.run("a2a_multi.github_agent:app", host="0.0.0.0", port=PORT, reload=False)
