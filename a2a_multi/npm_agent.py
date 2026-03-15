"""A2A specialist agent for npm data — runs as an HTTP server on port 8002."""

from __future__ import annotations

import json

import anthropic
import uvicorn

from a2a_multi.a2a_models import AgentCard, AgentCapabilities, AgentSkill
from a2a_multi.a2a_server import A2AServer
from shared.metrics import MetricsCollector
from shared.npm_client import get_full_package_info

MODEL = "claude-sonnet-4-20250514"
PORT = 8002

SYSTEM_PROMPT = """You are an npm registry data specialist agent. You analyze npm package data to assess ecosystem health.

You will receive queries about packages. Use the provided data to give detailed responses about:
- Download trends and adoption
- Version history and release cadence
- Dependency footprint
- Package maintenance status

Always respond with structured data and clear analysis."""

PACKAGE_MAP: dict[str, str] = {
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "angular": "@angular/core",
    "next.js": "next",
    "nextjs": "next",
    "nuxt": "nuxt",
    "sveltekit": "@sveltejs/kit",
    "express": "express",
    "express.js": "express",
    "fastify": "fastify",
    "koa": "koa",
    "deno": "deno",
    "bun": "bun",
    "vite": "vite",
    "webpack": "webpack",
    "turbopack": "turbopack",
    "prisma": "@prisma/client",
    "drizzle": "drizzle-orm",
    "typeorm": "typeorm",
    "sequelize": "sequelize",
    "redux": "redux",
    "zustand": "zustand",
    "jotai": "jotai",
    "recoil": "recoil",
    "tailwind": "tailwindcss",
    "tailwind css": "tailwindcss",
    "tailwindcss": "tailwindcss",
    "bootstrap": "bootstrap",
    "jest": "jest",
    "vitest": "vitest",
    "playwright": "playwright",
    "lodash": "lodash",
    "axios": "axios",
    "tensorflow.js": "@tensorflow/tfjs",
    "tensorflowjs": "@tensorflow/tfjs",
    "remix": "@remix-run/react",
}

AGENT_CARD = AgentCard(
    name="npm Registry Agent",
    description="Specialist agent for analyzing npm package data including downloads, versions, dependencies, and release cadence.",
    url=f"http://localhost:{PORT}",
    version="1.0.0",
    capabilities=AgentCapabilities(),
    skills=[
        AgentSkill(
            id="npm-package-analysis",
            name="npm Package Analysis",
            description="Analyzes npm package statistics and adoption metrics",
            tags=["npm", "downloads", "versions", "dependencies", "packages"],
            examples=[
                "What's the weekly npm download count for express?",
                "What's the latest version of Next.js on npm?",
            ],
        )
    ],
)


def _resolve_package(project: str) -> str:
    key = project.lower().strip()
    return PACKAGE_MAP.get(key, project)


def _extract_projects(query: str) -> list[str]:
    found = []
    query_lower = query.lower()
    for name in PACKAGE_MAP:
        if name in query_lower:
            found.append(name)
    return found if found else ["react"]


class NpmA2AServer(A2AServer):
    async def process_task(self, query: str, projects: list[str] | None) -> dict:
        metrics = MetricsCollector()
        metrics.start()

        results = {}
        errors = []

        if not projects:
            projects = _extract_projects(query)

        for project in projects:
            try:
                pkg = _resolve_package(project)
                info = await get_full_package_info(pkg)
                metrics.record_api_call()
                results[project] = info
            except Exception as e:
                errors.append(f"{project}: {str(e)}")
                metrics.record_error(str(e))

        response_text = ""
        if results:
            client = anthropic.Anthropic()
            synthesis_prompt = f"""Based on this npm data, answer the query: "{query}"

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
            "source": "npm",
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


server = NpmA2AServer(AGENT_CARD)
app = server.app

if __name__ == "__main__":
    uvicorn.run("a2a_multi.npm_agent:app", host="0.0.0.0", port=PORT, reload=False)
