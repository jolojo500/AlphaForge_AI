"""Trace helper for nodes (PRD 3.2, O-6). Orchestrator-owned."""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Callable
from typing import Any

from alphaforge import config


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")


def lookup_model_pricing(model_name: str) -> dict[str, float]:
    """Look up on-demand pricing (USD per 1M tokens) for a Bedrock model."""
    if model_name in config.BEDROCK_PRICING:
        return config.BEDROCK_PRICING[model_name]
    m_lower = model_name.lower()
    if "opus" in m_lower:
        return config.BEDROCK_PRICING["global.anthropic.claude-opus-5-5"]
    if "haiku" in m_lower:
        return config.BEDROCK_PRICING["global.anthropic.claude-haiku-5-5"]
    return config.BEDROCK_PRICING["global.anthropic.claude-sonnet-5-5"]


def _usd_to_cad() -> float:
    """Last published Bank of Canada USD/CAD rate in the dataset (fallback: config)."""
    try:
        from alphaforge.data.provider import get_provider

        return float(get_provider().fx()["usdcad"].dropna().iloc[-1])
    except Exception:  # noqa: BLE001
        return config.USD_TO_CAD_RATE


def calculate_run_cost(trace: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Calculate token totals, latency and cost in CAD for a run based on its trace.

    Prices: config.BEDROCK_PRICING (Anthropic list prices used as an estimate of Bedrock
    cost, cited with their source and date). USD→CAD: last Bank of Canada rate in the data.
    """
    total_input = 0
    total_output = 0
    total_latency = 0
    total_calls = 0
    total_cost_usd = 0.0

    models_data: dict[str, dict[str, Any]] = {}

    for entry in trace or []:
        if not isinstance(entry, dict):
            continue
        # Only LLM nodes have "model" or "input_tokens" or "calls"
        if "model" not in entry and "input_tokens" not in entry and "calls" not in entry:
            continue

        model = entry.get("model") or config.MODEL_MAIN
        calls = int(entry.get("calls", 1))
        in_tok = int(entry.get("input_tokens", 0))
        out_tok = int(entry.get("output_tokens", 0))
        lat_ms = int(entry.get("latency_ms", 0))

        pricing = lookup_model_pricing(model)
        item_cost_usd = (
            in_tok * pricing["input_usd_per_1m"] + out_tok * pricing["output_usd_per_1m"]
        ) / 1_000_000.0

        total_input += in_tok
        total_output += out_tok
        total_latency += lat_ms
        total_calls += calls
        total_cost_usd += item_cost_usd

        if model not in models_data:
            models_data[model] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
                "cost_cad": 0.0,
            }
        m = models_data[model]
        m["calls"] += calls
        m["input_tokens"] += in_tok
        m["output_tokens"] += out_tok
        m["total_tokens"] += in_tok + out_tok
        m["latency_ms"] += lat_ms
        m["cost_usd"] += item_cost_usd
        m["cost_cad"] += item_cost_usd * _usd_to_cad()

    for m in models_data.values():
        m["cost_usd"] = round(m["cost_usd"], 6)
        m["cost_cad"] = round(m["cost_cad"], 6)

    total_cost_cad = total_cost_usd * _usd_to_cad()

    return {
        "cost_cad": round(total_cost_cad, 6),
        "cost_usd": round(total_cost_usd, 6),
        "total_tokens": total_input + total_output,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_latency_ms": total_latency,
        "calls": total_calls,
        "is_estimate": True,
        "pricing_source": config.BEDROCK_PRICE_SOURCE_URL,
        "pricing_date": config.BEDROCK_PRICE_DATE,
        "pricing_basis": config.BEDROCK_PRICE_BASIS,
        "usd_to_cad_rate": _usd_to_cad(),
        "confidence": "assumption",
        "models": models_data,
    }


def traced(name: str) -> Callable:
    """Wrap a node so it appends one trace entry.

    The node returns its partial state update plus an optional `summary` key: one
    user-facing sentence (French), never model reasoning. The wrapper removes `summary`
    and turns it into `{"node", "started_at", "ended_at", "summary"}` under `trace`.
    When the node made LLM calls, adds {"model", "calls", "input_tokens", "output_tokens", "latency_ms"}.
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state, *args, **kwargs):
            started = _now()
            from alphaforge.llm import track_llm_usage

            with track_llm_usage() as usage_list:
                update = dict(fn(state, *args, **kwargs) or {})

            summary = update.pop("summary", "")
            entry: dict[str, Any] = {
                "node": name,
                "started_at": started,
                "ended_at": _now(),
                "summary": summary,
            }
            if usage_list:
                total_in = sum(u.get("input_tokens", 0) for u in usage_list)
                total_out = sum(u.get("output_tokens", 0) for u in usage_list)
                total_lat = sum(u.get("latency_ms", 0) for u in usage_list)
                models = list(dict.fromkeys(u["model"] for u in usage_list if "model" in u))
                entry["model"] = models[0] if len(models) == 1 else ", ".join(models)
                entry["calls"] = len(usage_list)
                entry["input_tokens"] = total_in
                entry["output_tokens"] = total_out
                entry["latency_ms"] = total_lat

            update["trace"] = [entry]
            return update

        return wrapper

    return deco
