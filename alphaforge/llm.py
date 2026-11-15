"""Bedrock access for the LLM nodes (PRD 2, Models and AWS). Owned by Track B.

Credentials come from the standard AWS environment (env vars or AWS_PROFILE), never from code.
Model ids and region come from `alphaforge.config`.

Sonnet 5.5 rejects forced `tool_choice`, so structured output is done in the prompt and
validated with Pydantic here, with one repair retry.

Tests and the e2e suite can inject canned replies with `set_llm_override(fn)`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from alphaforge import config

log = logging.getLogger("alphaforge.llm")

ModelKind = Literal["main", "fast"]
Messages = list[tuple[str, str]]
# fn(messages, kind) -> raw reply text. `messages` is [("system", ...), ("human", ...)] and, on a
# repair turn, also the previous ("ai", ...) reply and a new ("human", ...) correction.
Override = Callable[[Messages, str], str]

MAX_OUTPUT_TOKENS = 4096
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_override: Override | None = None


class LLMError(RuntimeError):
    """The model did not return usable JSON after the repair retry, or the call failed."""


def set_llm_override(fn: Override | None) -> None:
    """Route every `call_json` to `fn` instead of Bedrock. Pass None to restore Bedrock."""
    global _override
    _override = fn


@contextmanager
def llm_override(fn: Override) -> Iterator[None]:
    previous = _override
    set_llm_override(fn)
    try:
        yield
    finally:
        set_llm_override(previous)


def model_id(kind: ModelKind) -> str:
    if kind not in ("main", "fast"):
        raise ValueError(f"unknown model kind {kind!r}; use 'main' or 'fast'")
    return config.MODEL_MAIN if kind == "main" else config.MODEL_FAST


@lru_cache(maxsize=4)
def get_llm(kind: ModelKind = "main"):
    """A cached ChatBedrockConverse for `kind` ('main' = Sonnet, 'fast' = Haiku)."""
    from langchain_aws import ChatBedrockConverse  # lazy: keeps imports cheap in unit tests

    return ChatBedrockConverse(
        model=model_id(kind),
        region_name=config.AWS_REGION,
        max_tokens=MAX_OUTPUT_TOKENS,
    )


def _text_of(message: Any) -> str:
    """Plain text of a LangChain message, whether `content` is a string or a list of blocks."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def extract_json(text: str) -> Any:
    """Parse the first JSON object in `text`, tolerating code fences and surrounding prose."""
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE_RE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    last_error: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_error = exc
    raise ValueError(f"no valid JSON found: {last_error}")


def schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)


def _invoke(llm: Any, messages: Messages, kind: str) -> str:
    """One model call. Logs model id, latency and token usage, never the prompt content."""
    if llm is None and _override is not None:
        started = time.perf_counter()
        text = _override(messages, kind)
        log.info("llm override kind=%s latency_ms=%d", kind, (time.perf_counter() - started) * 1000)
        return text
    if llm is None:
        if os.getenv("AF_LLM_OFFLINE") == "1":
            raise LLMError("LLM calls are disabled (AF_LLM_OFFLINE=1)")
        llm = get_llm(kind)  # type: ignore[arg-type]
    started = time.perf_counter()
    msg = llm.invoke(messages)
    usage = getattr(msg, "usage_metadata", None) or {}
    log.info(
        "llm call model=%s kind=%s latency_ms=%d input_tokens=%s output_tokens=%s",
        getattr(llm, "model_id", None) or getattr(llm, "model", None) or "injected",
        kind,
        (time.perf_counter() - started) * 1000,
        usage.get("input_tokens", "?"),
        usage.get("output_tokens", "?"),
    )
    return _text_of(msg)


def call_json[T: BaseModel](
    prompt: str,
    schema: type[T],
    *,
    kind: ModelKind = "main",
    system: str | None = None,
    llm: Any = None,
) -> T:
    """Ask the model for a JSON object and return it validated against `schema`.

    One repair retry: the model is shown its own reply and the validation error. Raises
    LLMError if the second attempt also fails. `llm` (a LangChain-style object with
    `.invoke`) is injectable for tests; so is the global `set_llm_override`.
    """
    instructions = (
        "Reply with a single JSON object that matches this JSON schema. "
        "No prose, no code fences.\n" + schema_hint(schema)
    )
    messages: Messages = [
        ("system", f"{system}\n\n{instructions}" if system else instructions),
        ("human", prompt),
    ]
    error = ""
    for attempt in range(2):
        try:
            reply = _invoke(llm, messages, kind)
        except LLMError:
            raise
        except Exception as exc:  # network, throttling, ExpiredToken, access denied
            raise LLMError(f"model call failed: {type(exc).__name__}: {exc}") from exc
        try:
            return schema.model_validate(extract_json(reply))
        except (ValueError, ValidationError) as exc:
            error = str(exc)
            if attempt == 0:
                messages += [
                    ("ai", reply),
                    (
                        "human",
                        "Your reply was not valid. Fix it and reply with the corrected JSON "
                        f"object only. Error: {error[:1500]}",
                    ),
                ]
    raise LLMError(f"invalid JSON after one repair attempt: {error[:500]}")
