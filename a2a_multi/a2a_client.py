"""A2A client — used by the coordinator to discover and delegate to specialist agents over HTTP."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from a2a_multi.a2a_models import AgentCard, JSONRPCRequest, Task, TaskState


class A2AClient:
    """Client for communicating with A2A-compliant agent servers."""

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._agent_card: AgentCard | None = None

    async def get_agent_card(self) -> AgentCard:
        """Discover agent capabilities via Agent Card endpoint."""
        if self._agent_card:
            return self._agent_card

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/.well-known/agent.json")
            resp.raise_for_status()
            self._agent_card = AgentCard(**resp.json())
            return self._agent_card

    async def send_task(
        self,
        query: str,
        projects: list[str] | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Send a task to the agent via JSON-RPC tasks/send."""
        if task_id is None:
            task_id = str(uuid.uuid4())

        parts: list[dict] = [{"type": "text", "text": query}]
        if projects:
            parts.append({"type": "data", "data": {"projects": projects}})

        rpc_request = JSONRPCRequest(
            method="tasks/send",
            params={
                "id": task_id,
                "message": {
                    "role": "user",
                    "parts": parts,
                },
                "metadata": metadata or {},
            },
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/",
                json=rpc_request.model_dump(),
            )
            resp.raise_for_status()
            rpc_response = resp.json()

        if rpc_response.get("error"):
            raise RuntimeError(
                f"A2A error: {rpc_response['error'].get('message', 'Unknown error')}"
            )

        return Task(**rpc_response["result"])

    async def get_task(self, task_id: str) -> Task:
        """Get task status via JSON-RPC tasks/get."""
        rpc_request = JSONRPCRequest(
            method="tasks/get",
            params={"id": task_id},
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/",
                json=rpc_request.model_dump(),
            )
            resp.raise_for_status()
            rpc_response = resp.json()

        if rpc_response.get("error"):
            raise RuntimeError(
                f"A2A error: {rpc_response['error'].get('message', 'Unknown error')}"
            )

        return Task(**rpc_response["result"])

    async def cancel_task(self, task_id: str) -> Task:
        """Cancel a task via JSON-RPC tasks/cancel."""
        rpc_request = JSONRPCRequest(
            method="tasks/cancel",
            params={"id": task_id},
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/",
                json=rpc_request.model_dump(),
            )
            resp.raise_for_status()
            rpc_response = resp.json()

        return Task(**rpc_response["result"])

    def extract_response_text(self, task: Task) -> str:
        """Extract the text response from a completed task."""
        if task.status.message:
            for part in task.status.message.parts:
                if hasattr(part, "text"):
                    return part.text
        return ""

    def extract_response_data(self, task: Task) -> dict:
        """Extract structured data from task artifacts."""
        for artifact in task.artifacts:
            if artifact.get("type") == "data":
                return artifact.get("data", {})
        return {}

    def extract_metrics(self, task: Task) -> dict:
        """Extract metrics from task artifacts."""
        for artifact in task.artifacts:
            if artifact.get("type") == "metrics":
                return artifact.get("data", {})
        return {}
