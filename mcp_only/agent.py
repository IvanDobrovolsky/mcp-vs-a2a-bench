"""Architecture A: Single agent with 4 MCP tool connections."""

from __future__ import annotations

import asyncio
import json
import sys
import os

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from shared.metrics import MetricsCollector
from shared.models import Architecture, BenchmarkResult, QueryComplexity

MODEL = "claude-sonnet-4-20250514"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYSTEM_PROMPT = """You are an Open Source Health Analyzer. You have access to tools from 4 MCP servers:
- GitHub: repository stats (stars, forks, issues, PRs, contributors, commits)
- npm: package info (downloads, versions, dependencies)
- OSV: vulnerability data (known CVEs by severity)
- StackOverflow: community metrics (questions, answer rates)

When answering queries:
1. Identify which data sources are needed
2. Call the relevant tools to gather data
3. Synthesize the information into a clear, data-driven response
4. Include specific numbers and comparisons where relevant

For project names, use common names like 'react', 'vue', 'express', etc.
For npm packages, use the npm package name (e.g. 'react', 'express', 'lodash').
For StackOverflow, use the appropriate tag (e.g. 'reactjs', 'vue.js', 'express').
"""

MCP_SERVERS = [
    StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_only.github_mcp_server"],
        env={**os.environ},
        cwd=PROJECT_ROOT,
    ),
    StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_only.npm_mcp_server"],
        env={**os.environ},
        cwd=PROJECT_ROOT,
    ),
    StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_only.osv_mcp_server"],
        env={**os.environ},
        cwd=PROJECT_ROOT,
    ),
    StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_only.stackoverflow_mcp_server"],
        env={**os.environ},
        cwd=PROJECT_ROOT,
    ),
]


async def _connect_and_list_tools(
    server_params: StdioServerParameters,
) -> tuple[ClientSession, list[dict]]:
    """Connect to an MCP server and list its tools."""
    read_stream, write_stream = await stdio_client(server_params).__aenter__()
    session = ClientSession(read_stream, write_stream)
    await session.__aenter__()
    await session.initialize()
    tools_result = await session.list_tools()
    tools = []
    for t in tools_result.tools:
        tools.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        })
    return session, tools


async def run_query(
    query: str,
    query_id: int = 0,
    complexity: QueryComplexity = QueryComplexity.SIMPLE,
    run_number: int = 1,
) -> BenchmarkResult:
    """Run a query through the MCP-only architecture."""
    metrics = MetricsCollector()
    metrics.start()

    sessions: list[ClientSession] = []
    tool_to_session: dict[str, ClientSession] = {}
    all_tools: list[dict] = []
    context_managers = []

    try:
        # Connect to all MCP servers
        for server_params in MCP_SERVERS:
            read_stream, write_stream = await stdio_client(server_params).__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()
            tools_result = await session.list_tools()

            for t in tools_result.tools:
                tool_def = {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                all_tools.append(tool_def)
                tool_to_session[t.name] = session

            sessions.append(session)

        # Convert tools to Anthropic format
        anthropic_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in all_tools
        ]

        # Run agentic loop
        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": query}]

        response_text = ""
        max_iterations = 15

        for _ in range(max_iterations):
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=anthropic_tools,
                messages=messages,
            )

            metrics.record_llm_usage(
                response.usage.input_tokens, response.usage.output_tokens
            )
            metrics.mark_first_output()

            # Process response
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    response_text += block.text
                elif block.type == "tool_use":
                    tool_calls.append(block)

            if response.stop_reason == "end_turn" or not tool_calls:
                break

            # Execute tool calls
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for tool_call in tool_calls:
                session = tool_to_session.get(tool_call.name)
                if session:
                    try:
                        metrics.record_api_call()
                        result = await session.call_tool(
                            tool_call.name, tool_call.input
                        )
                        tool_result_text = (
                            result.content[0].text if result.content else ""
                        )
                    except Exception as e:
                        tool_result_text = json.dumps({"error": str(e)})
                        metrics.record_error(str(e))
                else:
                    tool_result_text = json.dumps(
                        {"error": f"Unknown tool: {tool_call.name}"}
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": tool_result_text,
                })

            messages.append({"role": "user", "content": tool_results})

    finally:
        metrics.stop()

    return BenchmarkResult(
        query_id=query_id,
        query_text=query,
        complexity=complexity,
        architecture=Architecture.MCP,
        run_number=run_number,
        latency_ms=metrics.latency_ms,
        total_tokens=metrics.total_tokens,
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        llm_calls=metrics.llm_calls,
        api_calls=metrics.api_calls,
        error_recovery=len(metrics.errors) > 0 and response_text != "",
        cold_start_ms=metrics.cold_start_ms,
        cost_usd=metrics.cost_usd,
        success=response_text != "",
        error_message="; ".join(metrics.errors) if metrics.errors else "",
        response_text=response_text,
    )


async def main():
    """CLI entry point."""
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How many stars does React have?"
    print(f"Query: {query}\n")
    result = await run_query(query)
    print(f"Response:\n{result.response_text}\n")
    print(f"Latency: {result.latency_ms:.0f}ms | Tokens: {result.total_tokens} | "
          f"LLM calls: {result.llm_calls} | API calls: {result.api_calls} | "
          f"Cost: ${result.cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
