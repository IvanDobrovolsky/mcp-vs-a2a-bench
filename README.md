# mcp-vs-a2a-bench

## The first empirical benchmark comparing MCP and A2A agent communication protocols

An open-source benchmark that builds the **same application three ways** — MCP-only, A2A multi-agent, and Hybrid — and measures latency, token cost, error recovery, and code complexity across 30 standardized queries.

The application analyzes open-source project health by pulling data from four public APIs simultaneously.

### Key Findings

| Complexity | Fastest | Cheapest | Why |
|---|---|---|---|
| **Simple** (1 source) | MCP (8.7s) | All ~$0.016 | No delegation overhead |
| **Medium** (multi-source) | MCP (28.7s) | MCP ($0.040) | Single agent still efficient |
| **Complex** (multi-project) | A2A (44.3s) | A2A ($0.079) | Parallel delegation + smaller context windows |

**The crossover:** MCP is significantly faster for simple queries (p=0.015), but A2A wins on complex multi-project comparisons by using 2.4x fewer tokens (parallel agents keep context lean).

**Decision framework:**
- 1 source, 1 project → **MCP**
- Multiple sources, 1 project → **MCP** (still faster)
- Multiple sources, multiple projects → **A2A** (parallel + isolated context)
- Unknown complexity at runtime → **Hybrid** (auto-routes)

---

### Quick Start

```bash
# 1. Clone and install (requires Python 3.11+)
git clone https://github.com/IvanDobrovolsky/mcp-vs-a2a-bench.git
cd mcp-vs-a2a-bench
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install kaleido  # For chart export

# 2. Set up environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY (required) and GITHUB_TOKEN (optional)

# 3. Start A2A agent servers (keep this terminal open)
export $(cat .env | xargs)
python -m a2a_multi.launch

# 4. In another terminal — run the Streamlit UI
source .venv/bin/activate
export $(cat .env | xargs)
streamlit run app.py
# Opens at http://localhost:8501
```

The UI has a sidebar where you can enter your API key directly — no `.env` file needed if you prefer.

### Using Docker

```bash
# Start all agents + UI
docker compose up

# Run the full benchmark suite
docker compose --profile benchmark run benchmark
```

---

### Three Architectures

#### Architecture A: MCP-Only (Single Agent + Tool Servers)
```
User Query → Single Agent (one LLM) → 4 MCP Servers (stdio)
                                        ├── GitHub
                                        ├── npm
                                        ├── OSV
                                        └── StackOverflow
```
One agent calls tools directly via MCP stdio transport. Simple, low overhead, but context window grows with every tool response.

#### Architecture B: A2A Multi-Agent (Real HTTP Servers)
```
User Query → Coordinator Agent → 4 A2A Agents (HTTP/JSON-RPC)
                                  ├── GitHub Agent (:8001)
                                  ├── npm Agent (:8002)
                                  ├── OSV Agent (:8003)
                                  └── SO Agent (:8004)
```
Each specialist runs as an independent HTTP server implementing the Google A2A protocol. Coordinator discovers agents via `/.well-known/agent.json`, delegates tasks via `tasks/send` JSON-RPC. Agents run in parallel.

#### Architecture C: Hybrid (Smart Routing)
```
User Query → Router (heuristic) → Simple? → MCP (direct)
                                 → Complex? → A2A (delegate)
```
Classifies query complexity without an LLM call, routes accordingly.

---

### Data Sources

| API | Data | Auth |
|---|---|---|
| GitHub REST | Stars, forks, issues, PRs, contributors, commits | Free token (optional) |
| npm Registry | Downloads, dependencies, versions | No auth |
| OSV.dev | Known vulnerabilities by severity | No auth |
| StackOverflow | Question volume, answer rates, tag activity | No auth |

### What We Measure

| Metric | How |
|---|---|
| **Latency (ms)** | Wall clock time, start to complete response |
| **Token usage** | Sum of all prompt + completion tokens |
| **Cost (USD)** | Computed from Claude Sonnet pricing |
| **LLM calls** | Total API calls to Claude |
| **API calls** | Total calls to data sources |
| **Error recovery** | Active fault injection (API errors, timeouts, agent crashes) |
| **Hallucination rate** | Ground-truth verification against live API data |
| **Code complexity** | AST-based LOC and cyclomatic complexity |

### Statistical Methods

- **Bootstrap 95% confidence intervals** (10,000 resamples, non-parametric)
- **Mann-Whitney U test** for pairwise comparisons
- **Cliff's delta** for effect size
- **Bonferroni correction** for multiple comparisons

---

### Benchmark Suite

30 queries across 3 complexity levels:

- **Simple (10):** Single source, single project (e.g., "How many stars does React have?")
- **Medium (10):** Multi-source, single project (e.g., "Full health report on Express.js")
- **Complex (10):** Multi-source, multi-project (e.g., "Compare React vs Vue vs Svelte")

### CLI Commands

```bash
# Run individual architectures
python -m mcp_only.agent "How many stars does React have?"
python -m a2a_multi.coordinator "Compare React vs Vue vs Svelte"
python -m hybrid.coordinator "Is Express.js still maintained?"

# Run benchmark
python -m benchmark.run_benchmark --runs 5
python -m benchmark.run_benchmark --arch mcp a2a --queries 1 2 3 --runs 3
python -m benchmark.run_benchmark --full --runs 5  # Everything including fault injection

# Analysis
python -m benchmark.analyze_results
python -m benchmark.latex_tables
python -m benchmark.loc_counter
python -m benchmark.hallucination_detector

# A2A agent management
python -m a2a_multi.launch          # Start all 4 agents
python -m a2a_multi.launch --check  # Check status
```

### Tests

```bash
python -m pytest tests/ -v  # 82 tests
```

---

### Project Structure

```
mcp-vs-a2a-bench/
├── app.py                          # Streamlit UI (4 tabs)
├── shared/                         # Shared across all architectures
│   ├── project_maps.py             # Project name → API args mappings
│   ├── github_client.py            # GitHub REST API wrapper
│   ├── npm_client.py               # npm Registry API wrapper
│   ├── osv_client.py               # OSV.dev vulnerability API
│   ├── stackoverflow_client.py     # StackOverflow API wrapper
│   ├── models.py                   # Pydantic models
│   └── metrics.py                  # Token counting, cost, latency
├── mcp_only/                       # Architecture A
│   ├── agent.py                    # Single agent + 4 MCP connections
│   ├── github_mcp_server.py        # MCP server: GitHub tools
│   ├── npm_mcp_server.py           # MCP server: npm tools
│   ├── osv_mcp_server.py           # MCP server: OSV tools
│   └── stackoverflow_mcp_server.py # MCP server: SO tools
├── a2a_multi/                      # Architecture B
│   ├── a2a_models.py               # A2A protocol data models
│   ├── a2a_server.py               # Base A2A HTTP server (FastAPI)
│   ├── a2a_client.py               # A2A HTTP client
│   ├── coordinator.py              # A2A coordinator (delegates via HTTP)
│   ├── github_agent.py             # A2A server on :8001
│   ├── npm_agent.py                # A2A server on :8002
│   ├── osv_agent.py                # A2A server on :8003
│   ├── stackoverflow_agent.py      # A2A server on :8004
│   ├── launch.py                   # Process manager for all agents
│   └── agent_cards/                # A2A Agent Card JSON definitions
├── hybrid/                         # Architecture C
│   ├── coordinator.py              # Routes by complexity
│   └── router.py                   # Heuristic + LLM classifier
├── benchmark/                      # Measurement & analysis
│   ├── queries.json                # 30 benchmark queries
│   ├── run_benchmark.py            # Execute benchmark suite
│   ├── analyze_results.py          # Statistical analysis + charts
│   ├── fault_injection.py          # Error recovery testing
│   ├── hallucination_detector.py   # Ground-truth verification
│   ├── loc_counter.py              # Code complexity measurement
│   ├── latex_tables.py             # Publication-ready LaTeX output
│   └── results/                    # Raw JSON results
├── paper/figures/                  # Generated charts + tables
├── tests/                          # 82 unit tests
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Tech Stack

- **Python 3.11+** / FastAPI / Streamlit / Plotly
- **MCP SDK** (Anthropic) — stdio transport for tool servers
- **A2A protocol** (Google) — HTTP/JSON-RPC for agent-to-agent
- **Claude Sonnet** (claude-sonnet-4-20250514) — same model across all architectures
- **SciPy** — statistical testing

### License

MIT — open source, free to use, fork, and extend.
