"""Tests for trace telemetry, node tracing wrapper, and run cost estimation (O-6)."""

import pytest
from pydantic import BaseModel

from alphaforge import config, llm
from alphaforge.tracing import calculate_run_cost, lookup_model_pricing, traced


class Out(BaseModel):
    label: str
    score: float


class FakeMsg:
    def __init__(self, content, in_tok=50, out_tok=25):
        self.content = content
        self.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}


class FakeLLM:
    def __init__(self, model_id="global.anthropic.claude-sonnet-5-5", in_tok=100, out_tok=50):
        self.model_id = model_id
        self.in_tok = in_tok
        self.out_tok = out_tok

    def invoke(self, messages):
        return FakeMsg('{"label": "ok", "score": 1.0}', self.in_tok, self.out_tok)


def test_traced_decorator_without_llm_calls():
    @traced("quant")
    def deterministic_node(state):
        return {"summary": "Calcul déterministe achevé."}

    res = deterministic_node({})
    assert "trace" in res
    assert len(res["trace"]) == 1
    entry = res["trace"][0]
    assert entry["node"] == "quant"
    assert entry["summary"] == "Calcul déterministe achevé."
    assert "started_at" in entry and "ended_at" in entry
    # No LLM calls -> no LLM telemetry keys
    assert "model" not in entry
    assert "calls" not in entry
    assert "input_tokens" not in entry
    assert "output_tokens" not in entry
    assert "latency_ms" not in entry


def test_traced_decorator_with_llm_calls():
    fake = FakeLLM("global.anthropic.claude-sonnet-5-5", in_tok=120, out_tok=45)

    @traced("explain")
    def llm_node(state):
        out = llm.call_json("Generate explanation", Out, llm=fake)
        return {"summary": "Explication rédigée.", "score": out.score}

    res = llm_node({})
    assert res["score"] == 1.0
    assert "trace" in res
    entry = res["trace"][0]
    assert entry["node"] == "explain"
    assert entry["summary"] == "Explication rédigée."
    # LLM telemetry keys must be present (Issue #131 contract)
    assert entry["model"] == "global.anthropic.claude-sonnet-5-5"
    assert entry["calls"] == 1
    assert entry["input_tokens"] == 120
    assert entry["output_tokens"] == 45
    assert entry["latency_ms"] >= 0


def test_lookup_model_pricing():
    sonnet = lookup_model_pricing("global.anthropic.claude-sonnet-5-5")
    assert sonnet["input_usd_per_1m"] == 2.00
    assert sonnet["output_usd_per_1m"] == 10.00

    haiku = lookup_model_pricing("global.anthropic.claude-haiku-5-5")
    assert haiku["input_usd_per_1m"] == 0.10
    assert haiku["output_usd_per_1m"] == 0.50

    opus = lookup_model_pricing("global.anthropic.claude-opus-5-5")
    assert opus["input_usd_per_1m"] == 4.00
    assert opus["output_usd_per_1m"] == 20.00

    # Fallback by substring
    assert lookup_model_pricing("anthropic.claude-haiku-v1")["input_usd_per_1m"] == 0.10
    assert lookup_model_pricing("anthropic.claude-opus-v1")["input_usd_per_1m"] == 4.00
    assert lookup_model_pricing("unknown-model")["input_usd_per_1m"] == 2.00


def test_calculate_run_cost_empty_trace():
    cost = calculate_run_cost([])
    assert cost["total_tokens"] == 0
    assert cost["input_tokens"] == 0
    assert cost["output_tokens"] == 0
    assert cost["total_latency_ms"] == 0
    assert cost["calls"] == 0
    assert cost["cost_cad"] == 0.0
    assert cost["cost_usd"] == 0.0
    assert cost["is_estimate"] is True
    assert cost["pricing_source"] == config.BEDROCK_PRICE_SOURCE_URL
    assert cost["pricing_date"] == config.BEDROCK_PRICE_DATE
    assert cost["usd_to_cad_rate"] == pytest.approx(1.4255)  # last Bank of Canada rate in the data
    assert cost["confidence"] == "assumption"


def test_calculate_run_cost_with_llm_entries():
    trace = [
        {"node": "quant", "started_at": "...", "ended_at": "...", "summary": "Det"},
        {
            "node": "profile",
            "started_at": "...",
            "ended_at": "...",
            "summary": "Profile resolved",
            "model": "global.anthropic.claude-sonnet-5-5",
            "calls": 1,
            "input_tokens": 1000,
            "output_tokens": 200,
            "latency_ms": 450,
        },
        {
            "node": "events",
            "started_at": "...",
            "ended_at": "...",
            "summary": "Events classified",
            "model": "global.anthropic.claude-haiku-5-5",
            "calls": 2,
            "input_tokens": 500,
            "output_tokens": 100,
            "latency_ms": 320,
        },
    ]

    cost = calculate_run_cost(trace)
    assert cost["is_estimate"] is True
    assert cost["calls"] == 3
    assert cost["input_tokens"] == 1500
    assert cost["output_tokens"] == 300
    assert cost["total_tokens"] == 1800
    assert cost["total_latency_ms"] == 770

    # Pricing calculation:
    # Sonnet: (1000 * 2.0 + 200 * 10.0) / 1M = 0.004 USD
    # Haiku: (500 * 0.10 + 100 * 0.50) / 1M = 0.0001 USD
    # Total CAD = 0.0041 * 1.4255 (Bank of Canada, 2026-11-12)
    assert cost["cost_usd"] == pytest.approx(0.0041, rel=1e-3)
    assert cost["cost_cad"] == pytest.approx(0.0041 * 1.4255, rel=1e-3)

    models = cost["models"]
    assert "global.anthropic.claude-sonnet-5-5" in models
    assert "global.anthropic.claude-haiku-5-5" in models
    assert models["global.anthropic.claude-sonnet-5-5"]["cost_usd"] == pytest.approx(0.004)
    assert models["global.anthropic.claude-haiku-5-5"]["cost_usd"] == pytest.approx(0.0001)
