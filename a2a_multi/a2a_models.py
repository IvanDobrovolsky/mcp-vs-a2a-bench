"""A2A protocol models — implements the Google A2A spec over JSON-RPC/HTTP."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ── Task Lifecycle ──


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ── Message Parts ──


class TextPart(BaseModel):
    type: str = "text"
    text: str


class DataPart(BaseModel):
    type: str = "data"
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Messages ──


class Message(BaseModel):
    role: str  # "user" or "agent"
    parts: List[Union[TextPart, DataPart]] = Field(default_factory=list)


# ── Task ──


class TaskStatus(BaseModel):
    state: TaskState = TaskState.SUBMITTED
    message: Optional[Message] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = Field(default_factory=TaskStatus)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    history: List[Message] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── JSON-RPC ──


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


# ── Agent Card ──


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: List[AgentSkill] = Field(default_factory=list)
    defaultInputModes: List[str] = Field(default_factory=lambda: ["text"])
    defaultOutputModes: List[str] = Field(default_factory=lambda: ["text"])
