"""A2A specialist agent for StackOverflow data — runs as an HTTP server on port 8004."""

from __future__ import annotations

import json

import anthropic
import uvicorn

from a2a_multi.a2a_models import AgentCard, AgentCapabilities, AgentSkill
from a2a_multi.a2a_server import A2AServer
from shared.metrics import MetricsCollector
from shared.stackoverflow_client import get_tag_info

MODEL = "claude-sonnet-4-20250514"
PORT = 8004

SYSTEM_PROMPT = """You are a StackOverflow community specialist agent. You analyze StackOverflow data to assess community health.

You will receive queries about technology communities. Use the provided data to give detailed responses about:
- Question volume and trends
- Answer quality and engagement
- Community activity and health

Always respond with structured data and clear analysis."""

TAG_MAP: dict[str, str] = {
    "react": "reactjs",
    "vue": "vue.js",
    "svelte": "svelte",
    "angular": "angular",
    "next.js": "next.js",
    "nextjs": "next.js",
    "nuxt": "nuxt.js",
    "sveltekit": "sveltekit",
    "express": "express",
    "express.js": "express",
    "fastify": "fastify",
    "koa": "koa",
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "deno": "deno",
    "bun": "bun",
    "vite": "vite",
    "webpack": "webpack",
    "prisma": "prisma",
    "drizzle": "drizzle-orm",
    "typeorm": "typeorm",
    "sequelize": "sequelize.js",
    "redux": "redux",
    "zustand": "zustand",
    "jotai": "jotai",
    "recoil": "recoiljs",
    "tailwindcss": "tailwind-css",
    "tailwind": "tailwind-css",
    "tailwind css": "tailwind-css",
    "bootstrap": "bootstrap-5",
    "jest": "jestjs",
    "vitest": "vitest",
    "playwright": "playwright",
    "lodash": "lodash",
    "axios": "axios",
    "tensorflow.js": "tensorflow.js",
    "remix": "remix",
    "node.js": "node.js",
}

AGENT_CARD = AgentCard(
    name="StackOverflow Community Agent",
    description="Specialist agent for analyzing StackOverflow community metrics including question volume, answer rates, and tag activity.",
    url=f"http://localhost:{PORT}",
    version="1.0.0",
    capabilities=AgentCapabilities(),
    skills=[
        AgentSkill(
            id="community-analysis",
            name="Community Analysis",
            description="Analyzes StackOverflow community engagement and activity",
            tags=["stackoverflow", "community", "questions", "answers", "engagement"],
            examples=[
                "How many StackOverflow questions are tagged 'svelte'?",
                "Compare community engagement for React vs Vue",
            ],
        )
    ],
)


def _resolve_tag(project: str) -> str:
    key = project.lower().strip()
    return TAG_MAP.get(key, project.lower())


def _extract_projects(query: str) -> list[str]:
    found = []
    query_lower = query.lower()
    for name in TAG_MAP:
        if name in query_lower:
            found.append(name)
    return found if found else ["react"]


class StackOverflowA2AServer(A2AServer):
    async def process_task(self, query: str, projects: list[str] | None) -> dict:
        metrics = MetricsCollector()
        metrics.start()

        results = {}
        errors = []

        if not projects:
            projects = _extract_projects(query)

        for project in projects:
            try:
                tag = _resolve_tag(project)
                info = await get_tag_info(tag)
                metrics.record_api_call()
                results[project] = info
            except Exception as e:
                errors.append(f"{project}: {str(e)}")
                metrics.record_error(str(e))

        response_text = ""
        if results:
            client = anthropic.Anthropic()
            synthesis_prompt = f"""Based on this StackOverflow data, answer the query: "{query}"

Data:
{json.dumps(results, indent=2)}

Provide a factual community analysis."""

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
            "source": "stackoverflow",
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


server = StackOverflowA2AServer(AGENT_CARD)
app = server.app

if __name__ == "__main__":
    uvicorn.run("a2a_multi.stackoverflow_agent:app", host="0.0.0.0", port=PORT, reload=False)
