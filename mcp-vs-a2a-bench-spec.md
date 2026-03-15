# mcp-vs-a2a-bench

## The first empirical benchmark comparing MCP and A2A agent communication protocols

### What is this?

An open-source benchmark that builds the **same application three ways** — MCP-only, A2A multi-agent, and Hybrid — and measures latency, token cost, error recovery, and code complexity across 30 standardized queries. The application analyzes open-source project health by pulling data from four public APIs simultaneously.

### Why this matters

As of March 2026, MCP has 97M+ monthly SDK downloads and A2A has been adopted by 50+ enterprise partners. Every team building AI agents asks: "Should I use MCP, A2A, or both?" The only existing comparison (arXiv:2505.02279) is theoretical. **Nobody has published empirical benchmarks. This project fills that gap.**

### The Demo Application: Open Source Health Analyzer

User asks natural language questions about open-source projects:

```
"Compare React vs Vue vs Svelte — which project is healthiest?"
"Is Express.js still actively maintained?"
"Show me security vulnerabilities in the top 5 Python web frameworks"
"How does Fastify's community engagement compare to Koa?"
```

The system pulls data from **four free public APIs**:

| API | What it provides | Auth |
|-----|-----------------|------|
| **GitHub REST API** | Stars, forks, issues, PRs, contributors, commit frequency | Free token |
| **npm Registry API** | Downloads, dependencies, bundle size, versions | No auth |
| **OSV.dev API** (Google) | Known vulnerabilities by package | No auth |
| **StackOverflow API** | Question volume, answer rate, tag activity | No auth |

### Three Architectures, Same Task

#### Architecture A: MCP-Only (Single Agent + Tool Servers)

```
         User Query
              │
     ┌────────▼────────┐
     │  Single Agent    │
     │  (one LLM brain) │
     └──┬──┬──┬──┬─────┘
        │  │  │  │
        ▼  ▼  ▼  ▼
      MCP  MCP  MCP  MCP
      Server Server Server Server
      GitHub npm  OSV  StackOverflow
```

One agent orchestrates everything. Each API is wrapped in an MCP server. Agent decides which tools to call and in what order. All results flow back into one context window.

**Strengths:** Simple setup, easy debugging, less infrastructure.
**Weaknesses:** Context window grows with every tool response. Complex multi-source queries overload the single agent.

#### Architecture B: A2A Multi-Agent

```
         User Query
              │
     ┌────────▼─────────┐
     │  Coordinator      │ (A2A Client)
     │  Agent            │
     └──┬──┬──┬──┬──────┘
        │  │  │  │  A2A task delegation
        ▼  ▼  ▼  ▼
     ┌─────┐┌────┐┌────┐┌──────────┐
     │GitHub││npm ││OSV ││StackOver │
     │Agent ││Agent││Agent││flow Agent│
     │(MCP) ││(MCP)││(MCP)││(MCP)    │
     └─────┘└────┘└────┘└──────────┘
```

Coordinator delegates subtasks via A2A. Each specialist agent owns its domain and has its own MCP connection. Specialists return structured results. Coordinator synthesizes.

**Strengths:** Parallel execution, independent failure domains, scalable.
**Weaknesses:** More infrastructure, delegation overhead on simple queries, harder to debug.

#### Architecture C: Hybrid (Smart Routing)

```
         User Query
              │
     ┌────────▼─────────┐
     │  Coordinator      │
     │  + Router Logic   │
     └──┬────────┬───────┘
        │        │
   Simple?    Complex?
     MCP        A2A
   (direct)   (delegate)
```

A routing layer classifies query complexity. Simple single-source queries go through MCP directly. Complex multi-source queries get delegated to specialist agents via A2A.

**Strengths:** Best of both worlds. Fast for simple, robust for complex.
**Weaknesses:** Routing logic adds a decision layer that must be tuned.

### Benchmark Suite: 30 Queries

#### Simple (10 queries — single source, single project)
Expected: MCP wins (less overhead)

1. "How many stars does React have?"
2. "What's the weekly npm download count for express?"
3. "Are there any critical vulnerabilities in lodash?"
4. "How many open issues does Vue have?"
5. "What's the latest version of Next.js on npm?"
6. "How many StackOverflow questions are tagged 'svelte'?"
7. "When was the last commit to fastify?"
8. "How many contributors does Django have?"
9. "What's the bundle size of axios?"
10. "Is TensorFlow.js actively maintained?"

#### Medium (10 queries — multi-source, single project)
Expected: Close race, slight A2A advantage

11. "Give me a full health report on Express.js"
12. "Is Deno a safer alternative to Node.js? Compare vulnerabilities and community"
13. "How healthy is the Vue ecosystem — downloads, issues, security?"
14. "Should I adopt Bun? Check GitHub activity, npm adoption, and known issues"
15. "Compare Fastify's maintainer activity vs community engagement"
16. "Is Remix gaining traction? Check GitHub, npm, and StackOverflow trends"
17. "Give me a risk assessment for using Prisma in production"
18. "How's Angular doing — downloads, vulnerabilities, and community support?"
19. "Is Flask still relevant? Check all health indicators"
20. "Evaluate Tailwind CSS — security, adoption, and development velocity"

#### Complex (10 queries — multi-source, multi-project comparison)
Expected: A2A wins (parallel delegation, independent failures)

21. "Compare React vs Vue vs Svelte across all health metrics"
22. "Rank the top 5 Node.js web frameworks by overall project health"
23. "Which Python web framework has the best security posture — Django, Flask, or FastAPI?"
24. "Compare the ecosystem health of Vite vs Webpack vs Turbopack"
25. "Is the JavaScript ORM space healthy? Compare Prisma, Drizzle, TypeORM, and Sequelize"
26. "Rank React state management libs by community health: Redux, Zustand, Jotai, Recoil"
27. "Cross-reference GitHub activity with npm downloads for the top 5 CSS frameworks"
28. "Which testing framework is healthiest — Jest, Vitest, or Playwright?"
29. "Full ecosystem comparison: Next.js vs Nuxt vs SvelteKit"
30. "Build a health dashboard for the top 10 most downloaded npm packages"

### What We Measure (per query, per architecture, 5 runs each = 450 total runs)

| Metric | How measured |
|--------|-------------|
| **Latency (ms)** | Wall clock time from query to complete response |
| **LLM tokens consumed** | Sum of all Reasoner + Synthesizer tokens |
| **Number of LLM calls** | Total API calls to Claude |
| **Number of API calls** | Total calls to GitHub/npm/OSV/SO |
| **Error recovery** | Does the system still produce results if one API fails? |
| **Cold start time** | Time to first useful output |
| **Code complexity (LOC)** | Lines of code for each implementation |
| **Hallucination rate** | Manual spot-check: did any response contain fabricated data? |

### Expected Findings (the paper's contribution)

```
    Latency (ms)
    │
    │                          ╱ MCP (context overload)
800 │                       ╱
    │                    ╱
600 │              ╱──── A2A (delegation overhead)
    │         ╱────
400 │    ╱────        ──── Hybrid (routes smartly)
    │───
200 │
    └──────────────────────────────
      Simple     Medium     Complex
         Query Complexity →
```

**The decision framework:**
- Query touches **1 source** → MCP (no delegation needed)
- Query touches **2+ sources for the same project** → Either works, MCP slightly faster
- Query touches **2+ sources for multiple projects** → A2A (parallel, isolated failures)
- **Unknown complexity at runtime** → Hybrid with routing

### Tech Stack

- **Python 3.11+** + **FastAPI** backend
- **Streamlit** frontend with Plotly charts
- **MCP SDK**: `mcp` Python package (Anthropic official)
- **A2A SDK**: Google's A2A Python SDK
- **LLM**: Claude API (claude-sonnet-4-20250514) — same model for all architectures
- **APIs**: GitHub REST, npm Registry, OSV.dev, StackOverflow — all free

### Project Structure

```
mcp-vs-a2a-bench/
├── README.md
├── requirements.txt
├── app.py                              # Streamlit UI: run queries, see results, compare
│
├── shared/
│   ├── github_client.py                # GitHub REST API wrapper
│   ├── npm_client.py                   # npm Registry API wrapper
│   ├── osv_client.py                   # OSV.dev API wrapper
│   ├── stackoverflow_client.py         # StackOverflow API wrapper
│   ├── models.py                       # Pydantic: HealthReport, QueryPlan, BenchmarkResult
│   └── metrics.py                      # Token counting, latency tracking
│
├── mcp_only/
│   ├── agent.py                        # Single agent with 4 MCP tool connections
│   ├── github_mcp_server.py            # MCP server: GitHub tools
│   ├── npm_mcp_server.py               # MCP server: npm tools
│   ├── osv_mcp_server.py               # MCP server: OSV tools
│   └── stackoverflow_mcp_server.py     # MCP server: StackOverflow tools
│
├── a2a_multi/
│   ├── coordinator.py                  # A2A client: delegates to specialists
│   ├── github_agent.py                 # A2A server + MCP client for GitHub
│   ├── npm_agent.py                    # A2A server + MCP client for npm
│   ├── osv_agent.py                    # A2A server + MCP client for OSV
│   ├── stackoverflow_agent.py          # A2A server + MCP client for SO
│   └── agent_cards/                    # A2A Agent Card JSON definitions
│       ├── github_agent_card.json
│       ├── npm_agent_card.json
│       ├── osv_agent_card.json
│       └── stackoverflow_agent_card.json
│
├── hybrid/
│   ├── coordinator.py                  # Hybrid: routes by complexity
│   └── router.py                       # Classification: simple → MCP, complex → A2A
│
├── benchmark/
│   ├── queries.json                    # All 30 benchmark queries with metadata
│   ├── run_benchmark.py                # Execute all queries × 3 architectures × 5 runs
│   ├── analyze_results.py              # Generate comparison tables and charts
│   └── results/                        # Raw JSON results + generated figures
│
└── paper/
    └── figures/                        # Publication-ready charts (auto-generated)
```

### Streamlit UI

```
┌──────────────────────────────────────────┐
│  mcp-vs-a2a-bench                        │
│  Open Source Health Analyzer             │
├──────────────────────────────────────────┤
│                                          │
│  Architecture: [MCP] [A2A] [Hybrid] [All]│
│                                          │
│  Query: "Compare React vs Vue vs Svelte" │
│  [Run Query]  [Run Benchmark Suite]      │
│                                          │
│  ┌─── Pipeline View ──────────────────┐  │
│  │ 🧠 Agent: Parsing intent...       │  │
│  │ ⚙️ GitHub: fetching 3 repos...    │  │
│  │ ⚙️ npm: fetching download stats...│  │
│  │ ⚙️ OSV: checking vulns...        │  │
│  │ ⚙️ SO: fetching tag stats...     │  │
│  │ 📊 Synthesizing report...         │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌─── Health Radar Chart ─────────────┐  │
│  │      Stars                         │  │
│  │       ╱╲                           │  │
│  │  Sec ╱  ╲ Downloads               │  │
│  │     ╱ ●  ╲                        │  │
│  │    ╱      ╲                       │  │
│  │   Community  Issues               │  │
│  │  React ● Vue ● Svelte ●          │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌─── Metrics Comparison ─────────────┐  │
│  │         MCP    A2A    Hybrid       │  │
│  │ Latency: 2.1s  1.8s   1.4s        │  │
│  │ Tokens:  4200   3100   2800        │  │
│  │ LLM calls: 1    5      3           │  │
│  │ API calls: 12   12     12          │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### Paper This Supports

**"MCP vs A2A: An Empirical Comparison of Agent Communication Protocols for Enterprise Task Orchestration"**

Target: Ukrainian Category B journal + arXiv preprint

### License

MIT — open source, free to use, fork, and extend.
