"""Launch all A2A specialist agent servers.

Usage:
    python -m a2a_multi.launch          # Start all 4 agents
    python -m a2a_multi.launch github   # Start only GitHub agent
    python -m a2a_multi.launch --check  # Check if agents are running
"""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import signal
import sys
import time

import httpx
import uvicorn


AGENTS = {
    "github": {"module": "a2a_multi.github_agent:app", "port": 8001},
    "npm": {"module": "a2a_multi.npm_agent:app", "port": 8002},
    "osv": {"module": "a2a_multi.osv_agent:app", "port": 8003},
    "stackoverflow": {"module": "a2a_multi.stackoverflow_agent:app", "port": 8004},
}


def _run_agent(module: str, port: int):
    """Run a single agent server in a subprocess."""
    uvicorn.run(module, host="0.0.0.0", port=port, log_level="info")


async def check_agents():
    """Check which agents are running by hitting their Agent Card endpoints."""
    print("Checking A2A agent status...\n")
    async with httpx.AsyncClient(timeout=5) as client:
        for name, config in AGENTS.items():
            url = f"http://localhost:{config['port']}/.well-known/agent.json"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    card = resp.json()
                    print(f"  [UP]   {name:15s} port {config['port']}  ({card['name']})")
                else:
                    print(f"  [DOWN] {name:15s} port {config['port']}  (HTTP {resp.status_code})")
            except Exception:
                print(f"  [DOWN] {name:15s} port {config['port']}  (not reachable)")


def launch(agent_names: list[str] | None = None):
    """Launch agent servers as subprocesses."""
    if agent_names is None:
        agent_names = list(AGENTS.keys())

    processes: list[multiprocessing.Process] = []

    print("Starting A2A agent servers...\n")

    for name in agent_names:
        if name not in AGENTS:
            print(f"Unknown agent: {name}")
            continue

        config = AGENTS[name]
        p = multiprocessing.Process(
            target=_run_agent,
            args=(config["module"], config["port"]),
            daemon=True,
        )
        p.start()
        processes.append(p)
        print(f"  Started {name:15s} on port {config['port']} (PID {p.pid})")

    print(f"\n{len(processes)} agent(s) started. Press Ctrl+C to stop all.\n")

    # Wait for agents to be ready
    time.sleep(2)
    asyncio.run(check_agents())

    # Wait for interrupt
    def signal_handler(sig, frame):
        print("\nShutting down agents...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join(timeout=5)
        print("All agents stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Keep main process alive
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        signal_handler(None, None)


def main():
    parser = argparse.ArgumentParser(description="Launch A2A agent servers")
    parser.add_argument("agents", nargs="*", help="Specific agents to launch (default: all)")
    parser.add_argument("--check", action="store_true", help="Check agent status only")
    args = parser.parse_args()

    if args.check:
        asyncio.run(check_agents())
    else:
        launch(args.agents if args.agents else None)


if __name__ == "__main__":
    main()
