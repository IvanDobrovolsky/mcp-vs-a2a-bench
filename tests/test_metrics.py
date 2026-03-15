"""Tests for metrics collection and cost computation."""

import time

import pytest
from shared.metrics import MetricsCollector, compute_cost, estimate_tokens


class TestComputeCost:
    def test_zero_tokens(self):
        assert compute_cost(0, 0) == 0.0

    def test_input_only(self):
        # 1M input tokens at $3/M = $3.00
        cost = compute_cost(1_000_000, 0)
        assert cost == pytest.approx(3.00)

    def test_output_only(self):
        # 1M output tokens at $15/M = $15.00
        cost = compute_cost(0, 1_000_000)
        assert cost == pytest.approx(15.00)

    def test_mixed(self):
        # 500 input + 100 output
        cost = compute_cost(500, 100)
        expected = (500 / 1_000_000) * 3.00 + (100 / 1_000_000) * 15.00
        assert cost == pytest.approx(expected)

    def test_realistic_query(self):
        # Typical single query: ~2000 input, ~500 output
        cost = compute_cost(2000, 500)
        assert cost > 0
        assert cost < 0.05  # Should be well under 5 cents


class TestMetricsCollector:
    def test_initial_state(self):
        m = MetricsCollector()
        assert m.total_tokens == 0
        assert m.llm_calls == 0
        assert m.cost_usd == 0.0

    def test_record_llm_usage(self):
        m = MetricsCollector()
        m.record_llm_usage(1000, 200)
        assert m.llm_calls == 1
        assert m.total_tokens == 1200
        assert m.prompt_tokens == 1000
        assert m.completion_tokens == 200
        assert m.cost_usd > 0

    def test_multiple_llm_calls_accumulate(self):
        m = MetricsCollector()
        m.record_llm_usage(1000, 200)
        m.record_llm_usage(500, 100)
        assert m.llm_calls == 2
        assert m.total_tokens == 1800
        assert m.cost_usd == pytest.approx(
            compute_cost(1000, 200) + compute_cost(500, 100)
        )

    def test_api_calls(self):
        m = MetricsCollector()
        m.record_api_call()
        m.record_api_call()
        assert m.api_calls == 2

    def test_errors(self):
        m = MetricsCollector()
        m.record_error("timeout")
        m.record_error("500")
        assert len(m.errors) == 2

    def test_latency_tracking(self):
        m = MetricsCollector()
        m.start()
        time.sleep(0.01)  # 10ms
        m.stop()
        assert m.latency_ms >= 10

    def test_cold_start(self):
        m = MetricsCollector()
        m.start()
        time.sleep(0.01)
        m.mark_first_output()
        assert m.cold_start_ms >= 10
        # Second call should not update
        time.sleep(0.01)
        m.mark_first_output()
        assert m.cold_start_ms < 30  # Still the first measurement

    def test_context_manager(self):
        m = MetricsCollector()
        with m.track_latency():
            time.sleep(0.01)
        assert m.latency_ms >= 10


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 1  # Minimum 1

    def test_short(self):
        assert estimate_tokens("hello") >= 1

    def test_longer(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100
