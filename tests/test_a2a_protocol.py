"""Tests for A2A protocol models and server."""

import pytest
from a2a_multi.a2a_models import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
    DataPart,
)


class TestTaskLifecycle:
    def test_initial_state(self):
        task = Task()
        assert task.status.state == TaskState.SUBMITTED
        assert task.id  # Should have UUID

    def test_state_transitions(self):
        task = Task()
        assert task.status.state == TaskState.SUBMITTED

        task.status = TaskStatus(state=TaskState.WORKING)
        assert task.status.state == TaskState.WORKING

        task.status = TaskStatus(
            state=TaskState.COMPLETED,
            message=Message(role="agent", parts=[TextPart(text="done")]),
        )
        assert task.status.state == TaskState.COMPLETED
        assert task.status.message.parts[0].text == "done"

    def test_failed_state(self):
        task = Task()
        task.status = TaskStatus(
            state=TaskState.FAILED,
            message=Message(role="agent", parts=[TextPart(text="Error: timeout")]),
        )
        assert task.status.state == TaskState.FAILED

    def test_canceled_state(self):
        task = Task()
        task.status = TaskStatus(state=TaskState.CANCELED)
        assert task.status.state == TaskState.CANCELED


class TestJSONRPC:
    def test_request(self):
        req = JSONRPCRequest(method="tasks/send", params={"id": "123"})
        assert req.jsonrpc == "2.0"
        assert req.method == "tasks/send"
        assert req.params["id"] == "123"

    def test_response_success(self):
        resp = JSONRPCResponse(id="1", result={"status": "ok"})
        assert resp.error is None
        assert resp.result["status"] == "ok"

    def test_response_error(self):
        resp = JSONRPCResponse(
            id="1",
            error={"code": -32601, "message": "Method not found"},
        )
        assert resp.result is None
        assert resp.error["code"] == -32601

    def test_roundtrip(self):
        req = JSONRPCRequest(method="tasks/send", params={"id": "test"})
        data = req.model_dump()
        restored = JSONRPCRequest(**data)
        assert restored.method == "tasks/send"


class TestAgentCard:
    def test_minimal(self):
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8001",
        )
        assert card.version == "1.0.0"
        assert card.capabilities.streaming is False

    def test_with_skills(self):
        card = AgentCard(
            name="GitHub Agent",
            description="GitHub specialist",
            url="http://localhost:8001",
            skills=[
                AgentSkill(
                    id="repo-analysis",
                    name="Repo Analysis",
                    description="Analyzes repos",
                    tags=["github"],
                ),
            ],
        )
        assert len(card.skills) == 1
        assert card.skills[0].id == "repo-analysis"

    def test_serialization(self):
        card = AgentCard(
            name="Test",
            description="Test",
            url="http://localhost:8001",
        )
        data = card.model_dump()
        assert data["name"] == "Test"
        assert "capabilities" in data


class TestMessageParts:
    def test_text_part(self):
        part = TextPart(text="Hello")
        assert part.type == "text"
        assert part.text == "Hello"

    def test_data_part(self):
        part = DataPart(data={"stars": 1000})
        assert part.type == "data"
        assert part.data["stars"] == 1000

    def test_message_with_parts(self):
        msg = Message(
            role="user",
            parts=[
                TextPart(text="Analyze React"),
                DataPart(data={"projects": ["react"]}),
            ],
        )
        assert msg.role == "user"
        assert len(msg.parts) == 2
