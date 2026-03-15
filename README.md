# mcp-vs-a2a-bench

## The first empirical benchmark comparing MCP and A2A agent communication protocols

An open-source benchmark that builds the **same application three ways** — MCP-only, A2A multi-agent, and Hybrid — and measures latency, token cost, error recovery, and code complexity across 30 standardized queries.

The application analyzes open-source project health by pulling data from four public APIs simultaneously.

### Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and optional GITHUB_TOKEN

# 3. Architecture A — MCP-Only (no extra setup)
python -m mcp_only.agent "How many stars does React have?"

# 4. Architecture B — A2A Multi-Agent (requires agent servers)
# Terminal 1: Start all 4 A2A agent servers
python -m a2a_multi.launch

# Terminal 2: Run queries via the coordinator
python -m a2a_multi.coordinator "Compare React vs Vue vs Svelte"

# 5. Architecture C — Hybrid (requires A2A servers for complex queries)
python -m hybrid.coordinator "Give me a full health report on Express.js"

# 6. Run the Streamlit UI
streamlit run app.py

# 7. Run the full benchmark suite (start A2A agents first!)
python -m benchmark.run_benchmark --runs 5

# 8. Analyze results
python -m benchmark.analyze_results
```

### A2A Agent Architecture

The A2A implementation uses **real HTTP servers** implementing the Google A2A protocol:

```
Coordinator (A2A Client)
    │
    ├── GET /.well-known/agent.json  ← Agent Card discovery
    │
    └── POST / (JSON-RPC)
        ├── tasks/send    ← Submit task, get result
        ├── tasks/get     ← Poll task status
        └── tasks/cancel  ← Cancel running task
```

Each specialist agent runs as an independent HTTP server:

| Agent | Port | Endpoint |
|---|---|---|
| GitHub | 8001 | `http://localhost:8001` |
| npm | 8002 | `http://localhost:8002` |
| OSV | 8003 | `http://localhost:8003` |
| StackOverflow | 8004 | `http://localhost:8004` |

**Agent management:**
```bash
python -m a2a_multi.launch                # Start all 4 agents
python -m a2a_multi.launch github npm     # Start specific agents
python -m a2a_multi.launch --check        # Check agent status
```

### Three Architectures

| Architecture | How it works | Best for |
|---|---|---|
| **MCP-Only** | Single agent + 4 MCP tool servers (stdio) | Simple, single-source queries |
| **A2A Multi-Agent** | Coordinator delegates to 4 HTTP agent servers in parallel | Complex, multi-project comparisons |
| **Hybrid** | Routes simple→MCP, complex→A2A | Unknown complexity at runtime |

### Data Sources

| API | Data | Auth |
|---|---|---|
| GitHub REST | Stars, forks, issues, PRs, contributors, commits | Free token |
| npm Registry | Downloads, dependencies, versions | No auth |
| OSV.dev | Known vulnerabilities by severity | No auth |
| StackOverflow | Question volume, answer rates, tag activity | No auth |

### What We Measure

- **Latency** — wall clock time per query
- **Token usage** — total LLM tokens consumed
- **LLM calls** — number of API calls to Claude
- **API calls** — number of calls to data sources
- **Error recovery** — graceful degradation when APIs fail
- **Cold start** — time to first useful output

### Benchmark Suite

30 queries across 3 complexity levels, 5 runs each = 450 total executions.

### Tech Stack

- Python 3.11+ / FastAPI / Streamlit / Plotly
- MCP SDK (Anthropic official) — stdio transport for tool servers
- A2A protocol (Google) — HTTP/JSON-RPC transport for agent-to-agent
- Claude Sonnet (claude-sonnet-4-20250514)

### License

MIT
