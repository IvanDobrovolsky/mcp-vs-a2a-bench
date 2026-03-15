"""A2A specialist agent for OSV vulnerability data — runs as an HTTP server on port 8003."""

from __future__ import annotations

import json

import anthropic
import uvicorn

from a2a_multi.a2a_models import AgentCard, AgentCapabilities, AgentSkill
from a2a_multi.a2a_server import A2AServer
from shared.metrics import MetricsCollector
from shared.osv_client import query_vulnerabilities

MODEL = "claude-sonnet-4-20250514"
PORT = 8003

SYSTEM_PROMPT = """You are a security vulnerability specialist agent. You analyze OSV.dev vulnerability data.

You will receive queries about package security. Use the provided data to give detailed responses about:
- Known vulnerabilities and their severity
- Security posture compared to alternatives
- Risk assessment for production use

Always respond with structured data and clear analysis."""

ECOSYSTEM_MAP: dict[str, tuple[str, str]] = {
    "react": ("react", "npm"),
    "vue": ("vue", "npm"),
    "svelte": ("svelte", "npm"),
    "angular": ("@angular/core", "npm"),
    "next.js": ("next", "npm"),
    "nextjs": ("next", "npm"),
    "nuxt": ("nuxt", "npm"),
    "express": ("express", "npm"),
    "express.js": ("express", "npm"),
    "fastify": ("fastify", "npm"),
    "koa": ("koa", "npm"),
    "django": ("django", "PyPI"),
    "flask": ("flask", "PyPI"),
    "fastapi": ("fastapi", "PyPI"),
    "vite": ("vite", "npm"),
    "webpack": ("webpack", "npm"),
    "prisma": ("@prisma/client", "npm"),
    "drizzle": ("drizzle-orm", "npm"),
    "typeorm": ("typeorm", "npm"),
    "sequelize": ("sequelize", "npm"),
    "redux": ("redux", "npm"),
    "zustand": ("zustand", "npm"),
    "jotai": ("jotai", "npm"),
    "recoil": ("recoil", "npm"),
    "tailwindcss": ("tailwindcss", "npm"),
    "tailwind": ("tailwindcss", "npm"),
    "bootstrap": ("bootstrap", "npm"),
    "jest": ("jest", "npm"),
    "vitest": ("vitest", "npm"),
    "playwright": ("playwright", "npm"),
    "lodash": ("lodash", "npm"),
    "axios": ("axios", "npm"),
    "tensorflow.js": ("@tensorflow/tfjs", "npm"),
    "remix": ("@remix-run/react", "npm"),
    "deno": ("deno", "npm"),
    "bun": ("bun", "npm"),
    "node.js": ("node", "npm"),
}

AGENT_CARD = AgentCard(
    name="OSV Security Agent",
    description="Specialist agent for analyzing known security vulnerabilities using the OSV.dev database.",
    url=f"http://localhost:{PORT}",
    version="1.0.0",
    capabilities=AgentCapabilities(),
    skills=[
        AgentSkill(
            id="vulnerability-analysis",
            name="Vulnerability Analysis",
            description="Checks and analyzes known vulnerabilities for packages",
            tags=["security", "vulnerabilities", "CVE", "OSV", "risk"],
            examples=[
                "Are there any critical vulnerabilities in lodash?",
                "Compare security posture of Django vs Flask",
            ],
        )
    ],
)


def _resolve_package(project: str) -> tuple[str, str]:
    key = project.lower().strip()
    if key in ECOSYSTEM_MAP:
        return ECOSYSTEM_MAP[key]
    return project, "npm"


def _extract_projects(query: str) -> list[str]:
    found = []
    query_lower = query.lower()
    for name in ECOSYSTEM_MAP:
        if name in query_lower:
            found.append(name)
    return found if found else ["react"]


class OsvA2AServer(A2AServer):
    async def process_task(self, query: str, projects: list[str] | None) -> dict:
        metrics = MetricsCollector()
        metrics.start()

        results = {}
        errors = []

        if not projects:
            projects = _extract_projects(query)

        for project in projects:
            try:
                pkg, ecosystem = _resolve_package(project)
                report = await query_vulnerabilities(pkg, ecosystem)
                metrics.record_api_call()
                results[project] = report
            except Exception as e:
                errors.append(f"{project}: {str(e)}")
                metrics.record_error(str(e))

        response_text = ""
        if results:
            client = anthropic.Anthropic()
            synthesis_prompt = f"""Based on this vulnerability data, answer the query: "{query}"

Data:
{json.dumps(results, indent=2)}

Provide a factual security analysis."""

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
            "source": "osv",
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
                "cost_usd": metrics.cost_usd,
            },
        }


server = OsvA2AServer(AGENT_CARD)
app = server.app

if __name__ == "__main__":
    uvicorn.run("a2a_multi.osv_agent:app", host="0.0.0.0", port=PORT, reload=False)
