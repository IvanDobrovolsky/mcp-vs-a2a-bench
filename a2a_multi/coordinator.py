"""Architecture B: A2A Coordinator — delegates to specialist agents over HTTP.

Each specialist runs as a separate HTTP server implementing the A2A protocol.
The coordinator discovers agents via Agent Cards and sends tasks via JSON-RPC.
"""

from __future__ import annotations

import asyncio
import json
import sys

import anthropic

from a2a_multi.a2a_client import A2AClient
from a2a_multi.a2a_models import TaskState
from shared.metrics import MetricsCollector
from shared.models import Architecture, BenchmarkResult, QueryComplexity

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a coordinator agent for the Open Source Health Analyzer.
You delegate tasks to 4 specialist agents via the A2A protocol:
- GitHub agent (port 8001): repository stats
- npm agent (port 8002): package data
- OSV agent (port 8003): vulnerability info
- StackOverflow agent (port 8004): community metrics

Your job is to:
1. Analyze the user's query
2. Determine which specialists to invoke
3. Synthesize their responses into a unified answer

Respond with a JSON plan:
{
    "projects": ["project1", "project2"],
    "sources": ["github", "npm", "osv", "stackoverflow"],
    "strategy": "brief description of approach"
}"""

# A2A agent endpoints
AGENT_URLS = {
    "github": "http://localhost:8001",
    "npm": "http://localhost:8002",
    "osv": "http://localhost:8003",
    "stackoverflow": "http://localhost:8004",
}


async def _discover_agents() -> dict[str, A2AClient]:
    """Discover available A2A agents by fetching their Agent Cards."""
    clients = {}
    for name, url in AGENT_URLS.items():
        client = A2AClient(url)
        try:
            card = await client.get_agent_card()
            clients[name] = client
        except Exception:
            # Agent not available — skip
            pass
    return clients


async def _plan_query(client: anthropic.Anthropic, query: str, metrics: MetricsCollector) -> dict:
    """Use LLM to plan which agents to delegate to."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    metrics.record_llm_usage(response.usage.input_tokens, response.usage.output_tokens)

    text = response.content[0].text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        plan = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        plan = {
            "projects": [],
            "sources": ["github", "npm", "osv", "stackoverflow"],
            "strategy": "full analysis",
        }

    return plan


async def _delegate_to_agent(
    a2a_client: A2AClient,
    source: str,
    query: str,
    projects: list[str],
) -> dict:
    """Send a task to a specialist agent via A2A protocol over HTTP."""
    task = await a2a_client.send_task(
        query=query,
        projects=projects if projects else None,
        metadata={"projects": projects, "source": source},
    )

    # Extract results from completed task
    response_text = a2a_client.extract_response_text(task)
    data = a2a_client.extract_response_data(task)
    agent_metrics = a2a_client.extract_metrics(task)
    errors = task.metadata.get("errors", [])

    return {
        "source": source,
        "response": response_text,
        "data": data,
        "errors": errors,
        "metrics": agent_metrics,
        "task_state": task.status.state.value,
    }


async def _synthesize(
    client: anthropic.Anthropic,
    query: str,
    agent_results: list[dict],
    metrics: MetricsCollector,
) -> str:
    """Synthesize specialist results into a unified response."""
    results_text = "\n\n".join(
        f"=== {r['source'].upper()} Agent ===\n{r['response']}"
        for r in agent_results
        if r.get("response")
    )

    if not results_text:
        return "Unable to gather sufficient data to answer the query."

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system="You are a synthesizer. Combine specialist agent reports into a unified, well-structured response. Include specific numbers and data. Be comprehensive but concise.",
        messages=[{
            "role": "user",
            "content": f'Query: "{query}"\n\nSpecialist Reports:\n{results_text}\n\nProvide a unified analysis.',
        }],
    )
    metrics.record_llm_usage(response.usage.input_tokens, response.usage.output_tokens)
    return response.content[0].text


async def run_query(
    query: str,
    query_id: int = 0,
    complexity: QueryComplexity = QueryComplexity.SIMPLE,
    run_number: int = 1,
) -> BenchmarkResult:
    """Run a query through the A2A multi-agent architecture.

    Discovers specialist agents, delegates tasks in parallel via HTTP,
    and synthesizes results.
    """
    metrics = MetricsCollector()
    metrics.start()

    llm_client = anthropic.Anthropic()

    # Step 1: Discover available A2A agents
    available_agents = await _discover_agents()
    if not available_agents:
        metrics.stop()
        return BenchmarkResult(
            query_id=query_id,
            query_text=query,
            complexity=complexity,
            architecture=Architecture.A2A,
            run_number=run_number,
            success=False,
            error_message="No A2A agents available. Start agents with: python -m a2a_multi.launch",
            latency_ms=metrics.latency_ms,
        )

    # Step 2: Plan delegation
    plan = await _plan_query(llm_client, query, metrics)
    metrics.mark_first_output()

    projects = plan.get("projects", [])
    sources = plan.get("sources", ["github", "npm", "osv", "stackoverflow"])

    # Step 3: Delegate to specialists in parallel via A2A HTTP
    tasks = []
    for source in sources:
        if source in available_agents:
            tasks.append(
                _delegate_to_agent(available_agents[source], source, query, projects)
            )

    agent_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    valid_results = []
    for result in agent_results:
        if isinstance(result, Exception):
            metrics.record_error(str(result))
        else:
            valid_results.append(result)
            sub_metrics = result.get("metrics", {})
            metrics.total_tokens += sub_metrics.get("total_tokens", 0)
            metrics.prompt_tokens += sub_metrics.get("prompt_tokens", 0)
            metrics.completion_tokens += sub_metrics.get("completion_tokens", 0)
            metrics.llm_calls += sub_metrics.get("llm_calls", 0)
            metrics.api_calls += sub_metrics.get("api_calls", 0)

    # Step 4: Synthesize
    response_text = await _synthesize(llm_client, query, valid_results, metrics)

    metrics.stop()

    return BenchmarkResult(
        query_id=query_id,
        query_text=query,
        complexity=complexity,
        architecture=Architecture.A2A,
        run_number=run_number,
        latency_ms=metrics.latency_ms,
        total_tokens=metrics.total_tokens,
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        llm_calls=metrics.llm_calls,
        api_calls=metrics.api_calls,
        error_recovery=len(metrics.errors) > 0 and response_text != "",
        cold_start_ms=metrics.cold_start_ms,
        success=response_text != "",
        error_message="; ".join(metrics.errors) if metrics.errors else "",
        response_text=response_text,
        metadata={
            "agents_discovered": list(available_agents.keys()),
            "agents_delegated": sources,
        },
    )


async def main():
    """CLI entry point."""
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How many stars does React have?"
    print(f"Query: {query}\n")
    result = await run_query(query)
    if not result.success:
        print(f"Error: {result.error_message}")
        return
    print(f"Response:\n{result.response_text}\n")
    print(f"Agents: {result.metadata.get('agents_discovered', [])}")
    print(f"Latency: {result.latency_ms:.0f}ms | Tokens: {result.total_tokens} | "
          f"LLM calls: {result.llm_calls} | API calls: {result.api_calls}")


if __name__ == "__main__":
    asyncio.run(main())
