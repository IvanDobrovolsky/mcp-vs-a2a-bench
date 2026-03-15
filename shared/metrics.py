"""Token counting, latency tracking, and cost estimation utilities."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional


# Claude Sonnet pricing (per million tokens) — update if model changes
# Source: Anthropic pricing page
PRICING = {
    "claude-sonnet-4-20250514": {
        "input_per_million": 3.00,   # $3.00 per 1M input tokens
        "output_per_million": 15.00,  # $15.00 per 1M output tokens
    },
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    """Compute cost in USD for a given token usage."""
    pricing = PRICING.get(model, PRICING[DEFAULT_MODEL])
    input_cost = (prompt_tokens / 1_000_000) * pricing["input_per_million"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output_per_million"]
    return input_cost + output_cost


@dataclass
class MetricsCollector:
    """Collects metrics for a single query execution."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    api_calls: int = 0
    latency_ms: float = 0.0
    cold_start_ms: float = 0.0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    _start_time: Optional[float] = None
    _first_output_time: Optional[float] = None

    def start(self) -> None:
        self._start_time = time.perf_counter()

    def mark_first_output(self) -> None:
        if self._first_output_time is None and self._start_time is not None:
            self._first_output_time = time.perf_counter()
            self.cold_start_ms = (self._first_output_time - self._start_time) * 1000

    def stop(self) -> None:
        if self._start_time is not None:
            self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def record_llm_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.llm_calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.cost_usd += compute_cost(prompt_tokens, completion_tokens)

    def record_api_call(self) -> None:
        self.api_calls += 1

    def record_error(self, error: str) -> None:
        self.errors.append(error)

    @contextmanager
    def track_latency(self) -> Generator[None, None, None]:
        self.start()
        try:
            yield
        finally:
            self.stop()


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)
