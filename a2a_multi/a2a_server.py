"""Base A2A server — each specialist agent extends this.

Implements the A2A protocol:
- GET  /.well-known/agent.json  → Agent Card discovery
- POST /                        → JSON-RPC endpoint (tasks/send, tasks/get, tasks/cancel)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from a2a_multi.a2a_models import (
    AgentCard,
    DataPart,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)

logger = logging.getLogger(__name__)


class A2AServer:
    """Base A2A-compliant HTTP server.

    Subclasses implement `process_task(query, projects)` → dict with response data.
    """

    def __init__(self, agent_card: AgentCard):
        self.agent_card = agent_card
        self.app = FastAPI(title=agent_card.name)
        self.tasks: dict[str, Task] = {}

        # Register routes
        self.app.get("/.well-known/agent.json")(self._serve_agent_card)
        self.app.post("/")(self._handle_jsonrpc)

    async def _serve_agent_card(self) -> JSONResponse:
        """Serve the Agent Card for discovery."""
        return JSONResponse(self.agent_card.model_dump())

    async def _handle_jsonrpc(self, request: Request) -> JSONResponse:
        """Handle JSON-RPC requests per A2A spec."""
        body = await request.json()
        rpc_req = JSONRPCRequest(**body)

        if rpc_req.method == "tasks/send":
            return await self._handle_task_send(rpc_req)
        elif rpc_req.method == "tasks/get":
            return await self._handle_task_get(rpc_req)
        elif rpc_req.method == "tasks/cancel":
            return await self._handle_task_cancel(rpc_req)
        else:
            return JSONResponse(
                JSONRPCResponse(
                    id=rpc_req.id,
                    error={"code": -32601, "message": f"Method not found: {rpc_req.method}"},
                ).model_dump()
            )

    async def _handle_task_send(self, rpc_req: JSONRPCRequest) -> JSONResponse:
        """Handle tasks/send — create and execute a task."""
        params = rpc_req.params
        task_id = params.get("id", str(uuid.uuid4()))
        message_data = params.get("message", {})

        # Parse the incoming message
        query = ""
        projects = []
        metadata = params.get("metadata", {})

        for part in message_data.get("parts", []):
            if part.get("type") == "text":
                query = part["text"]
            elif part.get("type") == "data":
                projects = part.get("data", {}).get("projects", [])

        # Also check metadata for projects
        if not projects and "projects" in metadata:
            projects = metadata["projects"]

        # Create task in SUBMITTED state
        task = Task(
            id=task_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            history=[Message(role="user", parts=[TextPart(text=query)])],
            metadata=metadata,
        )
        self.tasks[task_id] = task

        # Transition to WORKING
        task.status = TaskStatus(state=TaskState.WORKING)

        try:
            # Execute the domain-specific logic (implemented by subclass)
            result = await self.process_task(query, projects if projects else None)

            # Transition to COMPLETED with results
            response_parts: list[TextPart | DataPart] = []
            if result.get("response"):
                response_parts.append(TextPart(text=result["response"]))
            if result.get("data"):
                response_parts.append(DataPart(data=result["data"]))

            task.status = TaskStatus(
                state=TaskState.COMPLETED,
                message=Message(role="agent", parts=response_parts),
            )

            # Store artifacts (raw data + metrics)
            task.artifacts = [
                {"type": "data", "data": result.get("data", {})},
                {"type": "metrics", "data": result.get("metrics", {})},
            ]
            if result.get("errors"):
                task.metadata["errors"] = result["errors"]

        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message=Message(role="agent", parts=[TextPart(text=f"Error: {str(e)}")]),
            )

        return JSONResponse(
            JSONRPCResponse(
                id=rpc_req.id,
                result=task.model_dump(),
            ).model_dump()
        )

    async def _handle_task_get(self, rpc_req: JSONRPCRequest) -> JSONResponse:
        """Handle tasks/get — return task status."""
        task_id = rpc_req.params.get("id", "")
        task = self.tasks.get(task_id)

        if not task:
            return JSONResponse(
                JSONRPCResponse(
                    id=rpc_req.id,
                    error={"code": -32602, "message": f"Task not found: {task_id}"},
                ).model_dump()
            )

        return JSONResponse(
            JSONRPCResponse(
                id=rpc_req.id,
                result=task.model_dump(),
            ).model_dump()
        )

    async def _handle_task_cancel(self, rpc_req: JSONRPCRequest) -> JSONResponse:
        """Handle tasks/cancel — cancel a task."""
        task_id = rpc_req.params.get("id", "")
        task = self.tasks.get(task_id)

        if not task:
            return JSONResponse(
                JSONRPCResponse(
                    id=rpc_req.id,
                    error={"code": -32602, "message": f"Task not found: {task_id}"},
                ).model_dump()
            )

        task.status = TaskStatus(state=TaskState.CANCELED)
        return JSONResponse(
            JSONRPCResponse(
                id=rpc_req.id,
                result=task.model_dump(),
            ).model_dump()
        )

    async def process_task(self, query: str, projects: list[str] | None) -> dict:
        """Override in subclass. Returns dict with 'response', 'data', 'errors', 'metrics'."""
        raise NotImplementedError
